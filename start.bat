@echo off
rem Startet Raumfeld Remote ohne Konsolenfenster (pythonw der virtuellen Umgebung).
cd /d "%~dp0"
if exist .venv\Scripts\pythonw.exe (
    start "" .venv\Scripts\pythonw.exe start.pyw
) else (
    start "" pythonw start.pyw
)
