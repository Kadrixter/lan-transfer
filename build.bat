@echo off
rem Buduje dist\LanTransfer.exe (jeden plik, bez konsoli)
cd /d "%~dp0"
python -m pip install -r requirements.txt
python -m PyInstaller --noconfirm --clean --onefile --windowed --name LanTransfer --collect-data customtkinter ^
    --icon assets\icon.ico --add-data "assets\icon.ico;assets" main.py
echo.
echo Gotowe: dist\LanTransfer.exe
pause
