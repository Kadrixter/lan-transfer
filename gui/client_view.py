"""Tryb klienta: lista hostów -> lista plików -> pobieranie."""
import math
import os
import threading
from tkinter import filedialog

import customtkinter as ctk

from gui import theme as T
from gui.base import View
from gui.widgets import AnimatedProgressBar, PasswordDialog, SelectableList
from net.client import AuthError, DownloadJob, HostConnection, PasswordRequired
from net.discovery import DiscoveryScanner
from net.protocol import TCP_PORT
from utils.fmt import fmt_eta, fmt_size, fmt_speed
from utils.netinfo import is_radmin_ip, radmin_available

MAX_FILE_ROWS = 300


def _badges(master, host):
    if host.get("radmin"):
        ctk.CTkLabel(master, text="[Radmin VPN host]", font=T.font(12, "bold"),
                     text_color=T.ORANGE).pack(side="left", padx=6)
    if host.get("protected"):
        ctk.CTkLabel(master, text="[🔒 z hasłem]", font=T.font(12, "bold"),
                     text_color=T.YELLOW).pack(side="left", padx=6)


class ClientServersView(View):
    def __init__(self, app):
        super().__init__(app)
        self.header("Tryb klienta", "Wyszukiwanie hostów w sieci lokalnej", back=self._back)
        self._busy = False
        self._sig = None
        self._dots = 0

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=20)
        self.status = ctk.CTkLabel(top, text="Szukam hostów", font=T.font(14, "bold"),
                                   text_color=T.ACCENT, anchor="w")
        self.status.pack(side="left")
        rad = radmin_available()
        ctk.CTkLabel(top, text="Radmin VPN: wykryto – szukam też w sieci Radmin" if rad
                     else "Radmin VPN: nie wykryto", font=T.font(12),
                     text_color=T.ORANGE if rad else T.MUTED).pack(side="right")

        self.box = ctk.CTkScrollableFrame(self, fg_color=T.PANEL, corner_radius=10)
        self.box.pack(fill="both", expand=True, padx=20, pady=8)
        self.empty = ctk.CTkLabel(self.box, text="Nie znaleziono jeszcze żadnego hosta…\n"
                                  "Upewnij się, że host działa i zapora Windows go nie blokuje.",
                                  text_color=T.MUTED, font=T.font(13))
        self.empty.pack(pady=40)

        foot = ctk.CTkFrame(self, fg_color=T.PANEL, corner_radius=10)
        foot.pack(fill="x", padx=20, pady=(0, 16))
        ctk.CTkLabel(foot, text="Nie widzisz hosta? Połącz po IP:", text_color=T.MUTED,
                     font=T.font(12)).pack(side="left", padx=(12, 6), pady=12)
        self.ip_entry = ctk.CTkEntry(foot, width=200, height=34, placeholder_text="np. 26.10.20.30")
        self.ip_entry.pack(side="left", padx=6)
        self.ip_entry.bind("<Return>", lambda e: self._manual())
        T.button(foot, "Połącz", self._manual, kind="primary", width=100).pack(side="left", padx=6)

        self.scanner = DiscoveryScanner()
        self.scanner.start()
        self._poll_job = None
        self._poll()

    def _back(self):
        from gui.start_view import StartView
        self.app.show(StartView)

    def _poll(self):
        if not self._busy:
            self._dots = (self._dots + 1) % 4
            self.status.configure(text="Szukam hostów" + "." * self._dots, text_color=T.ACCENT)
        hosts = self.scanner.get_hosts()
        sig = tuple((h["key"], h["name"], h["ip"], h["port"], h["protected"]) for h in hosts)
        if sig != self._sig:
            self._sig = sig
            self._render(hosts)
        self._poll_job = self.after(500, self._poll)

    def _render(self, hosts):
        for w in self.box.winfo_children():
            if w is not self.empty:
                w.destroy()
        if not hosts:
            self.empty.pack(pady=40)
            return
        self.empty.pack_forget()
        for h in hosts:
            card = ctk.CTkFrame(self.box, fg_color=T.ROW, corner_radius=10)
            card.pack(fill="x", padx=6, pady=4)
            line = ctk.CTkFrame(card, fg_color="transparent")
            line.pack(side="left", fill="x", expand=True, padx=12, pady=10)
            name = ctk.CTkLabel(line, text=f"🖥  {h['name']}", font=T.font(15, "bold"), text_color=T.TEXT)
            name.pack(side="left")
            _badges(line, h)
            addr = ctk.CTkLabel(line, text=f"{h['ip']}:{h['port']}", font=T.font(12), text_color=T.MUTED)
            addr.pack(side="left", padx=10)
            T.button(card, "Połącz  →", lambda h=h: self._connect(h), kind="primary",
                     width=110).pack(side="right", padx=12)
            for w in (card, line, name, addr):
                w.bind("<Button-1>", lambda e, h=h: self._connect(h))

    def _manual(self):
        text = self.ip_entry.get().strip()
        if not text:
            return
        ip, _, port = text.partition(":")
        try:
            port = int(port) if port else TCP_PORT
        except ValueError:
            self.status.configure(text="Nieprawidłowy port", text_color=T.RED)
            return
        self.scanner.add_manual(ip)
        self._connect({"name": ip, "ip": ip, "port": port, "protected": False,
                       "radmin": is_radmin_ip(ip)})

    def _connect(self, host, password=None, error=None):
        if self._busy:
            return
        self._busy = True
        self.status.configure(text=f"Łączenie z {host['name']}…", text_color=T.YELLOW)
        result = {}

        def work():
            try:
                conn = HostConnection(host["ip"], host["port"], password)
                result["ok"] = (conn, conn.list_items())
            except PasswordRequired:
                result["pw"] = True
            except AuthError as e:
                result["auth"] = str(e)
            except (OSError, ValueError) as e:
                result["err"] = str(e) or e.__class__.__name__

        def wait():
            if not result:
                self.after(100, wait)
                return
            self._busy = False
            if "ok" in result:
                conn, items = result["ok"]
                host["name"] = conn.host_name or host["name"]
                host["protected"] = conn.protected
                self.app.show(ClientFilesView, conn=conn, host=host, items=items)
            elif "pw" in result or "auth" in result:
                pw = PasswordDialog.ask(self, "Hasło", f"Host „{host['name']}” wymaga hasła",
                                        error=result.get("auth"))
                if pw is not None:
                    self._connect(host, pw)
            else:
                self.status.configure(text=f"Nie udało się połączyć: {result['err']}", text_color=T.RED)

        threading.Thread(target=work, daemon=True).start()
        wait()

    def cleanup(self):
        if self._poll_job:
            self.after_cancel(self._poll_job)
        self.scanner.stop()


