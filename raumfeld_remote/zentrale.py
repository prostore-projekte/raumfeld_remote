# -*- coding: utf-8 -*-
"""
zentrale.py - Kern des zentralen Dienstes (Mehrbenutzer-Betrieb im Buero).

Ein einziger Prozess auf dem Server haelt:
  - die zentralen Einstellungen (Datei dienst.json im Datenordner, fuer alle gleich)
  - die gefundenen Lautsprecher
  - genau EINE Wiedergabe pro Lautsprecher (alle Benutzer sehen und steuern dieselbe)
  - den gemeinsamen Stream-Server
  - die Ueberwachung der Ruhezeiten (z. B. "ab 21:00 Uhr keine Musik")

Die Web-Oberflaeche (web.py) ruft nur Methoden dieser Klasse auf.
Alle Methoden sind thread-sicher (waitress bedient Anfragen parallel).
"""

from __future__ import annotations

import datetime as dt
import json
import secrets
import subprocess
import threading
import time
from dataclasses import dataclass, field

from .einstellungen import konfig_ordner
from .player import Wiedergabe
from .protokoll import protokoll
from .quellen import KEIN_FENSTER, finde_programm, titel_liste_aufbauen
from .stream_server import StreamServer
from .upnp import (Renderer, hole_lautstaerke, lokale_ip_zu, netz_adressen,
                   renderer_laden, renderer_suchen, setze_lautstaerke)

# ---------------------------------------------------------------------------
# Einstellungen des Dienstes
# ---------------------------------------------------------------------------

# Alle Einstellungen mit Standardwerten. Gespeichert in <Datenordner>/dienst.json.
STANDARD: dict = {
    "passwort_hash": "",        # PBKDF2-Hash des Zugangspassworts (leer = noch nicht eingerichtet)
    "geheimschluessel": "",     # Schluessel fuer Sitzungs-Cookies (wird beim ersten Start erzeugt)
    "web_port": 8080,           # Port der Web-Oberflaeche
    "stream_port": 8765,        # Port, von dem die Lautsprecher den Stream holen
    "bitrate": "320k",          # MP3-Bitrate
    "such_netze": [],           # weitere Netze fuer die Suche, z. B. ["192.168.20.0/24"]
    "manuelle_boxen": [],       # Geraete-URLs, die bei jeder Suche direkt abgefragt werden
    "favoriten": [],            # Liste aus {"name": ..., "url": ...}
    # Ruhezeiten: Liste aus {"tage": [0..6] (0 = Montag), "von": "HH:MM", "bis": "HH:MM"}
    # "bis" vor "von" bedeutet: ueber Mitternacht (z. B. 21:00 bis 07:00)
    "ruhezeiten": [],
}

# Wochentage fuer Meldungen (Index wie datetime.weekday())
WOCHENTAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


class DienstEinstellungen:
    """Zentrale Einstellungen als JSON-Datei; thread-sicher, atomar gespeichert."""

    def __init__(self) -> None:
        self.datei = konfig_ordner() / "dienst.json"
        self._sperre = threading.Lock()
        self.daten: dict = json.loads(json.dumps(STANDARD))  # tiefe Kopie
        try:
            gelesen = json.loads(self.datei.read_text(encoding="utf-8"))
            for schluessel in STANDARD:
                if schluessel in gelesen:
                    self.daten[schluessel] = gelesen[schluessel]
        except (OSError, ValueError):
            pass  # erste Ausfuehrung oder kaputte Datei -> Standardwerte
        # Schluessel fuer Sitzungs-Cookies einmalig erzeugen
        if not self.daten["geheimschluessel"]:
            self.setzen(geheimschluessel=secrets.token_hex(32))

    def __getitem__(self, schluessel: str):
        with self._sperre:
            return json.loads(json.dumps(self.daten[schluessel]))  # Kopie herausgeben

    def setzen(self, **werte) -> None:
        """Setzt einen oder mehrere Werte und speichert sofort."""
        with self._sperre:
            for schluessel, wert in werte.items():
                if schluessel not in STANDARD:
                    raise KeyError(schluessel)
                self.daten[schluessel] = wert
            temp = self.datei.with_suffix(".tmp")
            temp.write_text(json.dumps(self.daten, indent=2, ensure_ascii=False),
                            encoding="utf-8")
            temp.replace(self.datei)


