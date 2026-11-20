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
import os
import random
import secrets
import subprocess
import sys
import threading
import time
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path

from .einstellungen import konfig_ordner
from .player import Wiedergabe
from .protokoll import protokoll
from .quellen import KEIN_FENSTER, Titel, finde_programm, titel_liste_aufbauen
from .spotify import Spotify, SpotifyFehler
from .stream_server import StreamServer
from .tidal import PRAEFIX as TIDAL_PRAEFIX
from .tidal import QUALITAETEN as TIDAL_QUALITAETEN
from .tidal import Tidal
from .upnp import (Renderer, hole_lautstaerke, lokale_ip_zu, netz_adressen,
                   port_neu_suchen, renderer_laden, renderer_suchen, setze_lautstaerke)

# ---------------------------------------------------------------------------
# Einstellungen des Dienstes
# ---------------------------------------------------------------------------

# Alle Einstellungen mit Standardwerten. Gespeichert in <Datenordner>/dienst.json.
STANDARD: dict = {
    "passwort_hash": "",        # PBKDF2-Hash des Zugangspassworts (leer = noch nicht eingerichtet)
    "geheimschluessel": "",     # Schluessel fuer Sitzungs-Cookies (wird beim ersten Start erzeugt)
    # Port der Web-Oberflaeche. Bewusst nicht 8080 (dort laufen oft schon andere Dienste).
    # Aenderbar in der Web-Oberflaeche und im Installer; wirkt nach Neustart des Dienstes.
    "web_port": 8766,
    "stream_port": 8765,        # Port, von dem die Lautsprecher den Stream holen
    "bitrate": "320k",          # MP3-Bitrate
    "such_netze": [],           # weitere Netze fuer die Suche, z. B. ["192.168.20.0/24"]
    "manuelle_boxen": [],       # Geraete-URLs, die bei jeder Suche direkt abgefragt werden
    # Automatisch gemerkte Geraete-URLs (einmal gefunden oder aus der Einzelplatz-Variante
    # uebernommen). Werden bei jeder Suche direkt abgefragt - wichtig fuer Netze hinter
    # VPN/Router, in denen die SSDP-Suche keine Antwort bekommt.
    "bekannte_boxen": [],
    "alte_geraete_geprueft": False,   # Uebernahme aus der Einzelplatz-Variante schon erfolgt?
    "favoriten": [],            # Liste aus {"name": ..., "url": ...}
    # Ruhezeiten: Liste aus {"tage": [0..6] (0 = Montag), "von": "HH:MM", "bis": "HH:MM"}
    # "bis" vor "von" bedeutet: ueber Mitternacht (z. B. 21:00 bis 07:00)
    "ruhezeiten": [],
    "spotify_client_id": "",    # Client-ID der eigenen Spotify-Developer-App
    "tidal_qualitaet": "LOSSLESS",  # Tidal-Quelle: "LOSSLESS" (FLAC) oder "HIGH" (AAC 320)
}

def port_pruefen(wert, bezeichnung: str) -> int:
    """Prueft eine Portangabe aus der Oberflaeche. Wirft ValueError mit deutscher Meldung."""
    try:
        port = int(str(wert).strip())
    except ValueError:
        raise ValueError(f"{bezeichnung}: bitte eine Zahl angeben.") from None
    # Unter 1024 sind Systemdienste ueblich, 49152 und hoeher vergibt Windows dynamisch
    if not 1024 <= port <= 49151:
        raise ValueError(f"{bezeichnung}: erlaubt ist 1024 bis 49151.")
    return port


def verknuepfung_schreiben(port: int) -> None:
    """
    Aktualisiert die Startmenue-Verknuepfung "Raumfeld Remote.url" im Programmordner,
    damit sie nach einer Portaenderung auf den richtigen Port zeigt.
    Nur in der installierten Fassung (PyInstaller-EXE); beim Entwickeln passiert nichts.
    """
    if not getattr(sys, "frozen", False):
        return
    datei = Path(sys.executable).parent / "Raumfeld Remote.url"
    try:
        datei.write_text(f"[InternetShortcut]\r\nURL=http://localhost:{port}/\r\n", encoding="ascii")
    except OSError as exc:
        protokoll(f"✗ Startmenü-Verknüpfung nicht aktualisiert: {exc}")