class ClientFilesView(View):
    def __init__(self, app, conn, host, items=None):
        super().__init__(app)
        self.conn = conn
        self.host = host
        self.items = {}
        bar = self.header(f"Pliki hosta „{host['name']}”", f"{host['ip']}:{host['port']}", back=self._back)
        badges = ctk.CTkFrame(bar, fg_color="transparent")
        badges.pack(side="right")
        _badges(badges, host)
        if not host.get("protected"):
            ctk.CTkLabel(badges, text="[bez hasła]", font=T.font(12), text_color=T.MUTED).pack(side="left", padx=6)

        tools = ctk.CTkFrame(self, fg_color="transparent")
        tools.pack(fill="x", padx=20, pady=(0, 4))
        self.info = ctk.CTkLabel(tools, text="", font=T.font(12), text_color=T.MUTED, anchor="w")
        self.info.pack(side="left")
        T.button(tools, "⟳ Odśwież", self._reload, width=100).pack(side="right", padx=3)
        T.button(tools, "Zaznacz wszystko", self._toggle_all, width=130).pack(side="right", padx=3)

        self.list = SelectableList(self, on_change=self._update)
        self.list.pack(fill="both", expand=True, padx=20, pady=4)

        foot = ctk.CTkFrame(self, fg_color=T.PANEL, corner_radius=10)
        foot.pack(fill="x", padx=20, pady=(6, 16))
        self.summary = ctk.CTkLabel(foot, text="", font=T.font(13), text_color=T.TEXT)
        self.summary.pack(side="left", padx=14, pady=12)
        self.dl_btn = T.button(foot, "⬇  Pobierz wszystko", self._download, kind="primary",
                               width=190, height=40)
        self.dl_btn.pack(side="right", padx=12, pady=10)

        if items is None:
            self._reload()
        else:
            self._fill(items)

    def _back(self):
        self.conn.close()
        self.app.show(ClientServersView)

    def _reload(self):
        self.list.clear("Wczytuję listę plików…")
        result = {}

        def work():
            try:
                if self.conn.sock is None:
                    self.conn.connect()
                result["items"] = self.conn.list_items()
            except Exception as e:
                self.conn.close()
                result["err"] = str(e) or e.__class__.__name__

        def wait():
            if not result:
                self.after(100, wait)
            elif "items" in result:
                self._fill(result["items"])
            else:
                self.list.clear(f"Nie udało się pobrać listy: {result['err']}")

        threading.Thread(target=work, daemon=True).start()
        wait()

    def _fill(self, items):
        self.items = {it["id"]: it for it in items}
        self.list.clear("Host nie udostępnia żadnych plików" if not items else "")
        for it in items:
            self.list.add(it["id"], it["name"], it["is_dir"], size=it["size"])
        n_files = sum(len(it["files"]) for it in items)
        self.info.configure(text=f"{len(items)} elementów  •  {n_files} plików  •  "
                                 f"{fmt_size(sum(it['size'] for it in items))}")
        self._update()

    def _toggle_all(self):
        self.list.set_all(len(self.list.selected()) < len(self.list.keys()))

    def _update(self):
        sel = self.list.selected()
        if sel:
            size, _ = self.list.size_of(sel)
            self.dl_btn.configure(text=f"⬇  Pobierz ({len(sel)})")
            self.summary.configure(text=f"Zaznaczono {len(sel)}  •  {fmt_size(size)}")
        else:
            size, _ = self.list.size_of(self.list.keys())
            self.dl_btn.configure(text="⬇  Pobierz wszystko")
            self.summary.configure(text=f"Wszystko  •  {fmt_size(size)}")

    def _download(self):
        keys = self.list.selected() or self.list.keys()
        items = [self.items[k] for k in keys if k in self.items]
        if not items:
            return
        dest = filedialog.askdirectory(parent=self, title="Wybierz folder lub dysk, do którego pobrać pliki")
        if not dest:
            return
        self.app.show(ClientDownloadView, conn=self.conn, host=self.host, items=items,
                      dest=os.path.normpath(dest))