# ---------------------------------------------------------------------------
# Ruhezeiten
# ---------------------------------------------------------------------------

def _minuten(uhrzeit: str) -> int:
    """'21:30' -> 1290 (Minuten seit Mitternacht). Wirft ValueError bei falschem Format."""
    stunden, minuten = uhrzeit.strip().split(":")
    wert = int(stunden) * 60 + int(minuten)
    if not 0 <= wert < 24 * 60:
        raise ValueError(uhrzeit)
    return wert


def ruhezeiten_pruefen(regeln: list[dict]) -> list[dict]:
    """
    Prueft und normalisiert Ruhezeit-Regeln aus der Web-Oberflaeche.
    Wirft ValueError mit verstaendlicher Meldung bei falschen Angaben.
    """
    sauber = []
    for regel in regeln:
        tage = sorted({int(t) for t in regel.get("tage", [])})
        if not tage or any(not 0 <= t <= 6 for t in tage):
            raise ValueError("Jede Ruhezeit braucht mindestens einen Wochentag.")
        von, bis = str(regel.get("von", "")), str(regel.get("bis", ""))
        try:
            if _minuten(von) == _minuten(bis):
                raise ValueError("Beginn und Ende einer Ruhezeit dürfen nicht gleich sein.")
        except (ValueError, AttributeError) as exc:
            if "dürfen" in str(exc):
                raise
            raise ValueError(f"Ungültige Uhrzeit: {von} – {bis} (Format HH:MM)") from exc
        sauber.append({"tage": tage, "von": von.strip(), "bis": bis.strip()})
    return sauber


def aktive_ruhezeit(regeln: list[dict], jetzt: dt.datetime | None = None) -> dict | None:
    """
    Liefert die Regel, die gerade gilt, sonst None.
    Ueber Mitternacht (bis < von): gilt am Starttag ab 'von' und am Folgetag bis 'bis'.
    Beispiel {"tage": [0..4], "von": "21:00", "bis": "07:00"}: Mo 21:00 bis Di 07:00 usw.
    """
    jetzt = jetzt or dt.datetime.now()
    minute = jetzt.hour * 60 + jetzt.minute
    heute = jetzt.weekday()
    gestern = (heute - 1) % 7
    for regel in regeln:
        try:
            von, bis = _minuten(regel["von"]), _minuten(regel["bis"])
        except (KeyError, ValueError):
            continue
        tage = regel.get("tage", [])
        if von < bis:
            # innerhalb eines Tages, z. B. 12:00-13:00
            if heute in tage and von <= minute < bis:
                return regel
        else:
            # ueber Mitternacht, z. B. 21:00-07:00
            if (heute in tage and minute >= von) or (gestern in tage and minute < bis):
                return regel
    return None


def ruhezeit_text(regel: dict) -> str:
    """Lesbare Form einer Regel, z. B. 'Mo, Di, Mi 21:00–07:00'."""
    tage = ", ".join(WOCHENTAGE[t] for t in regel.get("tage", []))
    return f"{tage} {regel.get('von')}–{regel.get('bis')}"


# ---------------------------------------------------------------------------
# Zustand pro Lautsprecher
# ---------------------------------------------------------------------------

@dataclass
class BoxZustand:
    """Was gerade auf einem Lautsprecher passiert (fuer die Anzeige bei allen Benutzern)."""
    renderer: Renderer
    wiedergabe: Wiedergabe | None = None
    titel: str = ""                 # aktueller Titel
    meldung: str = ""               # letzte Meldung (Fehler, Hinweise)
    gestartet_von: str = ""         # wer zuletzt abgespielt hat (IP-Adresse)
    pausiert: bool = False
    extras: dict = field(default_factory=dict)


