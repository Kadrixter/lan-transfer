"""Wykrywanie hostów w sieci lokalnej (LAN + Radmin VPN) przez UDP.

Klient co 1,5 s wysyła zapytanie (broadcast na każdy interfejs + localhost
+ ręcznie dodane IP), host odpowiada swoimi danymi.
"""
import json
import socket
import threading
import time

from net.protocol import DISCOVERY_PORT, MAGIC, QUERY
from utils.netinfo import interfaces, is_radmin_ip

HOST_TTL = 5.0


class DiscoveryResponder(threading.Thread):
    """Działa po stronie hosta – odpowiada na zapytania klientów."""

    def __init__(self, info_fn):
        super().__init__(daemon=True)
        self.info_fn = info_fn
        self.error = None
        self._stop = threading.Event()

    def run(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("", DISCOVERY_PORT))
        except OSError as e:
            self.error = f"Nie można otworzyć portu UDP {DISCOVERY_PORT}: {e}"
            s.close()
            return
        s.settimeout(0.5)
        while not self._stop.is_set():
            try:
                data, addr = s.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:  # Windows zgłasza ICMP "port unreachable" jako błąd recvfrom
                continue
            if data.strip() == QUERY:
                try:
                    s.sendto(json.dumps(self.info_fn()).encode("utf-8"), addr)
                except OSError:
                    pass
        s.close()

    def stop(self):
        self._stop.set()


class DiscoveryScanner(threading.Thread):
    """Działa po stronie klienta – zbiera listę dostępnych hostów."""

    def __init__(self):
        super().__init__(daemon=True)
        self._hosts = {}
        self._lock = threading.Lock()
        self._manual = set()
        self._ifaces = []
        self._stop = threading.Event()
        self._wake = threading.Event()

    def add_manual(self, ip):
        self._manual.add(ip)
        self._wake.set()

    def run(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.bind(("", 0))
        s.settimeout(0.25)
        next_query = 0.0
        while not self._stop.is_set():
            now = time.monotonic()
            if now >= next_query or self._wake.is_set():
                self._wake.clear()
                self._send_queries(s)
                next_query = now + 1.5
            try:
                data, addr = s.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                continue
            try:
                info = json.loads(data.decode("utf-8"))
            except ValueError:
                continue
            if isinstance(info, dict) and info.get("magic") == MAGIC:
                self._register(info, addr[0])
        s.close()

    def _send_queries(self, s):
        self._ifaces = interfaces()
        targets = {"255.255.255.255", "127.0.0.1"}
        targets |= {i["broadcast"] for i in self._ifaces}
        targets |= self._manual
        for t in targets:
            try:
                s.sendto(QUERY, (t, DISCOVERY_PORT))
            except OSError:
                pass

    def _register(self, info, ip):
        radmin = is_radmin_ip(ip, self._ifaces)
        key = (info.get("id"), radmin)
        now = time.monotonic()
        with self._lock:
            old = self._hosts.get(key)
            # ten sam host widziany przez localhost i przez LAN – wolimy adres LAN
            if old and not old["ip"].startswith("127.") and ip.startswith("127."):
                old["last_seen"] = now
                return
            self._hosts[key] = {
                "key": f"{info.get('id')}|{radmin}",
                "name": str(info.get("name", "?")),
                "ip": ip,
                "port": int(info.get("port", 0)),
                "protected": bool(info.get("protected")),
                "radmin": radmin,
                "last_seen": now,
            }

    def get_hosts(self):
        now = time.monotonic()
        with self._lock:
            for k in [k for k, h in self._hosts.items() if now - h["last_seen"] > HOST_TTL]:
                del self._hosts[k]
            hosts = [dict(h) for h in self._hosts.values()]
        hosts.sort(key=lambda h: (h["radmin"], h["name"].lower()))
        return hosts

    def stop(self):
        self._stop.set()