class ClientDownloadView(View):
    STATUS_COLORS = {"gotowe": T.GREEN, "już jest": T.GREEN, "pobieranie": T.ACCENT,
                     "błąd": T.RED, "ponawiam…": T.YELLOW}

    def __init__(self, app, conn, host, items, dest, intro=True):
        super().__init__(app)
        self.conn = conn
        self.host = host
        self.items = items
        self.dest = dest
        self.job = DownloadJob(conn, items, dest)
        self.job.start()
        self._poll_job = None
        self._anim_job = None
        self._intro_job = None
        self._done_shown = False
        if intro:
            self._show_intro()
        else:
            self._show_main()

    # ----- animacja „Pobieram X…” (3 s) -----

    def _show_intro(self):
        self.intro = ctk.CTkFrame(self, fg_color="transparent")
        self.intro.place(relx=0.5, rely=0.5, anchor="center")
        self.intro_lbl = ctk.CTkLabel(self.intro, text="", font=T.font(28, "bold"), text_color=T.TEXT)
        self.intro_lbl.pack()
        n = len(self.job.files)
        ctk.CTkLabel(self.intro, text=f"{n} plików z „{self.host['name']}”", font=T.font(13),
                     text_color=T.MUTED).pack(pady=(6, 18))
        self.intro_bar = AnimatedProgressBar(self.intro, height=10, bg=T.BG, width=380)
        self.intro_bar.set_indeterminate()
        self.intro_bar.pack()
        self._anim_t = 0
        self._animate_intro()
        self._intro_job = self.after(3000, self._show_main)

    def _animate_intro(self):
        self._anim_t += 1
        t = self._anim_t
        dots = "." * (t // 6 % 4)
        pulse = (1 + math.sin(t / 4)) / 2
        self.intro_lbl.configure(text=f"Pobieram {fmt_size(self.job.total)} plików{dots}",
                                 text_color=T.lerp_color(T.TEXT, T.ACCENT, pulse))
        self._anim_job = self.after(50, self._animate_intro)

    # ----- główny widok pobierania -----

    def _show_main(self):
        self._intro_job = None
        if self._anim_job:
            self.after_cancel(self._anim_job)
            self._anim_job = None
        if hasattr(self, "intro"):
            self.intro.destroy()

        self.header(f"Pobieranie z „{self.host['name']}”", f"Do: {self.dest}")
        card = ctk.CTkFrame(self, fg_color=T.PANEL, corner_radius=12)
        card.pack(fill="x", padx=20, pady=(0, 8))
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(14, 4))
        self.pct_lbl = ctk.CTkLabel(top, text="0%", font=T.font(26, "bold"), text_color=T.TEXT)
        self.pct_lbl.pack(side="left")
        self.speed_lbl = ctk.CTkLabel(top, text="", font=T.font(20, "bold"), text_color=T.ACCENT)
        self.speed_lbl.pack(side="right")
        self.bar = AnimatedProgressBar(card, height=18, bg=T.PANEL)
        self.bar.pack(fill="x", padx=16, pady=6)
        self.stats_lbl = ctk.CTkLabel(card, text="", font=T.font(12), text_color=T.MUTED, anchor="w")
        self.stats_lbl.pack(fill="x", padx=16)
        self.cur_lbl = ctk.CTkLabel(card, text="", font=T.font(12), text_color=T.TEXT, anchor="w")
        self.cur_lbl.pack(fill="x", padx=16, pady=(8, 2))
        self.cur_bar = AnimatedProgressBar(card, height=6, bg=T.PANEL)
        self.cur_bar.pack(fill="x", padx=16, pady=(0, 14))

        self.files_box = ctk.CTkScrollableFrame(self, fg_color=T.PANEL, corner_radius=10)
        self.files_box.pack(fill="both", expand=True, padx=20, pady=4)
        self._rows = []
        for f in self.job.files[:MAX_FILE_ROWS]:
            row = ctk.CTkFrame(self.files_box, fg_color=T.ROW, corner_radius=6)
            row.pack(fill="x", padx=4, pady=1)
            ctk.CTkLabel(row, text=T.shorten(f.rel, 80), anchor="w", font=T.font(12),
                         text_color=T.TEXT).pack(side="left", padx=10, pady=2)
            st = ctk.CTkLabel(row, text="", width=110, anchor="e", font=T.font(12))
            st.pack(side="right", padx=10)
            ctk.CTkLabel(row, text=fmt_size(f.size), width=90, anchor="e", font=T.font(12),
                         text_color=T.MUTED).pack(side="right")
            self._rows.append((f, st, [None]))
        if len(self.job.files) > MAX_FILE_ROWS:
            ctk.CTkLabel(self.files_box, text=f"… i jeszcze {len(self.job.files) - MAX_FILE_ROWS} plików",
                         text_color=T.MUTED).pack(pady=6)

        self.foot = ctk.CTkFrame(self, fg_color="transparent")
        self.foot.pack(fill="x", padx=20, pady=(4, 16))
        self.result_lbl = ctk.CTkLabel(self.foot, text="", font=T.font(13, "bold"), anchor="w",
                                       justify="left")
        self.result_lbl.pack(side="left")
        self.cancel_btn = T.button(self.foot, "Anuluj", self._cancel, kind="danger", width=120)
        self.cancel_btn.pack(side="right")
        self._poll()

    def _poll(self):
        job = self.job
        total, done = job.total, job.done_bytes
        frac = done / total if total else (1.0 if job.finished else 0.0)
        speed = job.meter.speed()
        self.bar.set(frac)
        self.pct_lbl.configure(text=f"{frac * 100:.1f}%")
        self.speed_lbl.configure(text=fmt_speed(speed))
        eta = (total - done) / speed if speed > 1 else None
        self.stats_lbl.configure(text=f"{fmt_size(done)} / {fmt_size(total)}   •   pozostało: {fmt_eta(eta)}")
        cur = job.current
        if cur:
            self.cur_lbl.configure(text=f"⬇  {T.shorten(cur.rel, 90)}")
            self.cur_bar.set(cur.done / cur.size if cur.size else 1.0)
        for f, lbl, last in self._rows:
            status = f.status
            if status == "pobieranie" and f.size:
                status = f"{f.done / f.size * 100:.0f}%"
            if status != last[0]:
                last[0] = status
                color = self.STATUS_COLORS.get(f.status, T.MUTED)
                lbl.configure(text=("✔ " if f.status in ("gotowe", "już jest") else "") + status,
                              text_color=color)

        if job.finished:
            self._finish()
        else:
            self._poll_job = self.after(200, self._poll)

    def _finish(self):
        if self._done_shown:
            return
        self._done_shown = True
        job = self.job
        self.cancel_btn.destroy()
        self.speed_lbl.configure(text="")
        self.cur_lbl.configure(text="")
        self.cur_bar.pack_forget()
        if job.error or job.cancelled:
            msg = "Anulowano" if job.cancelled else f"Błąd: {job.error}"
            self.result_lbl.configure(text=f"{msg}\nPostęp jest zapisany – „Wznów” dokończy pobieranie.",
                                      text_color=T.RED if job.error else T.YELLOW)
            self.bar.set_color(T.RED if job.error else T.YELLOW)
            T.button(self.foot, "↻ Wznów", self._resume, kind="primary", width=120).pack(side="right", padx=4)
        else:
            self.bar.set(1.0)
            self.bar.set_color(T.GREEN)
            self.pct_lbl.configure(text="100%", text_color=T.GREEN)
            extra = f"  ({job.failed} plików z błędem)" if job.failed else ""
            self.result_lbl.configure(text="✔ Pobieranie zakończone" + extra,
                                      text_color=T.YELLOW if job.failed else T.GREEN)
            T.button(self.foot, "📂 Otwórz folder", self._open, kind="success", width=150).pack(side="right", padx=4)
        T.button(self.foot, "← Lista plików", self._back, width=130).pack(side="right", padx=4)

    def _cancel(self):
        self.cancel_btn.configure(state="disabled", text="Anulowanie…")
        self.job.cancel()

    def _resume(self):
        self.app.show(ClientDownloadView, conn=self.conn, host=self.host, items=self.items,
                      dest=self.dest, intro=False)

    def _open(self):
        try:
            os.startfile(self.dest)
        except OSError:
            pass

    def _back(self):
        self.app.show(ClientFilesView, conn=self.conn, host=self.host)

    def cleanup(self):
        for job_id in (self._poll_job, self._anim_job, self._intro_job):
            if job_id:
                self.after_cancel(job_id)
        if not self.job.finished:
            self.job.cancel()
