"""Serwer hosta: obsługuje wielu klientów równolegle (wątek na klienta)."""
import hashlib
import hmac
import itertools
import os
import secrets
import socket
import threading
import time
import uuid

from net.discovery import DiscoveryResponder
from net.protocol import CHUNK, MAGIC, SOCK_BUF, TCP_PORT, make_proof, recv_msg, send_msg
from utils.files import collect_tree, safe_rel_parts
from utils.speed import SpeedMeter


class ClientSession:
    def __init__(self, sid, name, addr):
        self.id = sid
        self.name = name
        self.ip = addr[0]
        self.connected_at = time.time()
        self.total = 0
        self.sent = 0
        self.current = ""
        self.state = "przegląda pliki"
        self.meter = SpeedMeter()
        self.sock = None


class FileServer:
    def __init__(self, name, password=""):
        self.name = name
        self.password = password or ""
        self.id = uuid.uuid4().hex
        self.port = None
        self._items = {}
        self._items_lock = threading.Lock()
        self._sessions = {}
        self._sess_lock = threading.Lock()
        self._sid = itertools.count(1)
        self._listener = None
        self._running = False
        self._discovery = None

    @property
    def protected(self):
        return bool(self.password)

    @property
    def discovery_error(self):
        return self._discovery.error if self._discovery else None

    # ---------- lista hostowanych elementów ----------

    def set_items(self, paths):
        """Buduje indeks plików (może trwać – wywoływać w tle)."""
        items = {}
        for p in paths:
            p = os.path.abspath(p)
            if not os.path.exists(p):
                continue
            name, files, dirs = collect_tree(p)
            iid = hashlib.sha1(p.lower().encode("utf-8", "surrogatepass")).hexdigest()[:12]
            items[iid] = {
                "id": iid, "name": name, "path": p, "is_dir": os.path.isdir(p),
                "size": sum(f["size"] for f in files), "files": files, "dirs": dirs,
            }
        with self._items_lock:
            self._items = items

    def items_public(self):
        with self._items_lock:
            return [{k: v for k, v in it.items() if k != "path"} for it in self._items.values()]

    # ---------- start / stop ----------

    def start(self):
        ls = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        for port in range(TCP_PORT, TCP_PORT + 20):
            try:
                ls.bind(("", port))
                break
            except OSError:
                continue
        else:
            ls.close()
            raise OSError("Brak wolnego portu TCP")
        ls.listen(16)
        self._listener = ls
        self.port = port
        self._running = True
        threading.Thread(target=self._accept_loop, daemon=True).start()
        self._discovery = DiscoveryResponder(self._discovery_info)
        self._discovery.start()

    def stop(self):
        self._running = False
        if self._discovery:
            self._discovery.stop()
        if self._listener:
            try:
                self._listener.close()
            except OSError:
                pass
        with self._sess_lock:
            for s in self._sessions.values():
                try:
                    s.sock.close()
                except OSError:
                    pass

    def _discovery_info(self):
        return {"magic": MAGIC, "id": self.id, "name": self.name,
                "port": self.port, "protected": self.protected}

    def snapshot(self):
        with self._sess_lock:
            sessions = list(self._sessions.values())
        return [{"id": s.id, "name": s.name, "ip": s.ip, "connected_at": s.connected_at,
                 "total": s.total, "sent": s.sent, "current": s.current,
                 "state": s.state, "speed": s.meter.speed()} for s in sessions]

    # ---------- obsługa klientów ----------

    def _accept_loop(self):
        while self._running:
            try:
                conn, addr = self._listener.accept()
            except OSError:
                break
            threading.Thread(target=self._handle, args=(conn, addr), daemon=True).start()

    def _handle(self, conn, addr):
        session = None
        try:
            conn.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, SOCK_BUF)
            nonce = secrets.token_hex(16)
            send_msg(conn, {"type": "hello", "name": self.name,
                            "protected": self.protected, "nonce": nonce})
            msg = recv_msg(conn)
            if msg.get("cmd") != "auth":
                return
            if self.protected and not hmac.compare_digest(
                    str(msg.get("proof", "")), make_proof(self.password, nonce)):
                send_msg(conn, {"ok": False, "error": "Nieprawidłowe hasło"})
                return
            send_msg(conn, {"ok": True})

            session = ClientSession(next(self._sid), str(msg.get("name") or addr[0])[:64], addr)
            session.sock = conn
            with self._sess_lock:
                self._sessions[session.id] = session

            while self._running:
                msg = recv_msg(conn)
                cmd = msg.get("cmd")
                if cmd == "list":
                    send_msg(conn, {"items": self.items_public()})
                elif cmd == "begin":
                    session.total = int(msg.get("total", 0))
                    session.sent = 0
                    session.meter.reset()
                    session.state = "pobiera"
                elif cmd == "get":
                    self._send_file(conn, session, msg)
                elif cmd == "end":
                    session.state = "zakończył pobieranie" if msg.get("ok", True) else "przerwał pobieranie"
                    session.current = ""
                elif cmd == "bye":
                    break
        except (OSError, ValueError):
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass
            if session:
                with self._sess_lock:
                    self._sessions.pop(session.id, None)

    def _send_file(self, conn, session, msg):
        with self._items_lock:
            item = self._items.get(msg.get("item"))
        rel = str(msg.get("rel", ""))
        try:
            if not item:
                raise FileNotFoundError("Ten element nie jest już hostowany")
            parts = safe_rel_parts(rel)
            if parts[0] != item["name"] or (item["is_dir"] and len(parts) < 2):
                raise ValueError(f"Niedozwolona ścieżka: {rel}")
            full = os.path.join(item["path"], *parts[1:]) if item["is_dir"] else item["path"]
            f = open(full, "rb")
        except (OSError, ValueError) as e:
            send_msg(conn, {"ok": False, "error": str(e) or "Błąd pliku"})
            return
        with f:
            size = os.fstat(f.fileno()).st_size
            offset = int(msg.get("offset", 0))
            if not 0 <= offset <= size:
                offset = 0
            f.seek(offset)
            send_msg(conn, {"ok": True, "size": size, "offset": offset})
            session.current = rel
            remaining = size - offset
            while remaining > 0:
                buf = f.read(min(CHUNK, remaining))
                if not buf:  # plik skurczył się w trakcie – zrywamy, klient wznowi
                    raise ConnectionError("Plik zmienił się w trakcie wysyłania")
                conn.sendall(buf)
                remaining -= len(buf)
                session.sent += len(buf)
                session.meter.add(len(buf))
