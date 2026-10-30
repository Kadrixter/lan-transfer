"""Formatowanie rozmiarów, prędkości i czasu."""

GB = 1024 ** 3
MB = 1024 ** 2


def fmt_size(n):
    if n is None:
        return "liczę…"
    if n >= GB:
        return f"{n / GB:.2f} GB"
    return f"{n / MB:.2f} MB"


def fmt_speed(bps):
    return f"{bps / MB:.1f} MB/s"


def fmt_eta(seconds):
    if seconds is None or seconds < 0 or seconds == float("inf"):
        return "—"
    s = int(seconds)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
