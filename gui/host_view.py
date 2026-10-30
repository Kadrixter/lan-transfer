"""Tryb hosta: wybór plików -> hostowanie z listą klientów i postępem."""
import os
import socket
import threading
import time
from tkinter import filedialog

import customtkinter as ctk

from gui import theme as T
from gui.base import View
from gui.widgets import AnimatedProgressBar, SelectableList
from net.server import FileServer
from utils.files import entry_name, list_folder
from utils.fmt import fmt_size, fmt_speed
from utils.netinfo import interfaces


def _fill_candidates(lst, folder, extra, checked):
    """Wypełnia listę: zawartość folderu + elementy dodane spoza niego."""
    seen = set()
    if folder:
        for path, name, is_dir in list_folder(folder):
            lst.add(path, name, is_dir, checked=path in checked)
            lst.autosize(path, path)
            seen.add(path)
    for p in list(extra) + [p for p in checked if p not in extra]:
        if p in seen or not os.path.exists(p):
            continue
        lst.add(p, entry_name(p), os.path.isdir(p), checked=p in checked, badge="spoza folderu")
        lst.autosize(p, p)
        seen.add(p)


def _add_files(parent, lst, extra):
    for p in filedialog.askopenfilenames(parent=parent, title="Dodaj pliki"):
        p = os.path.normpath(p)
        if p not in lst.keys():
            extra.append(p)
            lst.add(p, entry_name(p), False, checked=True, badge="spoza folderu")
            lst.autosize(p, p)
    lst._changed()


def _add_folder(parent, lst, extra):
    p = filedialog.askdirectory(parent=parent, title="Dodaj folder")
    if p:
        p = os.path.normpath(p)
        if p not in lst.keys():
            extra.append(p)
            lst.add(p, entry_name(p), True, checked=True, badge="spoza folderu")
            lst.autosize(p, p)
        lst._changed()


class HostSetupView(View):
    def __init__(self, app, folder=None, extra=None, checked=None, name=None, password=""):
        super().__init__(app)
        self.folder = folder
        self.extra = list(extra or [])
        self.header("Tryb hosta", "Zaznacz pliki i foldery, które chcesz udostępnić", back=self._back)

        tools = ctk.CTkFrame(self, fg_color="transparent")
        tools.pack(fill="x", padx=20, pady=(0, 6))
        self.path_lbl = ctk.CTkLabel(tools, text="Nie wybrano folderu", text_color=T.MUTED,
                                     font=T.font(12), anchor="w")
        self.path_lbl.pack(side="left", fill="x", expand=True)
        T.button(tools, "Zaznacz wszystko", self._toggle_all, width=130).pack(side="right", padx=3)
        T.button(tools, "+ Folder", lambda: _add_folder(self, self.list, self.extra), width=90).pack(side="right", padx=3)
        T.button(tools, "+ Pliki", lambda: _add_files(self, self.list, self.extra), width=80).pack(side="right", padx=3)
        T.button(tools, "Zmień folder", self._choose_folder, width=110).pack(side="right", padx=3)

        self.list = SelectableList(self, on_change=self._update_footer)
        self.list.pack(fill="both", expand=True, padx=20, pady=4)

        foot = ctk.CTkFrame(self, fg_color=T.PANEL, corner_radius=10)
        foot.pack(fill="x", padx=20, pady=(6, 16))
        self.name_entry = ctk.CTkEntry(foot, width=180, height=36, placeholder_text="Nazwa hosta")
        self.name_entry.insert(0, name or socket.gethostname())
        self.name_entry.pack(side="left", padx=(12, 6), pady=12)
        self.pw_entry = ctk.CTkEntry(foot, width=180, height=36, show="•",
                                     placeholder_text="Hasło (opcjonalne)")
        if password:
            self.pw_entry.insert(0, password)
        self.pw_entry.pack(side="left", padx=6)
        self.summary = ctk.CTkLabel(foot, text="", text_color=T.MUTED, font=T.font(12))
        self.summary.pack(side="left", padx=10)
        self.host_btn = T.button(foot, "Hostuj  ▶", self._host, kind="primary", width=130, height=38)
        self._btn_visible = False

        if folder or self.extra:
            self._load(folder, set(checked or ()))
        else:
            self.list.set_empty_text("Wybierz folder z plikami do hostowania")
            self.after(200, self._choose_folder)

    def _back(self):
        from gui.start_view import StartView
        self.app.show(StartView)

    def _choose_folder(self):
        d = filedialog.askdirectory(parent=self, title="Wybierz folder z plikami do hostowania")
        if d:
            self._load(os.path.normpath(d), set(self.list.selected()))

    def _load(self, folder, checked):
        self.folder = folder
        self.path_lbl.configure(text=f"📂 {folder}" if folder else "Pliki spoza folderu")
        self.list.clear()
        _fill_candidates(self.list, folder, self.extra, checked)
        if not self.list.keys():
            self.list.set_empty_text("Folder jest pusty")
        self._update_footer()

    def _toggle_all(self):
        keys = self.list.keys()
        self.list.set_all(len(self.list.selected()) < len(keys))

    def _update_footer(self):
        sel = self.list.selected()
        if sel:
            size, complete = self.list.size_of(sel)
            self.summary.configure(text=f"Zaznaczono: {len(sel)}  •  {fmt_size(size)}" + ("" if complete else " +"))
            if not self._btn_visible:
                self.host_btn.pack(side="right", padx=12)
                self._btn_visible = True
        else:
            self.summary.configure(text="Nic nie zaznaczono")
            if self._btn_visible:
                self.host_btn.pack_forget()
                self._btn_visible = False

    def _host(self):
        paths = self.list.selected()
        if not paths:
            return
        self.app.show(HostRunView, paths=paths, folder=self.folder, extra=self.extra,
                      name=self.name_entry.get().strip() or socket.gethostname(),
                      password=self.pw_entry.get())