# Grosse Playlists: so viele Titel werden sofort geladen, der Rest im Hintergrund
ANFANG_TITEL = 25

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
        # Port-Neusuche: URL -> Zeitpunkt des letzten erfolglosen Versuchs (nicht bei jeder
        # Suche erneut ~30 s scannen, wenn eine Box z. B. ausgeschaltet ist)
        self._neusuche_fehlschlag: dict[str, float] = {}
        # Spotify: ein gemeinsames Konto fuer alle (Token im Datenordner)
        self.spotify = Spotify(konfig_ordner() / "spotify_token.json", self.einst["spotify_client_id"])
        self._spotify_anmeldung: tuple[str, str] | None = None   # (verifier, state) waehrend der Anmeldung
        self.spotify_geraet = ""   # zuletzt per Spotify Connect gestartetes Geraet (fuer Ruhezeit-Pause)
        # Tidal: gemeinsames Konto, Zugang dauerhaft in tidal_sitzung.json
        self.tidal = Tidal(konfig_ordner() / "tidal_sitzung.json", self.einst["tidal_qualitaet"])

    # ------------------------------------------------------------ Start
    def starten(self) -> None:
        """Hintergrund-Aufgaben starten: erste Suche, Ruhezeit-Waechter, yt-dlp-Update."""
        protokoll("=== Raumfeld Remote Dienst gestartet ===")
        if not self.einst["alte_geraete_geprueft"]:
            self._alte_geraete_uebernehmen()
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

    def _alte_geraete_uebernehmen(self) -> None:
        r"""
        Einmalig: Geraete-URLs aus der Einzelplatz-Variante (Desktop-Programm) uebernehmen.
        Das Desktop-Programm merkt sich die zuletzt gewaehlte Box und fest eingetragene Geraete
        und fragt sie bei jeder Suche direkt ab - deshalb fand es Boxen hinter dem VPN "sofort",
        auch wenn die SSDP-Suche dort keine Antwort bekommt.
        Gelesen werden (der Dienst laeuft als SYSTEM und darf das):
          - %PROGRAMDATA%\RaumfeldRemote\einstellungen.json   (gemeinsame Einstellungen)
          - C:\Users\*\AppData\Roaming\RaumfeldRemote\einstellungen.json  (je Benutzer)
        """
        dateien = [konfig_ordner() / "einstellungen.json"]
        oeffentlich = os.environ.get("PUBLIC")   # z. B. C:\Users\Public -> Elternordner = C:\Users
        if oeffentlich:
            benutzer_ordner = Path(oeffentlich).parent
            try:
                dateien += list(benutzer_ordner.glob("*/AppData/Roaming/RaumfeldRemote/einstellungen.json"))
            except OSError:
                pass   # z. B. fehlende Rechte -> nur die gemeinsame Datei
        urls: list[str] = []
        for datei in dateien:
            try:
                daten = json.loads(datei.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            kandidaten = list(daten.get("manuelle_boxen") or []) + [daten.get("letzte_box") or ""]
            for url in kandidaten:
                if isinstance(url, str) and url.startswith("http") and url not in urls:
                    urls.append(url)
        neu = [u for u in urls if u not in self.einst["bekannte_boxen"]]
        self.einst.setzen(bekannte_boxen=self.einst["bekannte_boxen"] + neu, alte_geraete_geprueft=True)
        if neu:
            protokoll(f"{len(neu)} Gerät(e) aus der Einzelplatz-Variante übernommen: {', '.join(neu)}")
        else:
            protokoll("Keine Geräte aus der Einzelplatz-Variante gefunden.")

    def _suchen(self) -> None:
        try:
            protokoll("Lautsprechersuche gestartet …")
            bekannte = self.einst["manuelle_boxen"] + [
                u for u in self.einst["bekannte_boxen"] if u not in self.einst["manuelle_boxen"]]
            gefunden = renderer_suchen(timeout=4.0,
                                       zusatz_netze=self.einst["such_netze"],
                                       bekannte_urls=bekannte)
            gefunden += self._ports_neu_suchen(bekannte, gefunden)
            with self._sperre:
                for r in gefunden:
                    if r.location in self.boxen:
                        self.boxen[r.location].renderer = r   # Daten auffrischen
                    else:
                        self.boxen[r.location] = BoxZustand(renderer=r)
            # Gefundene Geraete dauerhaft merken (max. 50), damit sie beim naechsten Mal
            # auch ohne SSDP-Antwort direkt abgefragt werden
            gemerkt = self.einst["bekannte_boxen"]
            neu = [r.location for r in gefunden if r.location not in gemerkt]
            if neu:
                self.einst.setzen(bekannte_boxen=(gemerkt + neu)[-50:])
            protokoll(f"Lautsprechersuche fertig: {len(gefunden)} Gerät(e) gefunden"
                      + (f" ({len(bekannte)} gemerkte Adresse(n) direkt abgefragt)." if bekannte else "."))
        finally:
            with self._sperre:
                self.suche_laeuft = False
                self.letzte_suche = time.time()

    def _ports_neu_suchen(self, bekannte: list[str], gefunden: list[Renderer]) -> list[Renderer]:
        """
        Gemerkte/eingetragene Geraete-URLs, die nicht geantwortet haben, unter neuem Port suchen
        (der Port der Raumfeld-Boxen aendert sich offenbar bei einem Neustart).
        Gefundene neue URLs ersetzen die alten in den Einstellungen. Rueckgabe: neu gefundene Renderer.
        """
        def schluessel(url: str) -> tuple:
            teile = urllib.parse.urlparse(url)
            return teile.hostname, teile.path   # Host + Pfad (UUID) = dieselbe Box

        bereits = {schluessel(r.location) for r in gefunden}
        jetzt = time.time()
        veraltet = [u for u in dict.fromkeys(bekannte)
                    if schluessel(u) not in bereits
                    and jetzt - self._neusuche_fehlschlag.get(u, 0) > 600]   # 10 Min. Pause nach Fehlschlag
        if not veraltet:
            return []
        protokoll(f"Suche {len(veraltet)} gemerkte Box(en) unter neuem Port …")
        ergebnisse: dict[str, Renderer | None] = {}

        def suchen(url: str) -> None:
            ergebnisse[url] = port_neu_suchen(url)

        threads = [threading.Thread(target=suchen, args=(u,), daemon=True) for u in veraltet]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        neu: list[Renderer] = []
        ersetzungen: dict[str, str] = {}
        for alt, r in ergebnisse.items():
            if r is None:
                self._neusuche_fehlschlag[alt] = time.time()
                continue
            self._neusuche_fehlschlag.pop(alt, None)
            ersetzungen[alt] = r.location
            if schluessel(r.location) not in bereits:
                neu.append(r)
                bereits.add(schluessel(r.location))
        if ersetzungen:
            # Alte URLs in beiden Listen durch die neuen ersetzen (Reihenfolge bleibt, keine Doppelten)
            def tauschen(liste: list[str]) -> list[str]:
                return list(dict.fromkeys(ersetzungen.get(u, u) for u in liste))
            self.einst.setzen(manuelle_boxen=tauschen(self.einst["manuelle_boxen"]),
                              bekannte_boxen=tauschen(self.einst["bekannte_boxen"]))
            # Veraltete Eintraege aus der Lautsprecherliste nehmen (nur, wenn dort nichts laeuft)
            with self._sperre:
                for alt in ersetzungen:
                    box = self.boxen.get(alt)
                    if box and not (box.wiedergabe and box.wiedergabe.laeuft):
                        del self.boxen[alt]
        return neu

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
                # Titel "tidal:<ID>" loest der Stream-Server erst beim Abruf ueber Tidal auf
                self.server.aufloeser[TIDAL_PRAEFIX.rstrip(":")] = self.tidal.stream_adresse
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
        # Grosse Playlists: erst den Anfang laden und sofort starten, den Rest im Hintergrund
        # nachladen (das vollstaendige Einlesen kann ueber eine Minute dauern).
        zweistufig = (len(eingaben) == 1 and not einzeln and "list=" in eingaben[0])
        liste, fehler = titel_liste_aufbauen(eingaben, self._cookie_args(), einzeln,
                                             bis=ANFANG_TITEL if zweistufig else None)
        for f in fehler:
            protokoll(f"  Hinweis: {f}")
        if not liste:
            raise ValueError("Keine abspielbaren Titel gefunden. " + " ".join(fehler))

        meldung = self._liste_starten(box, liste, zufall, wer)
        if zweistufig and len(liste) >= ANFANG_TITEL:
            wiedergabe = box.wiedergabe
            threading.Thread(target=self._rest_nachladen,
                             args=(box, wiedergabe, eingaben[0], zufall), daemon=True).start()
            meldung += " Weitere Titel der Playlist werden nachgeladen …"
        return meldung

    def _rest_nachladen(self, box: BoxZustand, wiedergabe, url: str, zufall: bool) -> None:
        """Hintergrund: restliche Titel einer grossen Playlist laden und anhaengen."""
        beginn = time.monotonic()
        rest, _fehler = titel_liste_aufbauen([url], self._cookie_args(), ab=ANFANG_TITEL + 1)
        # Inzwischen etwas anderes gestartet? Dann nichts anhaengen.
        if box.wiedergabe is not wiedergabe or not wiedergabe.laeuft or not rest:
            return
        if zufall:
            random.shuffle(rest)
        wiedergabe.anhaengen(rest)
        protokoll(f"  {box.renderer.name}: {len(rest)} weitere Titel nachgeladen "
                  f"({time.monotonic() - beginn:.0f} s).")

    def _liste_starten(self, box: BoxZustand, liste: list[Titel], zufall: bool, wer: str) -> str:
        """Startet eine fertige Titelliste auf einem Lautsprecher (ersetzt dessen Warteschlange)."""
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

    # ------------------------------------------------------------ Tidal
    def tidal_status(self) -> dict:
        """Zustand des Tidal-Kontos fuer die Oberflaeche."""
        anmeldung = self.tidal.anmeldung
        if anmeldung and not anmeldung["fehler"] and time.time() > anmeldung["bis"]:
            anmeldung = dict(anmeldung, fehler="Der Code ist abgelaufen – bitte neu anmelden.")
        return {"verfuegbar": self.tidal.verfuegbar(),
                "angemeldet": self.tidal.angemeldet(),
                "benutzer": self.tidal.benutzer,
                "anmeldung": anmeldung,
                "qualitaet": self.tidal.qualitaet}

    def tidal_anmelden_start(self, wer: str) -> dict:
        protokoll(f"{wer}: Tidal-Anmeldung angefordert.")
        return self.tidal.anmelden_start()

    def tidal_abmelden(self, wer: str) -> None:
        self.tidal.abmelden()
        protokoll(f"{wer}: Tidal-Konto getrennt.")

    def tidal_playlists(self) -> list[dict]:
        return self.tidal.playlists()

    def tidal_abspielen(self, location: str, eingabe: str, zufall: bool, wer: str) -> str:
        """
        Tidal-Playlist, -Favoriten, -Link oder -Suche auf einem Raumfeld-Lautsprecher abspielen.
        Der Ton kommt direkt von Tidal (nicht ueber YouTube); ffmpeg wandelt ihn in MP3.
        """
        self._ruhezeit_sperre()
        if finde_programm("ffmpeg") is None:
            raise ValueError("ffmpeg fehlt auf dem Server – bitte neu installieren.")
        box = self._box(location)
        titel, beschreibung = self.tidal.titel_liste(eingabe)
        if not titel:
            raise ValueError("Keine abspielbaren Tidal-Titel gefunden.")
        protokoll(f"{wer}: Tidal {beschreibung} ({len(titel)} Titel) auf {box.renderer.name}")
        liste = [Titel(f"{TIDAL_PRAEFIX}{kennung}", name) for kennung, name in titel]
        meldung = self._liste_starten(box, liste, zufall, wer)
        return f"Tidal: {beschreibung} – {meldung}"

    # ------------------------------------------------------------ Spotify
    def spotify_status(self) -> dict:
        return {"client_id": bool(self.einst["spotify_client_id"]),
                "angemeldet": self.spotify.angemeldet(),
                "anmeldung_laeuft": self._spotify_anmeldung is not None}

    def spotify_client_id_setzen(self, client_id: str) -> None:
        client_id = client_id.strip()
        if client_id and not client_id.isalnum():
            raise ValueError("Die Client-ID besteht nur aus Buchstaben und Ziffern.")
        self.einst.setzen(spotify_client_id=client_id)
        self.spotify.client_id = client_id
        protokoll("Spotify-Client-ID geändert.")

    def spotify_anmelden_start(self) -> str:
        """Liefert die Anmelde-Adresse; Verifier/State bleiben im Speicher des Dienstes."""
        url, verifier, zustand = self.spotify.anmelde_url()
        self._spotify_anmeldung = (verifier, zustand)
        return url

    def spotify_anmelden_ende(self, rueckruf_adresse: str, wer: str) -> None:
        if self._spotify_anmeldung is None:
            raise ValueError("Bitte zuerst „Bei Spotify anmelden“ klicken.")
        verifier, zustand = self._spotify_anmeldung
        self.spotify.anmeldung_abschliessen(rueckruf_adresse, verifier, zustand)
        self._spotify_anmeldung = None
        protokoll(f"{wer}: Spotify-Konto verbunden (gilt für alle).")

    def spotify_abmelden(self, wer: str) -> None:
        self.spotify.abmelden()
        protokoll(f"{wer}: Spotify-Konto getrennt.")

    def spotify_playlists(self) -> list[dict]:
        return [{"id": p["id"], "name": p.get("name") or "(ohne Namen)",
                 "anzahl": (p.get("tracks") or p.get("items") or {}).get("total", 0)}
                for p in self.spotify.playlists() if p.get("id")]

    def spotify_geraete(self) -> list[dict]:
        return [{"id": g["id"], "name": g.get("name", "?"), "aktiv": bool(g.get("is_active"))}
                for g in self.spotify.geraete() if g.get("id")]

    def spotify_via_youtube(self, location: str, playlist_id: str, zufall: bool, wer: str) -> str:
        """
        Spotify-Playlist auf einem Raumfeld-Lautsprecher abspielen: Titelnamen von Spotify
        lesen und jeden Titel beim Abspielen ueber die YouTube-Suche holen (Spotify-Audio
        selbst ist DRM-geschuetzt und nicht abgreifbar).
        """
        self._ruhezeit_sperre()
        box = self._box(location)
        namen = self.spotify.playlist_titel(playlist_id)
        if not namen:
            raise ValueError("Die Playlist enthält keine lesbaren Titel.")
        protokoll(f"{wer}: Spotify-Playlist ({len(namen)} Titel) über YouTube auf {box.renderer.name}")
        # "ytsearch1:" laesst yt-dlp erst beim Abspielen den ersten Treffer suchen
        liste = [Titel(f"ytsearch1:{n}", n) for n in namen]
        return self._liste_starten(box, liste, zufall, wer)

    def spotify_connect_abspielen(self, geraet_id: str, playlist_id: str, wer: str) -> str:
        """Playlist direkt auf einem Spotify-Connect-Geraet starten (Spotify Premium noetig)."""
        self._ruhezeit_sperre()
        self.spotify.wiedergabe_starten(geraet_id, playlist_id)
        self.spotify_geraet = geraet_id
        protokoll(f"{wer}: Spotify Connect gestartet (Gerät {geraet_id[:8]}…)")
        return "Spotify-Wiedergabe gestartet."

    def spotify_steuern(self, geraet_id: str, aktion: str) -> None:
        funktionen = {"pause": self.spotify.pause, "weiter": self.spotify.fortsetzen,
                      "naechster": self.spotify.naechster, "voriger": self.spotify.voriger}
        if aktion not in funktionen:
            raise ValueError(f"Unbekannte Aktion: {aktion}")
        if aktion != "pause":
            self._ruhezeit_sperre()
        funktionen[aktion](geraet_id)

    def _ruhezeit_sperre(self) -> None:
        """Wirft ValueError, wenn gerade eine Ruhezeit gilt."""
        regel = aktive_ruhezeit(self.einst["ruhezeiten"])
        if regel:
            raise ValueError(f"Ruhezeit ({ruhezeit_text(regel)}) – Abspielen ist gerade gesperrt.")

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

    def einstellungen_speichern(self, neu: dict) -> bool:
        """
        Prueft und speichert Einstellungen aus der Web-Oberflaeche.
        Rueckgabe: True, wenn ein Port geaendert wurde (wirkt erst nach Neustart des Dienstes).
        """
        werte: dict = {}
        # Ports: beide pruefen und gegeneinander abgleichen
        web_port = port_pruefen(neu.get("web_port", self.einst["web_port"]), "Port der Web-Oberfläche")
        stream_port = port_pruefen(neu.get("stream_port", self.einst["stream_port"]), "Stream-Port")
        if web_port == stream_port:
            raise ValueError("Web-Oberfläche und Stream brauchen verschiedene Ports.")
        neustart_noetig = (web_port != self.einst["web_port"] or stream_port != self.einst["stream_port"])
        werte["web_port"], werte["stream_port"] = web_port, stream_port
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
        if "tidal_qualitaet" in neu:
            if neu["tidal_qualitaet"] not in TIDAL_QUALITAETEN:
                raise ValueError("Ungültige Tidal-Qualität.")
            werte["tidal_qualitaet"] = neu["tidal_qualitaet"]
            self.tidal.qualitaet_setzen(neu["tidal_qualitaet"])
        if "favoriten" in neu:
            werte["favoriten"] = [{"name": str(f["name"])[:100], "url": str(f["url"])[:1000]}
                                  for f in neu["favoriten"] if f.get("url")]
        netze_neu = "such_netze" in werte and werte["such_netze"] != self.einst["such_netze"]
        self.einst.setzen(**werte)
        if netze_neu:
            # Geaenderte Netze sofort durchsuchen, nicht erst beim naechsten Klick auf "Suchen"
            self.suchen_im_hintergrund()
        if "bitrate" in werte and self.server:
            self.server.bitrate = werte["bitrate"]  # gilt ab dem naechsten Titel
        protokoll(f"Einstellungen geändert: {', '.join(werte) or '–'}")
        # Neue Ruhezeit greift sofort
        self._ruhezeit_pruefen_einmal()
        return neustart_noetig

    def neu_starten(self) -> None:
        """
        Beendet den Prozess nach kurzer Verzoegerung (damit die HTTP-Antwort noch rausgeht).
        Der Exit-Code 1 gilt fuer WinSW als Absturz -> es startet den Dienst nach
        10 Sekunden neu (<onfailure action="restart"> in RaumfeldRemote-Dienst.xml).
        So greifen geaenderte Ports, ohne dass jemand an den Server muss.
        """
        protokoll("Dienst wird auf Wunsch neu gestartet …")
        self.alles_stoppen("Dienst wird neu gestartet.")
        threading.Timer(1.5, os._exit, args=(1,)).start()

    # ------------------------------------------------------------ Hintergrund
    def _ruhezeit_pruefen_einmal(self) -> None:
        regel = aktive_ruhezeit(self.einst["ruhezeiten"])
        if regel:
            anzahl = self.alles_stoppen(f"Ruhezeit ({ruhezeit_text(regel)}) – automatisch gestoppt.")
            if self.spotify_geraet:
                try:
                    self.spotify.pause(self.spotify_geraet)
                    protokoll("Ruhezeit: Spotify-Wiedergabe pausiert.")
                except (SpotifyFehler, OSError):
                    pass  # laeuft evtl. gar nicht mehr
                self.spotify_geraet = ""
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
