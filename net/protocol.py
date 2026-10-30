"""Wspólny protokół: wiadomości JSON poprzedzone 4-bajtową długością.

Przebieg połączenia TCP:
  host  -> {"type": "hello", "name", "protected", "nonce"}
  klient-> {"cmd": "auth", "name", "proof"}        (proof = HMAC(hasło, nonce))
  host  -> {"ok": true} | {"ok": false, "error"}
  potem komendy klienta:
    list                      -> {"items": [...]}
    begin {total}             (informacja dla hosta, ile bajtów zostanie pobranych)
    get {item, rel, offset}   -> {"ok", "size", "offset"} + surowe bajty od offsetu
    end {ok}
    bye
"""
import hashlib
import hmac
import json
import struct

MAGIC = "LANTRANSFER1"
QUERY = b"LANTRANSFER?"
DISCOVERY_PORT = 50505
TCP_PORT = 50506
CHUNK = 1024 * 1024
SOCK_BUF = 4 * 1024 * 1024
MAX_MSG = 256 * 1024 * 1024


def send_msg(sock, obj):
    data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    sock.sendall(struct.pack("!I", len(data)) + data)


def recv_exact(sock, n):
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Połączenie zostało zamknięte")
        buf += chunk
    return bytes(buf)


def recv_msg(sock):
    (n,) = struct.unpack("!I", recv_exact(sock, 4))
    if n > MAX_MSG:
        raise ConnectionError("Zbyt duża wiadomość")
    return json.loads(recv_exact(sock, n).decode("utf-8"))


def make_proof(password, nonce):
    return hmac.new((password or "").encode("utf-8"), nonce.encode("ascii"), hashlib.sha256).hexdigest()
