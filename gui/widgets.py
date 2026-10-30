"""Własne widgety: animowany pasek postępu, lista z checkboxami, okno hasła."""
import queue
import threading
import tkinter as tk

import customtkinter as ctk

from gui import theme as T
from utils.files import entry_size
from utils.fmt import fmt_size


def _rr(x1, y1, x2, y2, r):
    """Punkty zaokrąglonego prostokąta dla create_polygon(smooth=True)."""
    return [x1 + r, y1, x1 + r, y1, x2 - r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
            x2, y1 + r, x2, y2 - r, x2, y2 - r, x2, y2, x2 - r, y2, x2 - r, y2,
            x1 + r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y2 - r, x1, y1 + r,
            x1, y1 + r, x1, y1]


class AnimatedProgressBar(tk.Canvas):
    """Pasek z płynnym dojazdem do wartości, gradientem koloru i przesuwającym się
    połyskiem. Tryb nieokreślony = przesuwający się blok."""

    def __init__(self, master, height=14, bg=T.PANEL, **kw):
        super().__init__(master, height=height, bg=bg, highlightthickness=0, bd=0, **kw)
        self._h = height
        self._target = 0.0
        self._shown = 0.0
        self._phase = 0.0
        self._indeterminate = False
        self._color = None
        self._track = self.create_polygon(0, 0, 0, 0, smooth=True, fill=T.TRACK, outline="")
        self._fill = self.create_polygon(0, 0, 0, 0, smooth=True, fill=T.ACCENT, outline="")
        self._shine = self.create_polygon(0, 0, 0, 0, smooth=True, fill=T.ACCENT, outline="")
        self._job = None
        self._tick()

    def set(self, value):
        self._target = max(0.0, min(1.0, value))
        self._indeterminate = False

    def set_indeterminate(self, on=True):
        self._indeterminate = on

    def set_color(self, color=None):
        """Wymusza kolor (np. zielony po zakończeniu); None = gradient."""
        self._color = color

    def destroy(self):
        if self._job:
            self.after_cancel(self._job)
            self._job = None
        super().destroy()

    def _tick(self):
        diff = self._target - self._shown
        self._shown = self._target if abs(diff) < 0.0005 else self._shown + diff * 0.15
        self._phase = (self._phase + 0.012) % 1.0
        self._draw()
        self._job = self.after(33, self._tick)

    def _draw(self):
        w, h = self.winfo_width(), self._h
        if w < 4:
            return
        self.coords(self._track, *_rr(0, 0, w, h, h / 2))

        if self._indeterminate:
            seg = w * 0.28
            x = (self._phase * 1.4 - 0.2) * w
            x1, x2 = max(0, x), min(w, x + seg)
            if x2 - x1 < 2:
                self.itemconfigure(self._fill, state="hidden")
            else:
                color = T.lerp_color(T.ACCENT, T.ACCENT2, self._phase)
                self.coords(self._fill, *_rr(x1, 0, x2, h, min(h / 2, (x2 - x1) / 2)))
                self.itemconfigure(self._fill, fill=color, state="normal")
            self.itemconfigure(self._shine, state="hidden")
            return

        fw = self._shown * w
        if fw < 1:
            self.itemconfigure(self._fill, state="hidden")
            self.itemconfigure(self._shine, state="hidden")
            return
        color = self._color or T.lerp_color(T.ACCENT, T.ACCENT2, self._shown)
        self.coords(self._fill, *_rr(0, 0, fw, h, min(h / 2, fw / 2)))
        self.itemconfigure(self._fill, fill=color, state="normal")

        sw = 60
        sx = self._phase * (fw + sw) - sw
        x1, x2 = max(0, sx), min(fw, sx + sw)
        if self._color is None and x2 - x1 > 3 and h > 6:
            self.coords(self._shine, *_rr(x1, 2, x2, h - 2, min((h - 4) / 2, (x2 - x1) / 2)))
            self.itemconfigure(self._shine, fill=T.lerp_color(color, "#ffffff", 0.3), state="normal")
        else:
            self.itemconfigure(self._shine, state="hidden")


