@echo off
rem ==========================================================================
rem  start.bat - prueft alle Voraussetzungen, installiert Fehlendes nach und
rem  startet Raumfeld Remote ohne Konsolenfenster.
rem
rem  Geprueft wird:
rem    1. Python 3.10+ (Python-Launcher "py" oder "python")
rem    2. virtuelle Umgebung .venv im Programmordner
rem    3. Python-Pakete aus requirements.txt (customtkinter)
rem    4. yt-dlp.exe und ffmpeg.exe (Ordner "tools" oder PATH)
rem
rem  Terminalserver: Das Nachinstallieren schreibt in den Programmordner.
rem  Normale Benutzer duerfen das dort meist nicht -> start.bat EINMAL als
rem  Administrator ausfuehren; danach starten alle Benutzer ohne Installation.
rem  Python muss dafuer "fuer alle Benutzer" installiert sein.
rem ==========================================================================
setlocal
cd /d "%~dp0"
set "VENV_PY=.venv\Scripts\python.exe"
set "VENV_PYW=.venv\Scripts\pythonw.exe"

rem --------------------------------------------------------------------------
rem  Schneller Weg: alles vorhanden -> direkt starten, keine Konsole offen lassen
rem --------------------------------------------------------------------------
if not exist "%VENV_PYW%" goto pruefen
"%VENV_PY%" -c "import customtkinter" >nul 2>&1 || goto pruefen
call :programm_da yt-dlp || goto pruefen
call :programm_da ffmpeg || goto pruefen
goto starten

:pruefen
echo Raumfeld Remote - Voraussetzungen werden geprueft ...
echo.

rem ---------------------------------------------------- 1. Python + .venv
if exist "%VENV_PY%" goto pakete
call :python_suchen
if not defined PY (
    echo [Python] nicht gefunden - Installation ueber winget wird versucht ...
    where winget >nul 2>&1 || goto fehler_python
    rem --scope machine: Python fuer alle Benutzer (wichtig auf Terminalservern)
    winget install -e --id Python.Python.3.12 --scope machine --accept-package-agreements --accept-source-agreements
    call :python_suchen
)
if not defined PY goto fehler_python

rem Warnung, wenn Python nur im eigenen Benutzerprofil installiert ist:
rem andere Benutzer koennen die .venv dann nicht verwenden.
%PY% -c "import sys; print(sys.base_prefix)" | findstr /I /B /C:"%USERPROFILE%" >nul && (
    echo [Hinweis] Python ist nur fuer diesen Benutzer installiert.
    echo           Auf einem Terminalserver Python "fuer alle Benutzer" installieren.
    echo.
)

echo [Python] virtuelle Umgebung .venv wird angelegt ...
%PY% -m venv .venv || goto fehler_rechte

:pakete
rem ---------------------------------------------------- 2. Python-Pakete
"%VENV_PY%" -c "import customtkinter" >nul 2>&1 && goto werkzeuge
echo [Pakete] werden installiert ...
"%VENV_PY%" -m pip install --disable-pip-version-check -q -r requirements.txt || goto fehler_rechte

:werkzeuge
rem ---------------------------------------------------- 3. yt-dlp und ffmpeg
call :programm_da yt-dlp && goto ffmpeg_pruefen
echo [yt-dlp] wird in den Ordner "tools" heruntergeladen ...
if not exist tools mkdir tools || goto fehler_rechte
call :laden "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe" "tools\yt-dlp.exe" || goto fehler_download

:ffmpeg_pruefen
call :programm_da ffmpeg && goto fertig
echo [ffmpeg] wird in den Ordner "tools" heruntergeladen (ca. 200 MB, kann einige Minuten dauern) ...
if not exist tools mkdir tools || goto fehler_rechte
call :laden "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip" "%TEMP%\raumfeld_ffmpeg.zip" || goto fehler_download
echo [ffmpeg] wird entpackt ...
rem $ProgressPreference: Fortschrittsanzeige aus - macht Expand-Archive in PowerShell 5.1 deutlich schneller
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue';" ^
  "$zip = Join-Path $env:TEMP 'raumfeld_ffmpeg.zip'; $ziel = Join-Path $env:TEMP 'raumfeld_ffmpeg';" ^
  "if (Test-Path $ziel) { Remove-Item $ziel -Recurse -Force }; Expand-Archive $zip -DestinationPath $ziel;" ^
  "Get-ChildItem $ziel -Recurse -Include ffmpeg.exe,ffprobe.exe | Copy-Item -Destination 'tools';" ^
  "Remove-Item $zip, $ziel -Recurse -Force" ^
  || goto fehler_download

:fertig
echo.
echo Alles vorhanden - Raumfeld Remote wird gestartet.

:starten
call :firewall
start "" "%VENV_PYW%" start.pyw
exit /b 0

rem ==========================================================================
rem  Hilfsroutinen
rem ==========================================================================

:programm_da
rem Erfolg (errorlevel 0), wenn %1.exe im Ordner tools oder im PATH liegt
if exist "tools\%~1.exe" exit /b 0
where %~1 >nul 2>&1
exit /b %errorlevel%

:python_suchen
rem Setzt PY auf einen funktionierenden Python-Aufruf (3.10+), sonst leer.
rem "python" allein kann der Microsoft-Store-Platzhalter sein -> mit Testaufruf pruefen.
set "PY="
py -3 -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1 && set "PY=py -3" && exit /b 0
python -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1 && set "PY=python"
exit /b 0

:laden
rem Laedt %1 (URL) nach %2 (Datei). Bevorzugt curl.exe (ab Windows 10 enthalten):
rem schnell und mit Fortschrittsbalken. Sonst PowerShell OHNE Fortschrittsanzeige,
rem denn die bremst Invoke-WebRequest in PowerShell 5.1 extrem aus.
where curl.exe >nul 2>&1 && (
    curl.exe -L --fail --progress-bar -o "%~2" "%~1"
    exit /b
)
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol='Tls12';" ^
  "Invoke-WebRequest '%~1' -OutFile '%~2' -UseBasicParsing"
exit /b

rem ==========================================================================
rem  Fehlermeldungen (Fenster bleibt offen)
rem ==========================================================================

:fehler_python
echo.
echo FEHLER: Python 3.10 oder neuer wurde nicht gefunden und konnte nicht installiert werden.
echo Bitte von https://www.python.org installieren:
echo   - Haken bei "Add python.exe to PATH"
echo   - auf Terminalservern "Install for all users" waehlen
goto ende_fehler

:fehler_rechte
echo.
echo FEHLER: Installation im Programmordner nicht moeglich - fehlende Schreibrechte?
echo start.bat einmal per Rechtsklick "Als Administrator ausfuehren".
goto ende_fehler

:fehler_download
echo.
echo FEHLER: Download fehlgeschlagen - Internetverbindung oder Proxy pruefen.
echo Alternativ yt-dlp.exe und ffmpeg.exe von Hand in den Ordner "tools" legen.
goto ende_fehler

:ende_fehler
echo.
pause
exit /b 1
