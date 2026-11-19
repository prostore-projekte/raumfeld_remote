# -*- coding: utf-8 -*-
"""
einstellungen.py - Persistente Einstellungen (JSON-Datei im Benutzerprofil).

Unter Windows liegt die Datei in:  %APPDATA%/RaumfeldRemote/einstellungen.json
Dort liegt spaeter auch das Spotify-Token (spotify_token.json).
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def konfig_ordner() -> Path:
    """Liefert den Ordner fuer Konfigurationsdateien und legt ihn bei Bedarf an."""
    appdata = os.environ.get("APPDATA")  # nur unter Windows gesetzt
    if appdata:
        ordner = Path(appdata) / "RaumfeldRemote"
    else:
        # Fallback fuer Linux/macOS (zum Entwickeln und Testen)
        ordner = Path.home() / ".config" / "raumfeld_remote"
    ordner.mkdir(parents=True, exist_ok=True)
    return ordner


# Alle bekannten Einstellungen mit ihren Standardwerten.
STANDARD: dict = {
    "port": 8765,                    # Port des lokalen Stream-Servers
    "bitrate": "320k",               # MP3-Bitrate fuer die Umwandlung
    "browser_cookies": "keiner",     # Browser, aus dem yt-dlp Cookies liest
    "cookies_datei": "",             # Alternative: cookies.txt (Netscape-Format)
    "letzte_box": "",                # LOCATION-URL des zuletzt gewaehlten Geraets
    "spotify_client_id": "",         # Client-ID der eigenen Spotify-App
    "nur_einzeltitel": False,        # Checkbox "Nur diesen Titel"
    "zufall": False,                 # Checkbox "Zufaellige Reihenfolge"
    "favoriten": [],                 # Liste aus {"name": ..., "url": ...}
    "such_netze": [],                # weitere Netze fuer die Suche, z. B. ["192.168.20.0/24"]
    "manuelle_boxen": [],            # manuell eingetragene Geraete-URLs (bei jeder Suche abgefragt)
}


class Einstellungen:
    """Kleiner Wrapper: Einstellungen lesen/schreiben wie ein Dictionary."""

    def __init__(self) -> None:
        self._datei = konfig_ordner() / "einstellungen.json"
        self.daten: dict = json.loads(json.dumps(STANDARD))  # tiefe Kopie
        self.laden()

    def laden(self) -> None:
        """Liest die Datei; unbekannte oder fehlende Schluessel werden ignoriert."""
        try:
            gelesen = json.loads(self._datei.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return  # Datei fehlt oder ist kaputt -> Standardwerte behalten
        for schluessel in STANDARD:
            if schluessel in gelesen:
                self.daten[schluessel] = gelesen[schluessel]

    def speichern(self) -> None:
        """Schreibt zuerst in eine Temp-Datei und ersetzt dann (kein halbes Schreiben)."""
        temp = self._datei.with_suffix(".tmp")
        temp.write_text(json.dumps(self.daten, indent=2, ensure_ascii=False),
                        encoding="utf-8")
        temp.replace(self._datei)

    def __getitem__(self, schluessel: str):
        return self.daten[schluessel]

    def __setitem__(self, schluessel: str, wert) -> None:
        self.daten[schluessel] = wert
        self.speichern()
