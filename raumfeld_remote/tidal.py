# -*- coding: utf-8 -*-
"""
tidal.py - Tidal-Anbindung fuer den zentralen Dienst (ein gemeinsames Konto).

Nutzt die Bibliothek "tidalapi" (inoffizielle Tidal-Schnittstelle, wie sie auch
andere Abspielprogramme verwenden). Wichtig:
  - Das ist NICHT die offizielle Entwickler-Schnittstelle von Tidal. Sie kann sich
    jederzeit aendern; die Nutzung verstoesst vermutlich gegen Tidals Nutzungsbedingungen.
    Ausdruecklicher Wunsch des Nutzers (siehe HANDOVER).
  - Anmeldung per Geraete-Code: Der Dienst holt einen Code, man oeffnet auf einem
    beliebigen Geraet link.tidal.com, gibt den Code ein und meldet sich dort bei Tidal an.
    Der Server braucht dafuer keinen Browser. Danach liegt der Zugang dauerhaft in
    <Datenordner>/tidal_sitzung.json (wird automatisch erneuert).
  - Abspielen: Pro Titel wird beim Abruf durch den Lautsprecher die Stream-Adresse bei
    Tidal geholt (sie ist nur kurz gueltig) und von ffmpeg in MP3 umgewandelt.

Titel in der Warteschlange haben die Quelle "tidal:<Titel-ID>".
"""

from __future__ import annotations

import json
import re
import tempfile
import threading
import time
from pathlib import Path

from .protokoll import protokoll

# Praefix fuer Warteschlangen-Eintraege, die der Stream-Server ueber Tidal aufloest
PRAEFIX = "tidal:"

# Sonder-ID fuer "Meine Titel" (Favoriten) in der Playlist-Auswahl
FAVORITEN = "favoriten"

# Erlaubte Tonqualitaeten (Tidal-Bezeichnungen). LOSSLESS = FLAC 16 bit/44,1 kHz,
# HIGH = AAC 320 kbit/s. Die Boxen bekommen ohnehin MP3 (siehe stream_server.py).
QUALITAETEN = ("HIGH", "LOSSLESS")

# Hoechstzahl Titel pro Playlist/Album/Favoriten (Schutz vor sehr langen Ladezeiten)
MAX_TITEL = 500


class TidalFehler(Exception):
    """Fehler mit verstaendlicher deutscher Meldung fuer die Oberflaeche."""


def _tidalapi():
    """
    tidalapi erst bei Bedarf laden: So laeuft der Rest des Dienstes auch dann,
    wenn die Bibliothek fehlt (z. B. beim Entwickeln), und meldet nur Tidal als nicht verfuegbar.
    """
    try:
        import tidalapi  # noqa: PLC0415 - bewusst verzoegerter Import
    except ImportError as exc:
        raise TidalFehler("Die Bibliothek „tidalapi“ fehlt – Tidal ist in dieser Installation nicht verfügbar.") from exc
    return tidalapi


def titel_name(track) -> str:
    """Anzeigename 'Interpret – Titel' fuer einen tidalapi-Track."""
    interpret = getattr(getattr(track, "artist", None), "name", "") or ""
    titel = getattr(track, "full_name", None) or getattr(track, "name", "") or "?"
    return f"{interpret} – {titel}" if interpret else titel


