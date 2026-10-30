"""LAN Transfer – hostowanie i pobieranie plików w sieci lokalnej / Radmin VPN."""
import sys

from gui.app import App

if __name__ == "__main__":
    if sys.platform == "win32":
        import ctypes
        # własny identyfikator – pasek zadań nie grupuje okna z Pythonem i bierze jego ikonę
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("LanTransfer.App")
    App().mainloop()
