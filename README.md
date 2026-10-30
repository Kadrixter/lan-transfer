# LAN Transfer

Prosta aplikacja do przesyłania plików i folderów w sieci lokalnej oraz przez Radmin VPN.
Jeden program obsługuje oba tryby: **Host** (udostępnia pliki) i **Klient** (pobiera).

## Pobierz

**[Pobierz LanTransfer.exe](https://github.com/Kadrixter/lan-transfer/releases/latest/download/LanTransfer.exe)** (Windows, nie wymaga instalacji)

Przy pierwszym uruchomieniu hosta Windows zapyta o zaporę – zezwól na dostęp (sieci prywatne), inaczej klienci nie znajdą hosta.

## Funkcje

**Host**
- wybór folderu, lista plików i folderów z rozmiarem (MB / GB) i polami do zaznaczenia
- dodawanie plików i folderów spoza wybranego folderu
- opcjonalne hasło (sprawdzane bez wysyłania hasła przez sieć)
- edycja hostowanych plików w trakcie hostowania
- lista połączonych klientów oraz postęp i prędkość (MB/s) każdego z nich

**Klient**
- automatyczne wyszukiwanie hostów w sieci lokalnej i w sieci Radmin VPN (oznaczone `[Radmin VPN host]`)
- informacja, że host jest chroniony hasłem
- połączenie ręczne po adresie IP
- pobieranie zaznaczonych elementów lub wszystkiego naraz, do wybranego folderu lub dysku
- animowany pasek postępu, prędkość, pozostały czas, status każdego pliku
- zachowanie struktury folderów
- wznawianie przerwanych pobrań (pliki `.part`), automatyczne ponawianie po zerwaniu połączenia

## Uruchomienie ze źródeł

Wymagany Python 3.10+.

```
pip install -r requirements.txt
python main.py
```

Budowanie pliku `.exe`: uruchom `build.bat` – wynik trafi do `dist\LanTransfer.exe`.

## Porty

| Port | Protokół | Zastosowanie |
|------|----------|--------------|
| 50505 | UDP | wyszukiwanie hostów |
| 50506 | TCP | przesyłanie plików (kolejny wolny, jeśli zajęty) |

## Struktura

```
main.py          start aplikacji
gui/             ekrany (start, host, klient), widgety, motyw
net/             protokół, wykrywanie hostów, serwer, klient
utils/           rozmiary plików, pomiar prędkości, interfejsy sieciowe / Radmin VPN
assets/          ikona i skrypt, który ją generuje
```

Uwaga: pliki przesyłane są bez szyfrowania – aplikacja jest przeznaczona do zaufanych sieci (LAN, Radmin VPN).
