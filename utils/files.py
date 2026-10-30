"""Operacje na plikach: listowanie, rozmiary, drzewo do przesłania."""
import os


def entry_name(path):
    """Nazwa elementu; dla katalogu głównego dysku (np. D:\\) zwraca 'D'."""
    name = os.path.basename(os.path.normpath(path))
    return name or path.replace(":", "").strip("\\/") or "dysk"


def dir_size(path):
    total = 0
    stack = [path]
    while stack:
        p = stack.pop()
        try:
            with os.scandir(p) as it:
                for e in it:
                    try:
                        if e.is_symlink():
                            continue
                        if e.is_dir():
                            stack.append(e.path)
                        elif e.is_file():
                            total += e.stat().st_size
                    except OSError:
                        pass
        except OSError:
            pass
    return total


def entry_size(path):
    try:
        return dir_size(path) if os.path.isdir(path) else os.path.getsize(path)
    except OSError:
        return 0


def list_folder(folder):
    """Zwraca [(ścieżka, nazwa, is_dir)] – najpierw foldery, potem pliki."""
    out = []
    try:
        with os.scandir(folder) as it:
            for e in it:
                try:
                    out.append((os.path.normpath(e.path), e.name, e.is_dir()))
                except OSError:
                    pass
    except OSError:
        pass
    out.sort(key=lambda x: (not x[2], x[1].lower()))
    return out


def collect_tree(path):
    """Zwraca (nazwa, pliki, katalogi).

    Ścieżki względne zaczynają się od nazwy elementu i używają '/',
    np. 'Gra/data/a.pak' – dzięki temu klient odtwarza strukturę folderów.
    """
    name = entry_name(path)
    if not os.path.isdir(path):
        return name, [{"rel": name, "size": os.path.getsize(path)}], []
    files, dirs = [], [name]
    stack = [(path, name)]
    while stack:
        p, rel = stack.pop()
        try:
            entries = list(os.scandir(p))
        except OSError:
            continue
        for e in entries:
            r = f"{rel}/{e.name}"
            try:
                if e.is_symlink():
                    continue
                if e.is_dir():
                    dirs.append(r)
                    stack.append((e.path, r))
                elif e.is_file():
                    files.append({"rel": r, "size": e.stat().st_size})
            except OSError:
                pass
    files.sort(key=lambda f: f["rel"].lower())
    return name, files, dirs


def safe_rel_parts(rel):
    """Rozbija ścieżkę względną i odrzuca próby wyjścia poza folder."""
    parts = rel.split("/")
    for p in parts:
        if p in ("", ".", "..") or ":" in p or "\\" in p:
            raise ValueError(f"Niedozwolona ścieżka: {rel}")
    return parts
