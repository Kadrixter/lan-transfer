"""Ekran startowy: okno przecięte ukośnie – lewa strona Klient, prawa Host.

Po najechaniu strona się poszerza, rozjaśnia i powiększa napisy;
po kliknięciu wypełnia cały ekran i przenosi do wybranego trybu.
"""
import math
import tkinter as tk
import tkinter.font as tkfont

from gui import theme as T
from gui.base import View

SIDES = {
    "client": {"color": T.ACCENT2, "icon": "⬇", "title": "KLIENT",
               "desc": "Znajdź hosta i pobierz pliki", "phase": 0.0},
    "host": {"color": T.ACCENT, "icon": "⬆", "title": "HOST",
             "desc": "Udostępnij pliki w sieci", "phase": math.pi},
}


class StartView(View):
    def __init__(self, app):
        super().__init__(app)
        self.cv = tk.Canvas(self, bg=T.BG, highlightthickness=0, bd=0, cursor="hand2")
        self.cv.pack(fill="both", expand=True)

        self.split = 0.5
        self.hover = {"client": 0.0, "host": 0.0}
        self.hovered = None
        self.leaving = None
        self.t = 0
        self._job = None

        self.poly = {s: self.cv.create_polygon(0, 0, 0, 0, outline="") for s in SIDES}
        self.glow = self.cv.create_line(0, 0, 0, 0, width=12, capstyle="round")
        self.line = self.cv.create_line(0, 0, 0, 0, width=3, capstyle="round")
        self.fonts, self.texts, self._sizes = {}, {}, {}
        for s, cfg in SIDES.items():
            f = {"icon": tkfont.Font(family="Segoe UI Symbol", size=-70, weight="bold"),
                 "title": tkfont.Font(family="Segoe UI", size=-44, weight="bold"),
                 "desc": tkfont.Font(family="Segoe UI", size=-16),
                 "hint": tkfont.Font(family="Segoe UI", size=-13, weight="bold")}
            self.fonts[s] = f
            self.texts[s] = {
                "icon": self.cv.create_text(0, 0, text=cfg["icon"], font=f["icon"]),
                "title": self.cv.create_text(0, 0, text=cfg["title"], font=f["title"]),
                "desc": self.cv.create_text(0, 0, text=cfg["desc"], font=f["desc"]),
                "hint": self.cv.create_text(0, 0, text="KLIKNIJ, ABY WEJŚĆ  →" if s == "host"
                                            else "←  KLIKNIJ, ABY WEJŚĆ", font=f["hint"]),
            }
        self.footer = self.cv.create_text(0, 0, text="LAN Transfer  •  sieć lokalna i Radmin VPN",
                                          font=tkfont.Font(family="Segoe UI", size=-12), fill=T.MUTED)

        self.cv.bind("<Motion>", self._on_motion)
        self.cv.bind("<Leave>", lambda e: self._set_hover(None))
        self.cv.bind("<Button-1>", self._on_click)
        self._tick()

    # ----- geometria -----

    def _geom(self):
        w, h = max(self.cv.winfo_width(), 2), max(self.cv.winfo_height(), 2)
        slant = h * 0.14
        mid = self.split * w
        return w, h, slant, mid + slant, mid - slant  # górny i dolny x przekątnej

    def _side_at(self, x, y):
        w, h, _, tx, bx = self._geom()
        return "client" if x < tx + (bx - tx) * y / h else "host"

    # ----- zdarzenia -----

    def _set_hover(self, side):
        if not self.leaving:
            self.hovered = side

    def _on_motion(self, e):
        self._set_hover(self._side_at(e.x, e.y))

    def _on_click(self, e):
        if not self.leaving:
            self.leaving = self._side_at(e.x, e.y)
            self.hovered = self.leaving

    # ----- animacja -----

    def _tick(self):
        self.t += 1
        w, h, slant, _, _ = self._geom()
        if self.leaving:
            # strona rozlewa się na cały ekran (z zapasem na skos)
            target = 1 + slant / w + 0.02 if self.leaving == "client" else -slant / w - 0.02
            self.split += (target - self.split) * 0.16
        else:
            target = {"client": 0.58, "host": 0.42}.get(self.hovered, 0.5)
            self.split += (target - self.split) * 0.12
        for s in SIDES:
            goal = 1.0 if s == self.hovered else 0.0
            self.hover[s] += (goal - self.hover[s]) * 0.15
        self._render()

        if self.leaving and abs(target - self.split) < 0.01:
            self._job = None
            self._open(self.leaving)
            return
        self._job = self.after(16, self._tick)

    def _render(self):
        w, h, slant, tx, bx = self._geom()
        cv = self.cv
        cv.coords(self.poly["client"], 0, 0, tx, 0, bx, h, 0, h)
        cv.coords(self.poly["host"], tx, 0, w, 0, w, h, bx, h)

        hv_c, hv_h = self.hover["client"], self.hover["host"]
        line_color = T.lerp_color(T.lerp_color(T.ACCENT2, T.ACCENT, 0.5),
                                  T.ACCENT2 if hv_c > hv_h else T.ACCENT, max(hv_c, hv_h))
        cv.coords(self.glow, tx, -10, bx, h + 10)
        cv.coords(self.line, tx, -10, bx, h + 10)
        cv.itemconfigure(self.glow, fill=T.lerp_color(T.BG, line_color, 0.35))
        cv.itemconfigure(self.line, fill=line_color)

        mid = self.split * w
        centers = {"client": mid / 2 - slant * 0.3, "host": (mid + w) / 2 + slant * 0.3}
        for s, cfg in SIDES.items():
            hv = self.hover[s]
            color = cfg["color"]
            fill = T.lerp_color(T.BG, color, 0.10 + 0.22 * hv)
            cv.itemconfigure(self.poly[s], fill=fill)

            self._resize(s, "icon", 70 + 26 * hv)
            self._resize(s, "title", 44 + 10 * hv)

            cx, cy = centers[s], h / 2
            bob = math.sin(self.t / 18 + cfg["phase"]) * (4 + 6 * hv)
            items = self.texts[s]
            cv.coords(items["icon"], cx, cy - 78 + bob)
            cv.coords(items["title"], cx, cy + 14)
            cv.coords(items["desc"], cx, cy + 56)
            cv.coords(items["hint"], cx, cy + 96 + 6 * (1 - hv))
            cv.itemconfigure(items["icon"], fill=T.lerp_color(T.lerp_color(T.BG, color, 0.55), color, hv))
            cv.itemconfigure(items["title"], fill=T.lerp_color(T.MUTED, "#ffffff", 0.4 + 0.6 * hv))
            cv.itemconfigure(items["desc"], fill=T.lerp_color(T.MUTED, T.TEXT, hv))
            cv.itemconfigure(items["hint"], fill=T.lerp_color(fill, color, hv))

        cv.coords(self.footer, w / 2, h - 18)
        cv.tag_raise(self.footer)

    def _resize(self, side, key, px):
        px = int(px)
        if self._sizes.get((side, key)) != px:
            self._sizes[(side, key)] = px
            self.fonts[side][key].configure(size=-px)

    def _open(self, side):
        if side == "host":
            from gui.host_view import HostSetupView
            self.app.show(HostSetupView)
        else:
            from gui.client_view import ClientServersView
            self.app.show(ClientServersView)

    def cleanup(self):
        if self._job:
            self.after_cancel(self._job)
            self._job = None
