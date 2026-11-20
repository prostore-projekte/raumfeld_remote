# -*- coding: utf-8 -*-
"""
dienst.py - Startpunkt des zentralen Dienstes (Web-Oberflaeche fuer alle Benutzer).

Aufruf:
    RaumfeldRemoteDienst.exe [--port 8080] [--daten C:\\ProgramData\\RaumfeldRemote]
    python -m raumfeld_remote.dienst

Unter Windows wird dieses Programm vom Installer als Windows-Dienst
eingerichtet (WinSW) und laeuft dann dauerhaft im Hintergrund als SYSTEM.
Alle Daten (Einstellungen, Passwort-Hash, cookies.txt, Protokoll) liegen im
Datenordner, standardmaessig C:\\ProgramData\\RaumfeldRemote.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path


def standard_datenordner() -> Path:
    """%PROGRAMDATA%\\RaumfeldRemote unter Windows, sonst ~/.local/share/raumfeld_remote."""
    programdata = os.environ.get("PROGRAMDATA")
    if programdata:
        return Path(programdata) / "RaumfeldRemote"
    return Path.home() / ".local" / "share" / "raumfeld_remote"


def main() -> None:
    parser = argparse.ArgumentParser(description="Raumfeld Remote – zentraler Dienst mit Web-Oberfläche")
    parser.add_argument("--port", type=int, help="Port der Web-Oberfläche (Standard: aus dienst.json, sonst 8080)")
    parser.add_argument("--daten", help="Datenordner (Standard: %%PROGRAMDATA%%\\RaumfeldRemote)")
    argumente = parser.parse_args()

    # WICHTIG: Datenordner setzen, BEVOR die anderen Module importiert werden,
    # denn protokoll.py legt den Pfad der Protokolldatei schon beim Import fest.
    os.environ["RAUMFELD_REMOTE_DATEN"] = argumente.daten or os.environ.get(
        "RAUMFELD_REMOTE_DATEN") or str(standard_datenordner())

    import waitress  # Produktions-Webserver, laeuft gut unter Windows

    from . import __version__
    from .protokoll import protokoll
    from .web import app_erzeugen
    from .zentrale import Zentrale

    zentrale = Zentrale()
    port = argumente.port or int(zentrale.einst["web_port"])
    zentrale.starten()
    app = app_erzeugen(zentrale)
    protokoll(f"Web-Oberfläche v{__version__} auf Port {port} – Datenordner "
              f"{os.environ['RAUMFELD_REMOTE_DATEN']}")
    if not zentrale.einst["passwort_hash"]:
        protokoll(f"Noch kein Passwort gesetzt: am Server http://localhost:{port} öffnen.")
    # threads: mehrere Browser gleichzeitig; "Abspielen" blockiert, bis die Titelliste steht
    waitress.serve(app, host="0.0.0.0", port=port, threads=16, ident="RaumfeldRemote")


if __name__ == "__main__":
    main()
