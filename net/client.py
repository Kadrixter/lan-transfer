"""Klient: połączenie z hostem i pobieranie z wznawianiem."""
import os
import socket
import threading
import time

from net.protocol import CHUNK, SOCK_BUF, make_proof, recv_msg, send_msg
from utils.files import safe_rel_parts
from utils.speed import SpeedMeter


class AuthError(Exception):
    pass


class PasswordRequired(AuthError):
    pass


class RemoteFileError(Exception):
    pass


class LocalWriteError(Exception):
    pass


class HostConnection:
    def __init__(self, ip, port, password=None, client_name=None):
        self.ip = ip
        self.port = port
        self.password = password
        self.client_name = client_name or socket.gethostname()
        self.sock = None
        self.host_name = ""
        self.protected = False
        self.connect()

    def connect(self):
        self.close()
        s = socket.create_connection((self.ip, self.port), timeout=5)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, SOCK_BUF)
            s.settimeout(30)
            hello = recv_msg(s)
            if hello.get("type") != "hello":
                raise ConnectionError("To nie jest host tej aplikacji")
            self.host_name = hello.get("name", "")
            self.protected = bool(hello.get("protected"))
            if self.protected and not self.password:
                raise PasswordRequired("Host wymaga hasła")
            proof = make_proof(self.password, hello["nonce"]) if self.protected else ""
            send_msg(s, {"cmd": "auth", "name": self.client_name, "proof": proof})
            resp = recv_msg(s)
            if not resp.get("ok"):
                raise AuthError(resp.get("error", "Odmowa dostępu"))
        except BaseException:
            s.close()
            raise
        self.sock = s

    def send(self, obj):
        if self.sock is None:
            raise ConnectionError("Brak połączenia z hostem")
        send_msg(self.sock, obj)

    def recv(self):
        if self.sock is None:
            raise ConnectionError("Brak połączenia z hostem")
        return recv_msg(self.sock)

    def list_items(self):
        self.send({"cmd": "list"})
        return self.recv()["items"]

    def close(self):
        s, self.sock = self.sock, None
        if s:
            try:
                send_msg(s, {"cmd": "bye"})
            except OSError:
                pass
            try:
                s.close()
            except OSError:
                pass


class DownloadFile:
    __slots__ = ("item_id", "rel", "size", "done", "status", "error")

    def __init__(self, item_id, rel, size):
        self.item_id = item_id
        self.rel = rel
        self.size = size
        self.done = 0
        self.status = "czeka"
        self.error = ""


class DownloadJob(threading.Thread):
    """Pobiera pliki po kolei. Niedokończone pliki trzymane są jako *.part,
    więc ponowne pobranie do tego samego folderu wznawia od miejsca przerwania."""

    MAX_RETRIES = 5

    def __init__(self, conn, items, dest_root):
        super().__init__(daemon=True)
        self.conn = conn
        self.dest_root = dest_root
        self.files = []
        self.dirs = []
        for it in items:
            self.dirs += it["dirs"]
            for f in it["files"]:
                self.files.append(DownloadFile(it["id"], f["rel"], f["size"]))
        self.total = sum(f.size for f in self.files)
        self.meter = SpeedMeter(3.0)
        self.current = None
        self.failed = 0
        self.error = None
        self.finished = False
        self._cancel = threading.Event()

    @property
    def done_bytes(self):
        return sum(f.done for f in self.files)

    @property
    def cancelled(self):
        return self._cancel.is_set()

    def cancel(self):
        self._cancel.set()
        self.conn.close()  # przerywa blokujące recv w wątku pobierania

    def _dest(self, rel):
        return os.path.join(self.dest_root, *safe_rel_parts(rel))

    def run(self):
        try:
            self._run()
        except Exception as e:
            if not self.cancelled:
                self.error = str(e) or e.__class__.__name__
        finally:
            self.current = None
            if self.error:
                self.conn.close()  # stan strumienia nieznany – wznowienie połączy się od nowa
            elif not self.cancelled:
                try:
                    self.conn.send({"cmd": "end", "ok": self.failed == 0})
                except OSError:
                    pass
            self.finished = True

    def _begin(self):
        self.conn.send({"cmd": "begin", "total": max(self.total - self.done_bytes, 0)})

    def _run(self):
        try:
            for d in self.dirs:
                os.makedirs(self._dest(d), exist_ok=True)
        except OSError as e:
            raise LocalWriteError(f"Nie można utworzyć folderu: {e}")

        # wznawianie: pliki kompletne pomijamy, *.part liczymy jako pobrane
        for f in self.files:
            dest = self._dest(f.rel)
            if os.path.isfile(dest) and os.path.getsize(dest) == f.size:
                f.done = f.size
                f.status = "już jest"
            elif os.path.isfile(dest + ".part"):
                f.done = min(os.path.getsize(dest + ".part"), f.size)

        if self.conn.sock is None:
            self.conn.connect()
        self._begin()

        retries = 0
        i = 0
        while i < len(self.files):
            if self.cancelled:
                return
            f = self.files[i]
            if f.status in ("gotowe", "już jest"):
                i += 1
                continue
            try:
                self._download_one(f)
                retries = 0
                i += 1
            except RemoteFileError as e:
                f.status = "błąd"
                f.error = str(e)
                self.failed += 1
                i += 1
            except OSError as e:
                if self.cancelled:
                    return
                retries += 1
                if retries > self.MAX_RETRIES:
                    f.status = "błąd"
                    raise ConnectionError(f"Utracono połączenie z hostem ({e})")
                f.status = "ponawiam…"
                time.sleep(min(2 * retries, 10))
                try:
                    self.conn.connect()
                    self._begin()
                except OSError:
                    pass  # kolejna próba w następnym obiegu pętli

    def _download_one(self, f):
        dest = self._dest(f.rel)
        part = dest + ".part"
        try:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            offset = os.path.getsize(part) if os.path.isfile(part) else 0
        except OSError as e:
            raise LocalWriteError(f"Błąd zapisu: {e}")
        if offset > f.size:
            offset = 0

        f.status = "pobieranie"
        self.current = f
        self.conn.send({"cmd": "get", "item": f.item_id, "rel": f.rel, "offset": offset})
        resp = self.conn.recv()
        if not resp.get("ok"):
            raise RemoteFileError(resp.get("error", "Błąd po stronie hosta"))
        size, offset = int(resp["size"]), int(resp["offset"])
        if size != f.size:
            self.total += size - f.size
            f.size = size
        f.done = offset

        sock = self.conn.sock
        remaining = size - offset
        buf = bytearray(CHUNK)
        mv = memoryview(buf)
        try:
            fh = open(part, "ab" if offset else "wb")
        except OSError as e:
            raise LocalWriteError(f"Nie można zapisać {f.rel}: {e}")
        with fh:
            while remaining > 0:
                n = sock.recv_into(mv[:min(CHUNK, remaining)])
                if n == 0:
                    raise ConnectionError("Host zamknął połączenie")
                try:
                    fh.write(mv[:n])
                except OSError as e:
                    raise LocalWriteError(f"Błąd zapisu (brak miejsca?): {e}")
                remaining -= n
                f.done += n
                self.meter.add(n)
        try:
            os.replace(part, dest)
        except OSError as e:
            raise LocalWriteError(f"Nie można zapisać {f.rel}: {e}")
        f.status = "gotowe"