class EditSharesDialog(ctk.CTkToplevel):
    """✎ Edycja hostowanych elementów w trakcie hostowania."""

    def __init__(self, master, folder, extra, checked, on_save):
        super().__init__(master, fg_color=T.BG)
        self.title("Edytuj hostowane pliki")
        self.geometry("680x520")
        self.transient(master.winfo_toplevel())
        self.on_save = on_save
        self.extra = list(extra)

        ctk.CTkLabel(self, text="Zaznacz, co ma być hostowane", font=T.font(16, "bold"),
                     text_color=T.TEXT).pack(anchor="w", padx=16, pady=(14, 4))
        tools = ctk.CTkFrame(self, fg_color="transparent")
        tools.pack(fill="x", padx=16)
        T.button(tools, "+ Pliki", lambda: _add_files(self, self.list, self.extra), width=80).pack(side="left", padx=(0, 6))
        T.button(tools, "+ Folder", lambda: _add_folder(self, self.list, self.extra), width=90).pack(side="left")

        self.list = SelectableList(self)
        self.list.pack(fill="both", expand=True, padx=16, pady=8)
        _fill_candidates(self.list, folder, self.extra, set(checked))

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=16, pady=(0, 14))
        T.button(btns, "Zapisz", self._save, kind="primary", width=120).pack(side="right", padx=4)
        T.button(btns, "Anuluj", self.destroy, width=120).pack(side="right", padx=4)
        self.after(150, self._focus)

    def _focus(self):
        self.lift()
        self.focus_force()

    def _save(self):
        sel = self.list.selected()
        if not sel:
            return
        self.on_save(sel, self.extra)
        self.destroy()


