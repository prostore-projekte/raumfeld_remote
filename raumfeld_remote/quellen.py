# -*- coding: utf-8 -*-
"""
quellen.py - Eingaben (YouTube-URL, Playlist, Suchbegriff, Datei) in eine
Titel-Warteschlange umwandeln, plus Hilfen rund um yt-dlp und ffmpeg.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# Unter Windows verhindert dieses Flag, dass fuer jeden Hilfsprozess
# (yt-dlp, ffmpeg) kurz ein schwarzes Konsolenfenster aufpoppt.
KEIN_FENSTER = getattr(subprocess, "CREATE_NO_WINDOW", 0)


@dataclass
class Titel:
    """Ein Eintrag der Warteschlange."""
    quelle: str   # YouTube-URL, "ytsearch1:..." oder lokaler Dateipfad
    titel: str    # Anzeigename


# ---------------------------------------------------------------------------
# Externe Programme finden
# ---------------------------------------------------------------------------

def _programm_ordner() -> Path:
    """Ordner der Anwendung (bei PyInstaller: Ordner der .exe)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def finde_programm(name: str) -> str | None:
    """
    Sucht ein Programm (z. B. 'ffmpeg', 'yt-dlp'):
      1. im Unterordner 'tools' neben der Anwendung
      2. im PATH des Systems
    Rueckgabe: vollstaendiger Pfad oder None.
    """
    endung = ".exe" if os.name == "nt" else ""
    lokal = _programm_ordner() / "tools" / (name + endung)
    if lokal.is_file():
        return str(lokal)
    return shutil.which(name)


def cookie_argumente(browser: str, datei: str) -> list[str]:
    """
    Baut die yt-dlp-Argumente fuer die Anmeldung bei YouTube.
      - cookies.txt hat Vorrang (stabiler als der Browser-Zugriff)
      - sonst Cookies direkt aus dem Browser lesen
    """
    if datei and os.path.isfile(datei):
        return ["--cookies", datei]
    if browser and browser != "keiner":
        return ["--cookies-from-browser", browser]
    return []


# ---------------------------------------------------------------------------
# Titel-Liste aufbauen
# ---------------------------------------------------------------------------

def titel_liste_aufbauen(eingaben: list[str], cookie_args: list[str],
                         einzeln: bool = False) -> tuple[list[Titel], list[str]]:
    """
    Wandelt Eingaben in Titel um.
      - Lokale Datei  -> ein Titel
      - URL           -> ein oder mehrere Titel (Playlists werden aufgeloest)
      - Freitext      -> YouTube-Suche, erster Treffer
    einzeln=True: Bei 'watch?v=..&list=..' nur den einen Titel nehmen.

    Rueckgabe: (Titel-Liste, Liste von Fehlermeldungen)
    """
    ytdlp = finde_programm("yt-dlp")
    titel_liste: list[Titel] = []
    fehler: list[str] = []

    for eintrag in eingaben:
        eintrag = eintrag.strip().strip('"')
        if not eintrag:
            continue

        # Lokale Datei?
        pfad = os.path.expanduser(eintrag)
        if os.path.isfile(pfad):
            titel_liste.append(Titel(os.path.abspath(pfad), os.path.basename(pfad)))
            continue

        # Spotify-Links koennen yt-dlp nicht (DRM) -> klare Meldung statt Raetselraten
        if "open.spotify.com" in eintrag or eintrag.startswith("spotify:"):
            fehler.append("Spotify-Links bitte im Reiter „Spotify“ verwenden.")
            continue

        if ytdlp is None:
            fehler.append("yt-dlp wurde nicht gefunden (siehe Reiter „Einstellungen“).")
            break

        # Kein Link -> als Suchbegriff behandeln
        if "://" not in eintrag:
            eintrag = f"ytsearch1:{eintrag}"

        befehl = [ytdlp, "--flat-playlist", "--ignore-errors", "--no-warnings",
                  "--print", "%(id)s\t%(title)s", *cookie_args]
        if einzeln:
            befehl.append("--no-playlist")
        befehl.append(eintrag)

        proc = subprocess.run(befehl, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              creationflags=KEIN_FENSTER)
        gefunden = 0
        for zeile in proc.stdout.splitlines():
            video_id, _, name = zeile.partition("\t")
            if video_id:
                titel_liste.append(Titel(
                    f"https://www.youtube.com/watch?v={video_id}",
                    name or video_id))
                gefunden += 1
        if not gefunden:
            meldung = proc.stderr.strip().splitlines()
            fehler.append(f"Nichts gefunden für „{eintrag}“. "
                          f"{meldung[-1] if meldung else ''}".strip())
    return titel_liste, fehler