class Tidal:
    """Gemeinsames Tidal-Konto des Dienstes. Alle Methoden sind thread-sicher."""

    def __init__(self, sitzungs_datei: Path, qualitaet: str = "LOSSLESS") -> None:
        self.datei = sitzungs_datei
        self.qualitaet = qualitaet if qualitaet in QUALITAETEN else "LOSSLESS"
        self._sperre = threading.RLock()
        self._sitzung = None          # tidalapi.Session, sobald angemeldet
        self._geladen = False         # Sitzungsdatei schon einmal gelesen?
        # Laufende Anmeldung per Geraete-Code: {"code", "url", "bis", "fehler"}
        self.anmeldung: dict | None = None
        self.benutzer = ""            # Anzeigename/E-Mail des angemeldeten Kontos (falls bekannt)
        # Temporaere HLS-Dateien (bei MPD-Streams), werden beim naechsten Aufruf aufgeraeumt
        self._hls_dateien: list[Path] = []

    # ------------------------------------------------------------ Sitzung
    def _neue_sitzung(self):
        """Neue tidalapi-Sitzung mit der eingestellten Qualitaet."""
        tidalapi = _tidalapi()
        konfig = tidalapi.Config(quality=self.qualitaet)
        return tidalapi.Session(konfig)

    def _sitzung_speichern(self, sitzung) -> None:
        """Zugangsdaten dauerhaft speichern (Datei liegt im geschuetzten Datenordner)."""
        daten = {
            "token_type": sitzung.token_type,
            "access_token": sitzung.access_token,
            "refresh_token": sitzung.refresh_token,
            "benutzer": self.benutzer,
        }
        temp = self.datei.with_suffix(".tmp")
        temp.write_text(json.dumps(daten, indent=2), encoding="utf-8")
        temp.replace(self.datei)

    def _benutzer_merken(self, sitzung) -> None:
        """Anzeigename des Kontos fuer die Oberflaeche ermitteln (nicht kritisch)."""
        try:
            nutzer = sitzung.user
            self.benutzer = (getattr(nutzer, "email", None) or getattr(nutzer, "username", None)
                             or getattr(nutzer, "first_name", None) or f"Benutzer {nutzer.id}")
        except Exception:  # noqa: BLE001 - nur Anzeige
            self.benutzer = ""

    def _sitzung_holen(self):
        """Angemeldete Sitzung zurueckgeben; beim ersten Aufruf aus der Datei laden."""
        with self._sperre:
            if self._sitzung is not None:
                return self._sitzung
            if self._geladen or not self.datei.is_file():
                self._geladen = True
                return None
            self._geladen = True
            try:
                daten = json.loads(self.datei.read_text(encoding="utf-8"))
                sitzung = self._neue_sitzung()
                ok = sitzung.load_oauth_session(daten["token_type"], daten["access_token"],
                                                daten.get("refresh_token"))
            except TidalFehler:
                raise
            except Exception as exc:  # noqa: BLE001 - Netz, abgelaufener Zugang ...
                protokoll(f"✗ Tidal-Zugang konnte nicht geladen werden: {exc}")
                return None
            if not ok:
                protokoll("✗ Tidal-Zugang ist abgelaufen – bitte unter „Konten“ neu anmelden.")
                return None
            self._sitzung = sitzung
            self.benutzer = daten.get("benutzer", "")
            # Zugriffsschluessel kann beim Laden erneuert worden sein -> sichern
            self._sitzung_speichern(sitzung)
            return sitzung

    def _sitzung_pflicht(self):
        """Wie _sitzung_holen, aber mit Fehler, wenn nicht angemeldet."""
        sitzung = self._sitzung_holen()
        if sitzung is None:
            raise TidalFehler("Tidal ist nicht verbunden – unter „Konten“ bei Tidal anmelden.")
        return sitzung

    def _nach_aufruf_sichern(self, sitzung, vorher: str) -> None:
        """tidalapi erneuert abgelaufene Schluessel selbst – dann die neuen speichern."""
        if sitzung.access_token != vorher:
            self._sitzung_speichern(sitzung)

    def angemeldet(self) -> bool:
        try:
            return self._sitzung_holen() is not None
        except TidalFehler:
            return False

    def verfuegbar(self) -> bool:
        """Ist die Bibliothek tidalapi installiert?"""
        try:
            _tidalapi()
            return True
        except TidalFehler:
            return False

    def qualitaet_setzen(self, qualitaet: str) -> None:
        if qualitaet not in QUALITAETEN:
            raise TidalFehler("Unbekannte Tidal-Qualität.")
        with self._sperre:
            self.qualitaet = qualitaet
            if self._sitzung is not None:
                self._sitzung.audio_quality = qualitaet

    # ------------------------------------------------------------ Anmeldung
    def anmelden_start(self) -> dict:
        """
        Startet die Anmeldung per Geraete-Code. Rueckgabe: {"code", "url", "bis"}.
        Im Hintergrund wird gewartet, bis die Anmeldung auf link.tidal.com bestaetigt ist.
        """
        sitzung = self._neue_sitzung()
        try:
            link = sitzung.get_link_login()
        except Exception as exc:  # noqa: BLE001
            raise TidalFehler(f"Tidal-Anmeldung konnte nicht gestartet werden: {exc}") from exc
        url = link.verification_uri_complete
        if not url.startswith("http"):
            url = "https://" + url
        with self._sperre:
            self.anmeldung = {"code": link.user_code, "url": url,
                              "bis": time.time() + link.expires_in, "fehler": ""}
        protokoll(f"Tidal-Anmeldung gestartet (Code {link.user_code}, gültig {int(link.expires_in // 60)} Min.).")
        threading.Thread(target=self._anmeldung_abwarten, args=(sitzung, link), daemon=True).start()
        return {"code": link.user_code, "url": url, "bis": self.anmeldung["bis"]}

    def _anmeldung_abwarten(self, sitzung, link) -> None:
        """Hintergrund: fragt bei Tidal nach, bis der Code bestaetigt wurde oder abgelaufen ist."""
        try:
            ok = sitzung.process_link_login(link, until_expiry=True)
            if not ok:
                raise TidalFehler("Tidal hat die Anmeldung nicht bestätigt.")
            sitzung.audio_quality = self.qualitaet
            with self._sperre:
                self._benutzer_merken(sitzung)
                self._sitzung = sitzung
                self._geladen = True
                self._sitzung_speichern(sitzung)
                self.anmeldung = None
            protokoll(f"Tidal verbunden{': ' + self.benutzer if self.benutzer else ''}.")
        except TimeoutError:
            with self._sperre:
                if self.anmeldung:
                    self.anmeldung["fehler"] = "Der Code ist abgelaufen – bitte neu anmelden."
            protokoll("✗ Tidal-Anmeldung: Code abgelaufen.")
        except Exception as exc:  # noqa: BLE001
            with self._sperre:
                if self.anmeldung:
                    self.anmeldung["fehler"] = f"Anmeldung fehlgeschlagen: {exc}"
            protokoll(f"✗ Tidal-Anmeldung fehlgeschlagen: {exc}")

    def abmelden(self) -> None:
        """Zugang vergessen (Datei loeschen)."""
        with self._sperre:
            self._sitzung = None
            self.anmeldung = None
            self.benutzer = ""
            self.datei.unlink(missing_ok=True)

    # ------------------------------------------------------------ Inhalte
    def playlists(self) -> list[dict]:
        """Eigene und gemerkte Playlists, vorne "Meine Titel" (Favoriten)."""
        sitzung = self._sitzung_pflicht()
        vorher = sitzung.access_token
        ergebnis = [{"id": FAVORITEN, "name": "♥ Meine Titel (Favoriten)", "anzahl": None}]
        try:
            offset = 0
            while offset < 1000:   # in 50er-Schritten (Grenze der Schnittstelle)
                seite = sitzung.user.playlist_and_favorite_playlists(offset=offset)
                for p in seite:
                    ergebnis.append({"id": p.id, "name": p.name, "anzahl": getattr(p, "num_tracks", None)})
                if len(seite) < 50:
                    break
                offset += 50
        except Exception as exc:  # noqa: BLE001
            raise TidalFehler(f"Tidal-Playlists konnten nicht gelesen werden: {exc}") from exc
        self._nach_aufruf_sichern(sitzung, vorher)
        return ergebnis

    def _alle(self, abruf) -> list:
        """Seitenweise abrufen (abruf(limit, offset) -> Liste), bis MAX_TITEL erreicht."""
        alle: list = []
        while len(alle) < MAX_TITEL:
            seite = abruf(100, len(alle))
            alle.extend(seite)
            if len(seite) < 100:
                break
        return alle[:MAX_TITEL]

    def titel_liste(self, eingabe: str) -> tuple[list[tuple[str, str]], str]:
        """
        Wandelt eine Auswahl oder Eingabe in Titel um. Rueckgabe: ([(Titel-ID, Anzeigename)], Beschreibung).
        Erlaubt:
          - "favoriten" oder eine Playlist-ID (aus der Auswahlliste)
          - Tidal-Links: .../playlist/<uuid>, .../album/<id>, .../track/<id>, .../artist/<id>, .../mix/<id>
          - sonst: Suchbegriff -> Interpret (beste Treffer) bzw. passende Titel
        """
        sitzung = self._sitzung_pflicht()
        vorher = sitzung.access_token
        eingabe = eingabe.strip()
        if not eingabe:
            raise TidalFehler("Bitte eine Playlist wählen oder einen Suchbegriff/Link eingeben.")
        try:
            tracks, beschreibung = self._titel_aufloesen(sitzung, eingabe)
        except TidalFehler:
            raise
        except Exception as exc:  # noqa: BLE001 - z. B. ObjectNotFound, Netzfehler
            raise TidalFehler(f"Tidal: {exc}") from exc
        self._nach_aufruf_sichern(sitzung, vorher)
        # Nur abspielbare Titel (z. B. keine regional gesperrten)
        liste = [(str(t.id), titel_name(t)) for t in tracks
                 if getattr(t, "available", True) and t.__class__.__name__ == "Track"]
        return liste, beschreibung

    def _titel_aufloesen(self, sitzung, eingabe: str) -> tuple[list, str]:
        """Hilfsfunktion zu titel_liste (ohne Fehlerbehandlung)."""
        if eingabe == FAVORITEN:
            return self._alle(lambda n, o: sitzung.user.favorites.tracks(limit=n, offset=o)), "Meine Titel"

        # Tidal-Link? z. B. https://tidal.com/browse/playlist/<uuid> oder listen.tidal.com/album/123
        treffer = re.search(r"tidal\.com/(?:browse/)?(playlist|album|track|artist|mix)/([\w-]+)", eingabe)
        if treffer:
            art, kennung = treffer.groups()
            eingabe_art = art
        elif re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", eingabe):
            eingabe_art, kennung = "playlist", eingabe     # ID aus der Playlist-Auswahl
        else:
            eingabe_art, kennung = "suche", eingabe

        if eingabe_art == "playlist":
            p = sitzung.playlist(kennung)
            return self._alle(lambda n, o: p.tracks(limit=n, offset=o)), f"Playlist „{p.name}“"
        if eingabe_art == "album":
            a = sitzung.album(kennung)
            return a.tracks(), f"Album „{a.name}“"
        if eingabe_art == "track":
            t = sitzung.track(kennung)
            return [t], titel_name(t)
        if eingabe_art == "artist":
            k = sitzung.artist(kennung)
            return k.get_top_tracks(limit=50), f"Beliebteste Titel von {k.name}"
        if eingabe_art == "mix":
            m = sitzung.mix(kennung)
            return m.items(), f"Mix „{getattr(m, 'title', kennung)}“"

        # Suchbegriff: passt er genau auf einen Interpreten, dessen beliebteste Titel,
        # sonst die besten Titel-Treffer
        tidalapi = _tidalapi()
        ergebnis = sitzung.search(kennung, models=[tidalapi.Artist, tidalapi.Track], limit=25)
        interpreten = ergebnis.get("artists") or []
        if interpreten and interpreten[0].name.strip().lower() == kennung.lower():
            k = interpreten[0]
            return k.get_top_tracks(limit=50), f"Beliebteste Titel von {k.name}"
        tracks = ergebnis.get("tracks") or []
        if not tracks:
            raise TidalFehler(f"Keine Treffer bei Tidal für „{kennung}“.")
        return tracks, f"Suche „{kennung}“"

    # ------------------------------------------------------------ Stream
    def stream_adresse(self, titel_id: str) -> str:
        """
        Liefert eine Eingabe fuer ffmpeg: direkte Datei-URL (FLAC/AAC) oder den Pfad einer
        temporaeren HLS-Liste (bei MPEG-DASH-Streams). Wird erst beim Abspielen aufgerufen,
        weil die Adressen nur kurz gueltig sind.
        """
        sitzung = self._sitzung_pflicht()
        vorher = sitzung.access_token
        self._hls_aufraeumen()
        try:
            track = sitzung.track(titel_id)
            # 1. Weg: einfache Datei-URL (klappt mit Geraete-Anmeldung bei HIGH/LOSSLESS)
            try:
                url = track.get_url()
                self._nach_aufruf_sichern(sitzung, vorher)
                return url
            except Exception as exc:  # noqa: BLE001 - weiter mit Weg 2
                protokoll(f"  Tidal: direkte Adresse nicht verfügbar ({exc}), versuche Stream-Manifest …")
            # 2. Weg: Stream-Manifest (BTS = direkte URL, MPD = Segmente -> HLS-Liste fuer ffmpeg)
            manifest = track.get_stream().get_stream_manifest()
            if manifest.is_encrypted:
                raise TidalFehler("Dieser Tidal-Titel ist verschlüsselt und kann nicht abgespielt werden.")
            if manifest.is_mpd:
                datei = Path(tempfile.gettempdir()) / f"raumfeld_tidal_{titel_id}_{int(time.time())}.m3u8"
                datei.write_text(manifest.get_hls(), encoding="utf-8")
                self._hls_dateien.append(datei)
                self._nach_aufruf_sichern(sitzung, vorher)
                return str(datei)
            self._nach_aufruf_sichern(sitzung, vorher)
            return manifest.get_urls()[0]
        except TidalFehler:
            raise
        except Exception as exc:  # noqa: BLE001
            raise TidalFehler(f"Tidal-Stream für Titel {titel_id} nicht verfügbar: {exc}") from exc

    def _hls_aufraeumen(self) -> None:
        """Alte temporaere HLS-Listen loeschen (aelter als 6 Stunden)."""
        grenze = time.time() - 6 * 3600
        for datei in list(self._hls_dateien):
            try:
                if datei.stat().st_mtime < grenze:
                    datei.unlink()
                    self._hls_dateien.remove(datei)
            except OSError:
                self._hls_dateien.remove(datei)
