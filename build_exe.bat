@echo off
rem Optional: baut eine einzelne .exe (PyInstaller). Ungetestet - siehe README.
cd /d "%~dp0"
call .venv\Scripts\activate.bat
pip install pyinstaller
pyinstaller --noconsole --onefile --name RaumfeldRemote --collect-all customtkinter start.pyw
echo.
echo Ergebnis: dist\RaumfeldRemote.exe
echo ffmpeg.exe und yt-dlp.exe in den Ordner "tools" neben die .exe legen (oder im PATH haben).
pause
