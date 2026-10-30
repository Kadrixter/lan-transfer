"""Interfejsy sieciowe i wykrywanie Radmin VPN."""
import ipaddress
import socket

try:
    import psutil
except ImportError:  # działa też bez psutil, tylko bez nazw interfejsów
    psutil = None

# Radmin VPN przydziela adresy z puli 26.0.0.0/8
RADMIN_NET = ipaddress.ip_network("26.0.0.0/8")


def interfaces():
    """Lista aktywnych interfejsów IPv4 (bez loopback i APIPA)."""
    res = []
    if psutil:
        stats = psutil.net_if_stats()
        for name, addrs in psutil.net_if_addrs().items():
            st = stats.get(name)
            if st and not st.isup:
                continue
            for a in addrs:
                if a.family != socket.AF_INET or not a.netmask:
                    continue
                ip = a.address
                if ip.startswith("127.") or ip.startswith("169.254."):
                    continue
                net = ipaddress.ip_network(f"{ip}/{a.netmask}", strict=False)
                radmin = "radmin" in name.lower() or ipaddress.ip_address(ip) in RADMIN_NET
                res.append({"name": name, "ip": ip, "network": net,
                            "broadcast": str(net.broadcast_address), "radmin": radmin})
    else:
        try:
            ips = socket.gethostbyname_ex(socket.gethostname())[2]
        except OSError:
            ips = []
        for ip in ips:
            if ip.startswith("127."):
                continue
            net = ipaddress.ip_network(f"{ip}/24", strict=False)
            res.append({"name": "?", "ip": ip, "network": net,
                        "broadcast": str(net.broadcast_address),
                        "radmin": ipaddress.ip_address(ip) in RADMIN_NET})
    return res


def is_radmin_ip(ip, ifaces=None):
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if addr in RADMIN_NET:
        return True
    for i in ifaces if ifaces is not None else interfaces():
        if i["radmin"] and addr in i["network"]:
            return True
    return False


def radmin_available():
    return any(i["radmin"] for i in interfaces())
