# -*- coding: utf-8 -*-
"""
einstellungen.py - Persistente Einstellungen (JSON-Datei im Benutzerprofil).

Zwei Ebenen (wichtig fuer Terminalserver mit mehreren Benutzern):
  1. Gemeinsam fuer alle Benutzer:  %PROGRAMDATA%/RaumfeldRemote/einstellungen.json
     (anderer Ort per Umgebungsvariable RAUMFELD_REMOTE_GEMEINSAM, z. B. Netzlaufwerk)
  2. Pro Benutzer:                  %APPDATA%/RaumfeldRemote/einstellungen.json
Reihenfolge beim Lesen: Standardwerte -> gemeinsam -> Benutzer.
In der Benutzerdatei stehen nur Werte, die der Benutzer selbst geaendert hat;
alles andere kommt aus der gemeinsamen Datei. Diese kann nur schreiben, wer
Schreibrechte auf den Ordner hat (normalerweise Administratoren).
Im Benutzerordner liegt auch das Spotify-Token (spotify_token.json).
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


def gemeinsamer_ordner() -> Path:
    """
    Ordner fuer Einstellungen, die fuer ALLE Benutzer gelten.
    Wird hier NICHT angelegt, weil normale Benutzer dort meist keine
    Schreibrechte haben (Anlegen erst beim Speichern "fuer alle").
    """
    eigener = os.environ.get("RAUMFELD_REMOTE_GEMEINSAM")
    if eigener:
        return Path(eigener)
    programdata = os.environ.get("PROGRAMDATA")  # Windows: meist C:\ProgramData
    if programdata:
        return Path(programdata) / "RaumfeldRemote"
    # Fallback fuer Linux/macOS (zum Entwickeln und Testen)
    return Path.home() / ".config" / "raumfeld_remote" / "gemeinsam"


# Einstellungen, die sich "fuer alle Benutzer" speichern lassen
# (Netze, Geraete, Konten, Stream-Optionen; nicht z. B. die zuletzt gewaehlte Box).
GEMEINSAME_SCHLUESSEL = (
    "port", "bitrate", "such_netze", "manuelle_boxen", "favoriten",
    "browser_cookies", "cookies_datei", "spotify_client_id",
)


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
        self.gemeinsame_datei = gemeinsamer_ordner() / "einstellungen.json"
        self.daten: dict = json.loads(json.dumps(STANDARD))  # tiefe Kopie
        self._eigene: set[str] = set()  # Schluessel, die der Benutzer selbst gesetzt hat
        self.laden()

    @staticmethod
    def _lies(datei: Path) -> dict:
        """Liest eine JSON-Datei; fehlt sie oder ist sie kaputt -> leeres Dictionary."""
        try:
            gelesen = json.loads(datei.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return gelesen if isinstance(gelesen, dict) else {}

    @staticmethod
    def _schreib(datei: Path, daten: dict) -> None:
        """Schreibt zuerst in eine Temp-Datei und ersetzt dann (kein halbes Schreiben)."""
        datei.parent.mkdir(parents=True, exist_ok=True)
        temp = datei.with_suffix(".tmp")
        temp.write_text(json.dumps(daten, indent=2, ensure_ascii=False), encoding="utf-8")
        temp.replace(datei)

    def laden(self) -> None:
        """Standard -> gemeinsame Datei -> Benutzerdatei; unbekannte Schluessel ignorieren."""
        gemeinsam = self._lies(self.gemeinsame_datei)
        for schluessel in GEMEINSAME_SCHLUESSEL:
            if schluessel in gemeinsam:
                self.daten[schluessel] = gemeinsam[schluessel]
        eigen = self._lies(self._datei)
        for schluessel in STANDARD:
            if schluessel in eigen:
                self.daten[schluessel] = eigen[schluessel]
                self._eigene.add(schluessel)

    def speichern(self) -> None:
        """Speichert nur die vom Benutzer selbst gesetzten Werte in seine Datei."""
        self._schreib(self._datei, {k: self.daten[k] for k in sorted(self._eigene)})

    def fuer_alle_speichern(self) -> Path:
        """
        Schreibt die aktuellen Werte der GEMEINSAME_SCHLUESSEL in die gemeinsame
        Datei und entfernt sie aus der Benutzerdatei (damit kuenftig die
        gemeinsamen Werte gelten). Wirft PermissionError/OSError, wenn der
        Benutzer keine Schreibrechte hat. Rueckgabe: Pfad der gemeinsamen Datei.
        """
        gemeinsam = self._lies(self.gemeinsame_datei)
        for schluessel in GEMEINSAME_SCHLUESSEL:
            gemeinsam[schluessel] = self.daten[schluessel]
        self._schreib(self.gemeinsame_datei, gemeinsam)
        self._eigene -= set(GEMEINSAME_SCHLUESSEL)
        self.speichern()
        return self.gemeinsame_datei

    def __getitem__(self, schluessel: str):
        return self.daten[schluessel]

    def __setitem__(self, schluessel: str, wert) -> None:
        self.daten[schluessel] = wert
        self._eigene.add(schluessel)  # ab jetzt eigener Wert dieses Benutzers
        self.speichern()