class Zentrale:
    """Der zentrale Zustand des Dienstes. Eine Instanz pro Prozess."""

    def __init__(self) -> None:
        self.einst = DienstEinstellungen()
        self._sperre = threading.RLock()
        self.boxen: dict[str, BoxZustand] = {}   # Schluessel: Geraete-URL (location)
        self.server: StreamServer | None = None
        self._zaehler = 0                         # fuer eindeutige Stream-Praefixe
        self.suche_laeuft = False
        self.letzte_suche = 0.0

    # ------------------------------------------------------------ Start
    def starten(self) -> None:
        """Hintergrund-Aufgaben starten: erste Suche, Ruhezeit-Waechter, yt-dlp-Update."""
        protokoll("=== Raumfeld Remote Dienst gestartet ===")
        self.suchen_im_hintergrund()
        threading.Thread(target=self._ruhezeit_waechter, daemon=True).start()
        threading.Thread(target=self._ytdlp_aktualisieren_schleife, daemon=True).start()

    # ------------------------------------------------------------ Lautsprecher
    def suchen_im_hintergrund(self) -> None:
        """Startet eine Lautsprechersuche, falls nicht schon eine laeuft."""
        with self._sperre:
            if self.suche_laeuft:
                return
            self.suche_laeuft = True
        threading.Thread(target=self._suchen, daemon=True).start()

    def _suchen(self) -> None:
        try:
            protokoll("Lautsprechersuche gestartet …")
            gefunden = renderer_suchen(timeout=4.0,
                                       zusatz_netze=self.einst["such_netze"],
                                       bekannte_urls=self.einst["manuelle_boxen"])
            with self._sperre:
                for r in gefunden:
                    if r.location in self.boxen:
                        self.boxen[r.location].renderer = r   # Daten auffrischen
                    else:
                        self.boxen[r.location] = BoxZustand(renderer=r)
            protokoll(f"Lautsprechersuche fertig: {len(gefunden)} Gerät(e) gefunden.")
        finally:
            with self._sperre:
                self.suche_laeuft = False
                self.letzte_suche = time.time()

    def box_hinzufuegen(self, url: str) -> str:
        """Geraet per URL hinzufuegen und dauerhaft merken. Rueckgabe: Name."""
        r = renderer_laden(url)
        if r is None:
            raise ValueError("Unter dieser URL wurde kein nutzbares Gerät gefunden.")
        liste = self.einst["manuelle_boxen"]
        if url not in liste:
            self.einst.setzen(manuelle_boxen=liste + [url])
        with self._sperre:
            self.boxen.setdefault(r.location, BoxZustand(renderer=r))
        protokoll(f"Gerät manuell hinzugefügt: {r.name} ({url})")
        return r.name

    def _box(self, location: str) -> BoxZustand:
        with self._sperre:
            if location not in self.boxen:
                raise ValueError("Unbekannter Lautsprecher – bitte neu suchen.")
            return self.boxen[location]

    def lautstaerke_lesen(self, location: str) -> int:
        return hole_lautstaerke(self._box(location).renderer)

    def lautstaerke_setzen(self, location: str, wert: int) -> None:
        setze_lautstaerke(self._box(location).renderer, max(0, min(100, int(wert))))

    # ------------------------------------------------------------ Wiedergabe
    def _server_sicherstellen(self) -> StreamServer:
        """Gemeinsamen Stream-Server bei Bedarf starten."""
        with self._sperre:
            if self.server is None:
                self.server = StreamServer(int(self.einst["stream_port"]),
                                           self.einst["bitrate"], self._cookie_args())
                self.server.starten()
            self.server.cookie_args = self._cookie_args()  # evtl. neue cookies.txt
            return self.server

    def _cookie_args(self) -> list[str]:
        """YouTube-Anmeldung: hochgeladene cookies.txt im Datenordner (falls vorhanden)."""
        datei = konfig_ordner() / "cookies.txt"
        return ["--cookies", str(datei)] if datei.is_file() else []

    def abspielen(self, location: str, eingabe: str, einzeln: bool, zufall: bool,
                  wer: str) -> str:
        """
        Spielt Link/Playlist/Suchbegriff auf einem Lautsprecher ab (blockiert,
        bis die Titelliste aufgeloest ist). Rueckgabe: Meldung fuer den Benutzer.
        """
        regel = aktive_ruhezeit(self.einst["ruhezeiten"])
        if regel:
            raise ValueError(f"Ruhezeit ({ruhezeit_text(regel)}) – Abspielen ist gerade gesperrt.")
        for programm in ("ffmpeg", "yt-dlp"):
            if finde_programm(programm) is None:
                raise ValueError(f"{programm} fehlt auf dem Server – bitte neu installieren.")
        box = self._box(location)
        eingaben = [z.strip() for z in eingabe.splitlines() if z.strip()]
        if not eingaben:
            raise ValueError("Bitte einen Link oder Suchbegriff eingeben.")

        protokoll(f"{wer}: Abspielen auf {box.renderer.name}: {', '.join(eingaben)[:200]}")
        liste, fehler = titel_liste_aufbauen(eingaben, self._cookie_args(), einzeln)
        for f in fehler:
            protokoll(f"  Hinweis: {f}")
        if not liste:
            raise ValueError("Keine abspielbaren Titel gefunden. " + " ".join(fehler))

        server = self._server_sicherstellen()
        with self._sperre:
            if box.wiedergabe:
                box.wiedergabe.beenden()
            self._zaehler += 1
            praefix = f"w{self._zaehler}_"

            def bei_titel(index: int, gesamt: int, titel: str, b=box) -> None:
                b.titel = f"{titel}  ({index + 1}/{gesamt})"
                b.pausiert = False

            def bei_meldung(text: str, b=box) -> None:
                b.meldung = text
                protokoll(f"  {b.renderer.name}: {text}")

            def bei_ende(b=box) -> None:
                b.titel = ""
                b.meldung = "Warteschlange zu Ende."

            box.wiedergabe = Wiedergabe(box.renderer, server, lokale_ip_zu(box.renderer.host),
                                        bei_titel, bei_meldung, bei_ende, praefix=praefix)
            box.meldung = ""
            box.gestartet_von = wer
            box.wiedergabe.starte(liste, mischen=zufall)
        return f"{len(liste)} Titel auf {box.renderer.name} gestartet."

    def steuern(self, location: str, aktion: str, index: int = -1) -> None:
        """Transport: pause, weiter, stop, naechster, voriger, springe."""
        box = self._box(location)
        w = box.wiedergabe
        if w is None or not w.laeuft:
            raise ValueError("Auf diesem Lautsprecher läuft gerade nichts.")
        if aktion in ("naechster", "voriger", "springe", "weiter") and \
                aktive_ruhezeit(self.einst["ruhezeiten"]):
            raise ValueError("Ruhezeit – Wiedergabe ist gerade gesperrt.")
        if aktion == "pause":
            w.pause()
            box.pausiert = True
        elif aktion == "weiter":
            w.fortsetzen()
            box.pausiert = False
        elif aktion == "stop":
            w.beenden()
            box.titel = ""
            box.meldung = "Gestoppt."
        elif aktion == "naechster":
            w.naechster()
        elif aktion == "voriger":
            w.voriger()
        elif aktion == "springe":
            w.springe_zu(index)
        else:
            raise ValueError(f"Unbekannte Aktion: {aktion}")

    def alles_stoppen(self, grund: str) -> int:
        """Stoppt alle laufenden Wiedergaben. Rueckgabe: Anzahl gestoppter Lautsprecher."""
        anzahl = 0
        with self._sperre:
            boxen = list(self.boxen.values())
        for box in boxen:
            if box.wiedergabe and box.wiedergabe.laeuft:
                box.wiedergabe.beenden()
                box.titel = ""
                box.meldung = grund
                anzahl += 1
        return anzahl

    # ------------------------------------------------------------ Zustand
    def zustand(self) -> dict:
        """Gesamtzustand fuer die Web-Oberflaeche (wird alle paar Sekunden abgefragt)."""
        regel = aktive_ruhezeit(self.einst["ruhezeiten"])
        with self._sperre:
            boxen = []
            for location, box in sorted(self.boxen.items(), key=lambda e: e[1].renderer.name.lower()):
                titel_liste, index = (box.wiedergabe.warteschlange if box.wiedergabe
                                      else ([], 0))
                laeuft = bool(box.wiedergabe and box.wiedergabe.laeuft)
                boxen.append({
                    "id": location,
                    "name": box.renderer.name,
                    "host": box.renderer.host,
                    "laeuft": laeuft,
                    "pausiert": box.pausiert and laeuft,
                    "titel": box.titel if laeuft else "",
                    "meldung": box.meldung,
                    "gestartet_von": box.gestartet_von,
                    "warteschlange": titel_liste if laeuft else [],
                    "index": index,
                })
            return {
                "boxen": boxen,
                "suche_laeuft": self.suche_laeuft,
                "ruhezeit": ruhezeit_text(regel) if regel else "",
                "programme": {p: bool(finde_programm(p)) for p in ("yt-dlp", "ffmpeg", "deno")},
                "cookies": (konfig_ordner() / "cookies.txt").is_file(),
            }

    # ------------------------------------------------------------ Einstellungen
    def einstellungen_lesen(self) -> dict:
        """Einstellungen fuer die Oberflaeche (ohne Passwort-Hash und Geheimschluessel)."""
        return {k: self.einst[k] for k in STANDARD
                if k not in ("passwort_hash", "geheimschluessel")}

    def einstellungen_speichern(self, neu: dict) -> None:
        """Prueft und speichert Einstellungen aus der Web-Oberflaeche."""
        werte: dict = {}
        if "such_netze" in neu:
            netze = [str(n).strip() for n in neu["such_netze"] if str(n).strip()]
            ungueltig = [n for n in netze if not netz_adressen([n])]
            if ungueltig:
                raise ValueError("Ungültige Netzangabe: " + ", ".join(ungueltig))
            werte["such_netze"] = netze
        if "manuelle_boxen" in neu:
            werte["manuelle_boxen"] = [str(u).strip() for u in neu["manuelle_boxen"] if str(u).strip()]
        if "ruhezeiten" in neu:
            werte["ruhezeiten"] = ruhezeiten_pruefen(neu["ruhezeiten"])
        if "bitrate" in neu:
            if neu["bitrate"] not in ("128k", "192k", "256k", "320k"):
                raise ValueError("Ungültige Bitrate.")
            werte["bitrate"] = neu["bitrate"]
        if "favoriten" in neu:
            werte["favoriten"] = [{"name": str(f["name"])[:100], "url": str(f["url"])[:1000]}
                                  for f in neu["favoriten"] if f.get("url")]
        self.einst.setzen(**werte)
        if "bitrate" in werte and self.server:
            self.server.bitrate = werte["bitrate"]  # gilt ab dem naechsten Titel
        protokoll(f"Einstellungen geändert: {', '.join(werte) or '–'}")
        # Neue Ruhezeit greift sofort
        self._ruhezeit_pruefen_einmal()

    # ------------------------------------------------------------ Hintergrund
    def _ruhezeit_pruefen_einmal(self) -> None:
        regel = aktive_ruhezeit(self.einst["ruhezeiten"])
        if regel:
            anzahl = self.alles_stoppen(f"Ruhezeit ({ruhezeit_text(regel)}) – automatisch gestoppt.")
            if anzahl:
                protokoll(f"Ruhezeit {ruhezeit_text(regel)}: {anzahl} Wiedergabe(n) gestoppt.")

    def _ruhezeit_waechter(self) -> None:
        """Prueft alle 30 Sekunden, ob eine Ruhezeit begonnen hat."""
        while True:
            try:
                self._ruhezeit_pruefen_einmal()
            except Exception as exc:  # noqa: BLE001 - Waechter darf nie sterben
                protokoll(f"✗ Ruhezeit-Prüfung fehlgeschlagen: {exc!r}")
            time.sleep(30)

    def _ytdlp_aktualisieren_schleife(self) -> None:
        """
        yt-dlp beim Start und danach taeglich aktualisieren (YouTube aendert sich oft).
        Der Dienst laeuft als SYSTEM und darf die Datei im Programmordner ersetzen.
        """
        while True:
            ytdlp = finde_programm("yt-dlp")
            if ytdlp:
                try:
                    ergebnis = subprocess.run([ytdlp, "-U"], capture_output=True, text=True,
                                              timeout=300, creationflags=KEIN_FENSTER)
                    letzte = (ergebnis.stdout.strip().splitlines() or ["?"])[-1]
                    protokoll(f"yt-dlp-Update: {letzte}")
                except (OSError, subprocess.SubprocessError) as exc:
                    protokoll(f"✗ yt-dlp-Update fehlgeschlagen: {exc}")
            time.sleep(24 * 3600)
