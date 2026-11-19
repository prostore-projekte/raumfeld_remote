# -*- coding: utf-8 -*-
"""
protokoll.py - Zentrales Protokoll fuer die Fehlersuche.

Jede Zeile geht an zwei Stellen:
  1. Datei %APPDATA%/RaumfeldRemote/stream.log (wird geleert, wenn > 1 MB)
  2. alle angemeldeten Beobachter (z. B. das aufklappbare Protokoll in der GUI)

Thread-sicher: darf aus beliebigen Threads aufgerufen werden. Beobachter
werden im aufrufenden Thread benachrichtigt und muessen selbst dafuer sorgen,
dass GUI-Aenderungen im Hauptthread passieren.
"""

from __future__ import annotations

import threading
import time
from typing import Callable

from .einstellungen import konfig_ordner

PROTOKOLL = konfig_ordner() / "stream.log"
MAX_GROESSE = 1_000_000  # Bytes; darueber wird die Datei beim Programmstart geleert

_sperre = threading.Lock()
_beobachter: list[Callable[[str], None]] = []

# Protokoll nicht endlos wachsen lassen
try:
    if PROTOKOLL.stat().st_size > MAX_GROESSE:
        PROTOKOLL.unlink()
except OSError:
    pass


def abonnieren(funktion: Callable[[str], None]) -> None:
    """Meldet eine Funktion an, die jede neue Protokollzeile erhaelt."""
    with _sperre:
        _beobachter.append(funktion)


def protokoll(text: str) -> None:
    """Schreibt eine Zeile mit Uhrzeit ins Protokoll (Fehler beim Schreiben ignorieren)."""
    zeile = time.strftime("%H:%M:%S ") + text.rstrip()
    with _sperre:
        try:
            with open(PROTOKOLL, "a", encoding="utf-8") as datei:
                datei.write(zeile + "\n")
        except OSError:
            pass
        beobachter = list(_beobachter)
    for funktion in beobachter:
        try:
            funktion(zeile)
        except Exception:  # noqa: BLE001 - ein defekter Beobachter darf nichts blockieren
            pass
