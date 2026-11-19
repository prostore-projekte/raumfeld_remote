# -*- coding: utf-8 -*-
"""
player.py - Spielt eine Warteschlange nacheinander auf einem Renderer ab.

Die Wiedergabe laeuft in einem eigenen Thread. Die GUI bekommt ueber
Rueckruf-Funktionen Bescheid (diese werden aus dem Thread aufgerufen -
die GUI muss sie also thread-sicher behandeln).
"""

from __future__ import annotations

import random
import threading
import time
from typing import Callable

from .quellen import Titel
from .stream_server import StreamServer
from .upnp import Renderer, avt, baue_didl, hole_zustand


class Wiedergabe:
    """Steuert Warteschlange, Weiterschalten, Pause und Stop."""

    def __init__(self, renderer: Renderer, server: StreamServer, eigene_ip: str,
                 bei_titel: Callable[[int, int, str], None],
                 bei_meldung: Callable[[str], None],
                 bei_ende: Callable[[], None]) -> None:
        self.renderer = renderer
        self.server = server
        self.eigene_ip = eigene_ip
        self.bei_titel = bei_titel      # (index, gesamt, titel)
        self.bei_meldung = bei_meldung  # (text)
        self.bei_ende = bei_ende        # Warteschlange komplett durchgelaufen

        self._titel: list[Titel] = []
        self._index = 0
        self._ende = False              # True = Thread soll sich beenden
        self._sprung: int | None = None  # gewuenschter Zielindex (Weiter/Zurueck)
        self._wecker = threading.Event()  # weckt die Warte-Schleife sofort auf
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------ API
    def starte(self, titel: list[Titel], mischen: bool = False) -> None:
        """Startet die Wiedergabe der Liste ab dem ersten Titel."""
        self._titel = list(titel)
        if mischen:
            random.shuffle(self._titel)
        self._index = 0
        self._ende = False
        self._sprung = None
        self._wecker.clear()
        # Dem Server mitteilen, welche Nummer zu welcher Quelle gehoert
        self.server.quellen = {str(i): t.quelle for i, t in enumerate(self._titel)}
        self._thread = threading.Thread(target=self._lauf, daemon=True)
        self._thread.start()

    def naechster(self) -> None:
        self._sprung = self._index + 1
        self._wecker.set()

    def voriger(self) -> None:
        self._sprung = max(0, self._index - 1)
        self._wecker.set()

    def pause(self) -> None:
        avt(self.renderer, "Pause")

    def fortsetzen(self) -> None:
        avt(self.renderer, "Play", Speed=1)

    def beenden(self) -> None:
        """Stoppt Wiedergabe und Thread (blockiert hoechstens wenige Sekunden)."""
        self._ende = True
        self._wecker.set()
        try:
            avt(self.renderer, "Stop")
        except (RuntimeError, OSError):
            pass
        if self._thread and self._thread.is_alive() \
                and self._thread is not threading.current_thread():
            self._thread.join(timeout=5)

    # ------------------------------------------------------------- Intern
    def _lauf(self) -> None:
        """Hauptschleife: Titel fuer Titel abspielen."""
        natuerliches_ende = True
        while not self._ende and 0 <= self._index < len(self._titel):
            titel = self._titel[self._index]
            self._sprung = None
            self.bei_titel(self._index, len(self._titel), titel.titel)

            url = f"http://{self.eigene_ip}:{self.server.port}/stream/{self._index}.mp3"
            try:
                try:
                    avt(self.renderer, "Stop")   # alte Wiedergabe beenden
                except RuntimeError:
                    pass
                avt(self.renderer, "SetAVTransportURI", CurrentURI=url,
                    CurrentURIMetaData=baue_didl(titel.titel, url))
                avt(self.renderer, "Play", Speed=1)
            except (RuntimeError, OSError) as exc:
                self.bei_meldung(f"Fehler bei „{titel.titel}“: {exc}")
                self._index += 1
                continue

            ergebnis = self._warte_auf_ende()
            if ergebnis == "stopp":
                natuerliches_ende = False
                break
            if ergebnis == "sprung" and self._sprung is not None:
                self._index = self._sprung
                continue
            if ergebnis == "nicht_gestartet":
                self.bei_meldung(f"„{titel.titel}“ startete nicht – nächster Titel.")
            self._index += 1

        if natuerliches_ende and not self._ende:
            self.bei_ende()

    def _warte_auf_ende(self, start_timeout: float = 45.0) -> str:
        """
        Wartet, bis der Titel zu Ende ist.
        Rueckgabe: "ende" | "sprung" | "stopp" | "nicht_gestartet"
        """
        gestartet = False
        beginn = time.monotonic()
        while True:
            # Wartet bis zu 2 s; kehrt sofort zurueck, wenn Weiter/Stop gedrueckt wird
            if self._wecker.wait(2.0):
                self._wecker.clear()
                if self._ende:
                    return "stopp"
                if self._sprung is not None:
                    return "sprung"
            try:
                zustand = hole_zustand(self.renderer)
            except (RuntimeError, OSError):
                continue  # kurzer Netzwerk-Haenger - weiter abfragen
            if zustand == "PLAYING":
                gestartet = True
            elif gestartet and zustand in ("STOPPED", "NO_MEDIA_PRESENT"):
                return "ende"
            elif not gestartet and time.monotonic() - beginn > start_timeout:
                return "nicht_gestartet"