class SelectableList(ctk.CTkScrollableFrame):
    """Lista elementów z checkboxem, ikoną, nazwą i rozmiarem.
    Rozmiary folderów mogą być liczone w tle (autosize)."""

    def __init__(self, master, on_change=None, checkable=True, **kw):
        kw.setdefault("fg_color", T.PANEL)
        kw.setdefault("corner_radius", 10)
        super().__init__(master, **kw)
        self.on_change = on_change
        self.checkable = checkable
        self._rows = {}
        self._gen = 0
        self._jobs = queue.Queue()
        self._results = queue.Queue()
        self._worker = None
        self._empty = ctk.CTkLabel(self, text="", text_color=T.MUTED, font=T.font(13))
        self._poll_job = self.after(150, self._poll)

    # ----- elementy -----

    def add(self, key, name, is_dir, size=None, checked=False, badge=None):
        if key in self._rows:
            return
        self._empty.pack_forget()
        row = ctk.CTkFrame(self, fg_color=T.ROW, corner_radius=8)
        row.pack(fill="x", padx=6, pady=3)
        var = tk.BooleanVar(value=checked)
        cb = None
        if self.checkable:
            cb = ctk.CTkCheckBox(row, text="", width=22, checkbox_width=20, checkbox_height=20,
                                 variable=var, onvalue=True, offvalue=False,
                                 command=self._changed, fg_color=T.ACCENT,
                                 hover_color=T.ACCENT_HOVER, border_color=T.MUTED)
            cb.pack(side="left", padx=(10, 2), pady=7)
        icon = ctk.CTkLabel(row, text="📁" if is_dir else "📄", width=24, font=T.font(14),
                            text_color=T.YELLOW if is_dir else T.MUTED)
        icon.pack(side="left", padx=(8 if not cb else 2, 4), pady=7)
        name_lbl = ctk.CTkLabel(row, text=T.shorten(name, 80), anchor="w", font=T.font(13),
                                text_color=T.TEXT)
        name_lbl.pack(side="left", fill="x", expand=True)
        size_lbl = ctk.CTkLabel(row, text=fmt_size(size), width=95, anchor="e",
                                font=T.font(12), text_color=T.MUTED)
        size_lbl.pack(side="right", padx=(6, 14))
        widgets = [row, icon, name_lbl, size_lbl]
        if badge:
            b = ctk.CTkLabel(row, text=badge, font=T.font(11), text_color=T.ORANGE)
            b.pack(side="right", padx=4)
            widgets.append(b)
        if cb:
            for w in widgets:
                w.bind("<Button-1>", lambda e, c=cb: c.toggle())
        self._rows[key] = {"frame": row, "var": var, "size": size, "size_lbl": size_lbl,
                           "is_dir": is_dir, "name": name}

    def autosize(self, key, path):
        if self._worker is None:
            self._worker = threading.Thread(target=self._size_worker, daemon=True)
            self._worker.start()
        self._jobs.put((self._gen, key, path))

    def set_size(self, key, size):
        r = self._rows.get(key)
        if r:
            r["size"] = size
            r["size_lbl"].configure(text=fmt_size(size))

    def clear(self, empty_text=""):
        for r in self._rows.values():
            r["frame"].destroy()
        self._rows = {}
        self._gen += 1
        self.set_empty_text(empty_text)

    def set_empty_text(self, text):
        self._empty.configure(text=text)
        if text and not self._rows:
            self._empty.pack(pady=40)
        else:
            self._empty.pack_forget()

    # ----- zaznaczenie -----

    def keys(self):
        return list(self._rows)

    def selected(self):
        return [k for k, r in self._rows.items() if r["var"].get()]

    def size_of(self, keys):
        """(suma, czy_wszystko_policzone)"""
        sizes = [self._rows[k]["size"] for k in keys if k in self._rows]
        return sum(s or 0 for s in sizes), all(s is not None for s in sizes)

    def set_all(self, value):
        for r in self._rows.values():
            r["var"].set(value)
        self._changed()

    def _changed(self):
        if self.on_change:
            self.on_change()

    # ----- liczenie rozmiarów w tle -----

    def _size_worker(self):
        while True:
            gen, key, path = self._jobs.get()
            if gen != self._gen:
                continue
            self._results.put((gen, key, entry_size(path)))

    def _poll(self):
        changed = False
        try:
            while True:
                gen, key, size = self._results.get_nowait()
                if gen == self._gen:
                    self.set_size(key, size)
                    changed = True
        except queue.Empty:
            pass
        if changed:
            self._changed()
        self._poll_job = self.after(150, self._poll)

    def destroy(self):
        if self._poll_job:
            self.after_cancel(self._poll_job)
            self._poll_job = None
        self._gen += 1
        super().destroy()


class PasswordDialog(ctk.CTkToplevel):
    def __init__(self, master, title, message, error=None):
        super().__init__(master, fg_color=T.BG)
        self.title(title)
        self.geometry("380x210")
        self.resizable(False, False)
        self.transient(master.winfo_toplevel())
        self.result = None
        ctk.CTkLabel(self, text=message, font=T.font(14, "bold"), text_color=T.TEXT,
                     wraplength=340).pack(pady=(20, 6), padx=20)
        if error:
            ctk.CTkLabel(self, text=error, font=T.font(12), text_color=T.RED).pack()
        self.entry = ctk.CTkEntry(self, show="•", width=300, height=36, placeholder_text="Hasło")
        self.entry.pack(pady=10)
        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(pady=6)
        T.button(btns, "Anuluj", self.destroy, width=120).pack(side="left", padx=6)
        T.button(btns, "OK", self._ok, kind="primary", width=120).pack(side="left", padx=6)
        self.entry.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self.destroy())
        self.after(120, self._focus)

    def _focus(self):
        self.lift()
        self.focus_force()
        self.entry.focus_set()
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def _ok(self):
        self.result = self.entry.get()
        self.destroy()

    @classmethod
    def ask(cls, master, title, message, error=None):
        d = cls(master, title, message, error)
        master.wait_window(d)
        return d.result
