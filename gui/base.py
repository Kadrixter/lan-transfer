import customtkinter as ctk

from gui import theme as T


class View(ctk.CTkFrame):
    """Bazowy ekran. cleanup() wywoływane przy przejściu do innego ekranu."""

    def __init__(self, app):
        super().__init__(app, fg_color=T.BG, corner_radius=0)
        self.app = app

    def cleanup(self):
        pass

    def header(self, title, subtitle="", back=None, back_text="← Wstecz"):
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=20, pady=(16, 8))
        if back:
            T.button(bar, back_text, back, width=100).pack(side="left", padx=(0, 14))
        box = ctk.CTkFrame(bar, fg_color="transparent")
        box.pack(side="left", fill="x", expand=True)
        self.title_lbl = ctk.CTkLabel(box, text=title, font=T.font(22, "bold"),
                                      text_color=T.TEXT, anchor="w")
        self.title_lbl.pack(fill="x")
        self.subtitle_lbl = ctk.CTkLabel(box, text=subtitle, font=T.font(12),
                                         text_color=T.MUTED, anchor="w")
        self.subtitle_lbl.pack(fill="x")
        return bar

    def section(self, master, title):
        """Nagłówek sekcji; zwraca (ramka nagłówka, etykieta)."""
        bar = ctk.CTkFrame(master, fg_color="transparent")
        bar.pack(fill="x", pady=(10, 4))
        lbl = ctk.CTkLabel(bar, text=title, font=T.font(15, "bold"), text_color=T.TEXT, anchor="w")
        lbl.pack(side="left")
        return bar, lbl
