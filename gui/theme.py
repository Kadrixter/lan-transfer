"""Kolory i drobne helpery wyglądu (ciemny motyw)."""
import customtkinter as ctk

BG = "#111317"
PANEL = "#181b21"
ROW = "#1f232b"
ROW_HOVER = "#2a2f3a"
TRACK = "#2a2f3a"
ACCENT = "#4f8cff"
ACCENT_HOVER = "#3b72e0"
ACCENT2 = "#a855f7"
TEXT = "#e8eaf0"
MUTED = "#8b92a3"
GREEN = "#34d399"
RED = "#f87171"
YELLOW = "#fbbf24"
ORANGE = "#fb923c"

_KINDS = {
    "primary": (ACCENT, ACCENT_HOVER, "#ffffff"),
    "secondary": (ROW, ROW_HOVER, TEXT),
    "danger": ("#b4383f", "#952d33", "#ffffff"),
    "success": ("#1f9d6b", "#178257", "#ffffff"),
}


def font(size=13, weight="normal"):
    return ctk.CTkFont(family="Segoe UI", size=size, weight=weight)


def button(master, text, command=None, kind="secondary", **kw):
    fg, hover, txt = _KINDS[kind]
    kw.setdefault("height", 34)
    kw.setdefault("corner_radius", 8)
    kw.setdefault("font", font(13, "bold" if kind == "primary" else "normal"))
    return ctk.CTkButton(master, text=text, command=command, fg_color=fg,
                         hover_color=hover, text_color=txt, **kw)


def lerp_color(c1, c2, t):
    t = max(0.0, min(1.0, t))
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


def shorten(text, n=70):
    return text if len(text) <= n else text[:n - 1] + "…"
