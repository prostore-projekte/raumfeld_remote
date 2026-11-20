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
from .protokoll import protokoll
from .stream_server import StreamServer
from .upnp import Renderer, avt, baue_didl, hole_zustand


class Wiedergabe:
    """Steuert Warteschlange, Weiterschalten, Pause und Stop."""

    def __init__(self, renderer: Renderer, server: StreamServer, eigene_ip: str,
                 bei_titel: Callable[[int, int, str], None],
                 bei_meldung: Callable[[str], None],
                 bei_ende: Callable[[], None], praefix: str = "") -> None:
        self.renderer = renderer
        # Praefix fuer die Stream-Nummern: mehrere Wiedergaben (eine pro Lautsprecher)
        # teilen sich einen Stream-Server und duerfen sich nicht ueberschreiben.
        self.praefix = praefix
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
        # Dem Server mitteilen, welche Nummer zu welcher Quelle gehoert.
        # Nur die eigenen Eintraege (mit Praefix) ersetzen, andere Wiedergaben behalten ihre.
        if self.praefix:
            for alt in [k for k in self.server.quellen if k.startswith(self.praefix)]:
                del self.server.quellen[alt]
            self.server.quellen.update({f"{self.praefix}{i}": t.quelle
                                        for i, t in enumerate(self._titel)})
        else:
            self.server.quellen = {str(i): t.quelle for i, t in enumerate(self._titel)}
        self._thread = threading.Thread(target=self._lauf, daemon=True)
        self._thread.start()

    @property
    def warteschlange(self) -> tuple[list[str], int]:
        """Anzeigenamen aller Titel und Index des aktuellen Titels (fuer die Web-Oberflaeche)."""
        return [t.titel for t in self._titel], self._index

    @property
    def laeuft(self) -> bool:
        """True, solange der Wiedergabe-Thread arbeitet."""
        return bool(self._thread and self._thread.is_alive() and not self._ende)

    def springe_zu(self, index: int) -> None:
        """Springt direkt zu einem Titel der Warteschlange (Klick in der Liste)."""
        if 0 <= index < len(self._titel):
            self._sprung = index
            self._wecker.set()

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

            url = f"http://{self.eigene_ip}:{self.server.port}/stream/{self.praefix}{self._index}.mp3"
            try:
                try:
                    avt(self.renderer, "Stop")   # alte Wiedergabe beenden
                except RuntimeError:
                    pass
                avt(self.renderer, "SetAVTransportURI", CurrentURI=url,
                    CurrentURIMetaData=baue_didl(titel.titel, url))
                avt(self.renderer, "Play", Speed=1)
                self._abruf_pruefen(f"{self.praefix}{self._index}", url)
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

    def _abruf_pruefen(self, nummer: str, url: str, sekunden: float = 10.0) -> None:
        """
        Prueft nach einigen Sekunden, ob der Lautsprecher den Stream wirklich
        abgerufen hat. Wenn nicht, erreicht er den PC nicht (Firewall, Routing,
        falsche IP-Adresse) - dann laeuft die Anzeige weiter, aber es ist nichts zu hoeren.
        """
        def pruefen() -> None:
            if not self._ende and self.server.abrufe.get(nummer, 0) == 0:
                protokoll(f"✗ Lautsprecher hat {url} nach {sekunden:.0f} s nicht abgerufen")
                self.bei_meldung("Der Lautsprecher hat den Stream nicht abgerufen – "
                                 f"erreicht er den PC? Firewall/Port prüfen. URL: {url}")
        zeitgeber = threading.Timer(sekunden, pruefen)
        zeitgeber.daemon = True
        zeitgeber.start()

    def _warte_auf_ende(self, start_timeout: float = 45.0) -> str:
        """
        Wartet, bis der Titel zu Ende ist.
        Rueckgabe: "ende" | "sprung" | "stopp" | "nicht_gestartet"
        """
        gestartet = False
        beginn = time.monotonic()
        letzter_zustand = None  # fuer das Protokoll: nur Wechsel melden
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
            # Nur Zustandswechsel protokollieren (Abfrage laeuft alle 2 s)
            if zustand != letzter_zustand:
                protokoll(f"  Zustand {self.renderer.name}: {zustand or '(leer)'}")
                letzter_zustand = zustand
            if zustand == "PLAYING":
                gestartet = True
            elif gestartet and zustand in ("STOPPED", "NO_MEDIA_PRESENT"):
                return "ende"
            elif not gestartet and time.monotonic() - beginn > start_timeout:
                return "nicht_gestartet"
