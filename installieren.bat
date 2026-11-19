@echo off
rem Richtet eine virtuelle Python-Umgebung ein und installiert die Abhaengigkeiten.
rem Voraussetzung: Python 3.10+ (https://www.python.org, Haken bei "Add to PATH").
cd /d "%~dp0"
rem Bevorzugt den Python-Launcher "py" (Standard bei python.org-Installation),
rem sonst "python" aus dem PATH (kann auch der Microsoft-Store-Platzhalter sein).
set "PY=python"
where py >nul 2>&1 && set "PY=py -3"
%PY% -m venv .venv || (echo Python wurde nicht gefunden. & pause & exit /b 1)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
echo.
echo Fertig. Jetzt noch yt-dlp und ffmpeg installieren (falls noch nicht vorhanden):
echo   winget install yt-dlp.yt-dlp
echo   winget install Gyan.FFmpeg
echo Danach "start.bat" ausfuehren.
pause