class HostRunView(View):
    def __init__(self, app, paths, folder, extra, name, password):
        super().__init__(app)
        self.paths = list(paths)
        self.folder = folder
        self.extra = list(extra)
        self.name = name
        self.password = password
        self.server = FileServer(name, password)
        self._state = "starting"  # starting | running -> running_shown | error -> error_shown
        self._error = None
        self._items_dirty = False
        self._client_rows = {}
        self._transfer_rows = {}
        self._poll_job = None

        bar = self.header("Hostowanie", "Uruchamianie…")
        T.button(bar, "■  Zatrzymaj hosting", self._stop, kind="danger", width=170).pack(side="right")

        info = ctk.CTkFrame(self, fg_color=T.PANEL, corner_radius=10)
        info.pack(fill="x", padx=20, pady=(0, 4))
        self.status_lbl = ctk.CTkLabel(info, text="●  Przygotowuję listę plików…", font=T.font(14, "bold"),
                                       text_color=T.YELLOW, anchor="w")
        self.status_lbl.pack(fill="x", padx=14, pady=(10, 0))
        self.addr_lbl = ctk.CTkLabel(info, text="", font=T.font(12), text_color=T.MUTED,
                                     anchor="w", justify="left")
        self.addr_lbl.pack(fill="x", padx=14, pady=(2, 10))

        # siatka: listy dzielą wolne miejsce w proporcji 2 : 1 : 3
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=(0, 14))
        body.grid_columnconfigure(0, weight=1)
        for row, weight in ((1, 2), (3, 1), (5, 3)):
            body.grid_rowconfigure(row, weight=weight, uniform="lists")

        bar, _ = self._grid_section(body, 0, "Hostowane pliki")
        T.button(bar, "✎ Edytuj", self._edit, width=90, height=28).pack(side="left", padx=10)
        self.files_lbl = ctk.CTkLabel(bar, text="", font=T.font(12), text_color=T.MUTED)
        self.files_lbl.pack(side="right")
        self.files_box = ctk.CTkScrollableFrame(body, fg_color=T.PANEL, corner_radius=10, height=40)
        self.files_box.grid(row=1, column=0, sticky="nsew")

        _, self.clients_title = self._grid_section(body, 2, "Połączeni klienci (0)")
        self.clients_box = ctk.CTkScrollableFrame(body, fg_color=T.PANEL, corner_radius=10, height=40)
        self.clients_box.grid(row=3, column=0, sticky="nsew")
        self.no_clients = ctk.CTkLabel(self.clients_box, text="Czekam na klientów…", text_color=T.MUTED)
        self.no_clients.pack(pady=10)

        self._grid_section(body, 4, "Postęp pobierania")
        self.transfer_box = ctk.CTkScrollableFrame(body, fg_color=T.PANEL, corner_radius=10, height=40)
        self.transfer_box.grid(row=5, column=0, sticky="nsew")
        self.no_transfers = ctk.CTkLabel(self.transfer_box, text="Nikt jeszcze nie pobiera", text_color=T.MUTED)
        self.no_transfers.pack(pady=10)

        threading.Thread(target=self._start_server, daemon=True).start()
        self._poll()

    def _grid_section(self, master, row, title):
        bar = ctk.CTkFrame(master, fg_color="transparent")
        bar.grid(row=row, column=0, sticky="ew", pady=(10, 4))
        lbl = ctk.CTkLabel(bar, text=title, font=T.font(15, "bold"), text_color=T.TEXT, anchor="w")
        lbl.pack(side="left")
        return bar, lbl

    # ----- serwer -----

    def _start_server(self):
        try:
            self.server.set_items(self.paths)
            self.server.start()
            self._items_dirty = True
            self._state = "running"
        except Exception as e:
            self._error = str(e)
            self._state = "error"

    def _show_running(self):
        lines = []
        for i in interfaces():
            tag = "   [Radmin VPN]" if i["radmin"] and "radmin" not in i["name"].lower() else ""
            lines.append(f"{i['ip']}:{self.server.port}   ({T.shorten(i['name'], 40)}){tag}")
        pw = "z hasłem 🔒" if self.server.protected else "bez hasła"
        self.subtitle_lbl.configure(text=f"Host „{self.name}”  •  {pw}")
        warn = f"\n⚠ {self.server.discovery_error} – klienci mogą połączyć się ręcznie po IP" \
            if self.server.discovery_error else ""
        self.addr_lbl.configure(text="Adresy: " + ("\n             ".join(lines) or "brak sieci") + warn)
        self.status_lbl.configure(text="●  Hostowanie aktywne", text_color=T.GREEN)

    def _refresh_files(self):
        for w in self.files_box.winfo_children():
            w.destroy()
        items = self.server.items_public()
        for it in items:
            row = ctk.CTkFrame(self.files_box, fg_color=T.ROW, corner_radius=8)
            row.pack(fill="x", padx=6, pady=2)
            ctk.CTkLabel(row, text=("📁 " if it["is_dir"] else "📄 ") + T.shorten(it["name"], 70),
                         anchor="w", text_color=T.TEXT).pack(side="left", padx=10, pady=4)
            extra = f"{len(it['files'])} plików  •  " if it["is_dir"] else ""
            ctk.CTkLabel(row, text=extra + fmt_size(it["size"]), text_color=T.MUTED,
                         font=T.font(12)).pack(side="right", padx=12)
        total = sum(i["size"] for i in items)
        self.files_lbl.configure(text=f"{len(items)} elementów  •  {fmt_size(total)}")

    def _edit(self):
        if self._state != "running_shown":
            return
        EditSharesDialog(self, self.folder, self.extra, self.paths, self._apply_edit)

    def _apply_edit(self, paths, extra):
        self.paths = list(paths)
        self.extra = list(extra)
        self.files_lbl.configure(text="Aktualizuję listę…")

        def work():
            self.server.set_items(self.paths)
            self._items_dirty = True
        threading.Thread(target=work, daemon=True).start()

    # ----- odświeżanie -----

    def _poll(self):
        if self._state == "running":
            self._show_running()
            self._state = "running_shown"
        elif self._state == "error":
            self.status_lbl.configure(text=f"●  Błąd: {self._error}", text_color=T.RED)
            self._state = "error_shown"
        if self._items_dirty:
            self._items_dirty = False
            self._refresh_files()

        snap = self.server.snapshot()
        self._sync_clients(snap)
        self._sync_transfers([s for s in snap if s["total"] or s["state"] != "przegląda pliki"])
        self._poll_job = self.after(250, self._poll)

    def _sync_clients(self, snap):
        ids = {s["id"] for s in snap}
        for sid in list(self._client_rows):
            if sid not in ids:
                self._client_rows.pop(sid)["frame"].destroy()
        for s in snap:
            r = self._client_rows.get(s["id"])
            if not r:
                frame = ctk.CTkFrame(self.clients_box, fg_color=T.ROW, corner_radius=8)
                frame.pack(fill="x", padx=6, pady=2)
                ctk.CTkLabel(frame, text=f"💻  {s['name']}", text_color=T.TEXT,
                             font=T.font(13, "bold")).pack(side="left", padx=10, pady=4)
                ctk.CTkLabel(frame, text=s["ip"], text_color=T.MUTED, font=T.font(12)).pack(side="left", padx=6)
                ctk.CTkLabel(frame, text="od " + time.strftime("%H:%M", time.localtime(s["connected_at"])),
                             text_color=T.MUTED, font=T.font(12)).pack(side="left", padx=6)
                state = ctk.CTkLabel(frame, text="", font=T.font(12))
                state.pack(side="right", padx=12)
                r = self._client_rows[s["id"]] = {"frame": frame, "state": state}
            color = T.ACCENT if s["state"] == "pobiera" else T.GREEN if s["state"].startswith("zakończ") else T.MUTED
            r["state"].configure(text=s["state"], text_color=color)
        self.clients_title.configure(text=f"Połączeni klienci ({len(snap)})")
        if snap:
            self.no_clients.pack_forget()
        else:
            self.no_clients.pack(pady=10)

    def _sync_transfers(self, snap):
        ids = {s["id"] for s in snap}
        for sid in list(self._transfer_rows):
            if sid not in ids:
                self._transfer_rows.pop(sid)["frame"].destroy()
        for s in snap:
            r = self._transfer_rows.get(s["id"])
            if not r:
                frame = ctk.CTkFrame(self.transfer_box, fg_color=T.ROW, corner_radius=8)
                frame.pack(fill="x", padx=6, pady=3)
                top = ctk.CTkFrame(frame, fg_color="transparent")
                top.pack(fill="x", padx=12, pady=(8, 2))
                ctk.CTkLabel(top, text=f"💻  {s['name']}", font=T.font(13, "bold"),
                             text_color=T.TEXT).pack(side="left")
                speed = ctk.CTkLabel(top, text="", font=T.font(13, "bold"), text_color=T.ACCENT)
                speed.pack(side="right")
                bar = AnimatedProgressBar(frame, height=12, bg=T.ROW)
                bar.pack(fill="x", padx=12, pady=4)
                info = ctk.CTkLabel(frame, text="", font=T.font(11), text_color=T.MUTED, anchor="w")
                info.pack(fill="x", padx=12, pady=(0, 8))
                r = self._transfer_rows[s["id"]] = {"frame": frame, "bar": bar, "speed": speed, "info": info}
            total = s["total"]
            frac = s["sent"] / total if total else (1.0 if s["state"].startswith("zakończ") else 0.0)
            r["bar"].set(frac)
            done = s["state"].startswith("zakończ")
            r["bar"].set_color(T.GREEN if done else None)
            r["speed"].configure(text="✔ gotowe" if done else fmt_speed(s["speed"]),
                                 text_color=T.GREEN if done else T.ACCENT)
            cur = f"  •  {T.shorten(s['current'], 60)}" if s["current"] else ""
            r["info"].configure(text=f"{fmt_size(s['sent'])} / {fmt_size(total)}  ({frac * 100:.0f}%){cur}")
        if snap:
            self.no_transfers.pack_forget()
        else:
            self.no_transfers.pack(pady=10)

    def _stop(self):
        self.app.show(HostSetupView, folder=self.folder, extra=self.extra, checked=set(self.paths),
                      name=self.name, password=self.password)

    def cleanup(self):
        if self._poll_job:
            self.after_cancel(self._poll_job)
        self.server.stop()
