# -*- coding: utf-8 -*-
"""
spotify.py - Anbindung an die Spotify Web API (Anmeldung per PKCE).

WICHTIG - was dieses Modul kann und was nicht:
  * Spotify liefert seine Audiodaten verschluesselt (DRM). Man kann sie nicht
    wie YouTube per yt-dlp holen. Dieses Modul steuert deshalb nur ueber die
    offizielle Web API:
      - Playlists des Kontos auflisten
      - Wiedergabe auf einem "Spotify Connect"-Geraet starten/steuern
      - Titelnamen einer Playlist lesen (damit sie ersatzweise ueber YouTube
        Music abgespielt werden koennen)
  * Die Web-API-Wiedergabesteuerung erfordert nach meinem Kenntnisstand
    Spotify Premium.
  * Ob ein Raumfeld-Lautsprecher in der Geraeteliste von Spotify erscheint,
    haengt von der Firmware ab und konnte hier nicht getestet werden.

Einrichtung (einmalig, siehe README):
  1. App im Spotify Developer Dashboard anlegen
  2. Redirect-URI eintragen:  http://127.0.0.1:8888/callback
  3. Client-ID in der Oberflaeche eintragen (ein Client-Secret ist NICHT noetig)
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import json
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

# Muss exakt mit dem Eintrag im Spotify Developer Dashboard uebereinstimmen
REDIRECT_PORT = 8888
REDIRECT_URI = f"http://127.0.0.1:{REDIRECT_PORT}/callback"

# Benoetigte Berechtigungen
SCOPES = ("user-read-playback-state user-modify-playback-state "
          "playlist-read-private playlist-read-collaborative")

API = "https://api.spotify.com/v1"
TOKEN_URL = "https://accounts.spotify.com/api/token"
AUTH_URL = "https://accounts.spotify.com/authorize"


class SpotifyFehler(Exception):
    """Fehler bei der Kommunikation mit Spotify (Text ist anzeigbar)."""


def playlist_id_aus_text(text: str) -> str | None:
    """Zieht die Playlist-ID aus einem Link ('.../playlist/ID?si=...') oder URI."""
    treffer = re.search(r"playlist[/:]([A-Za-z0-9]+)", text)
    return treffer.group(1) if treffer else None


class Spotify:
    """Minimaler Spotify-Client (nur die benoetigten Funktionen)."""

    def __init__(self, token_datei: Path, client_id: str) -> None:
        self.token_datei = token_datei
        self.client_id = client_id
        self._token: dict = {}
        try:
            self._token = json.loads(token_datei.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass

    # ------------------------------------------------------------ Anmeldung
    def angemeldet(self) -> bool:
        return bool(self._token.get("refresh_token"))

    def abmelden(self) -> None:
        self._token = {}
        try:
            self.token_datei.unlink()
        except OSError:
            pass

    def _token_speichern(self, antwort: dict) -> None:
        """Merkt sich Token + Ablaufzeit; behaelt den alten Refresh-Token falls keiner kommt."""
        neu = dict(self._token)
        neu["access_token"] = antwort["access_token"]
        neu["laeuft_ab"] = time.time() + int(antwort.get("expires_in", 3600)) - 30
        if antwort.get("refresh_token"):
            neu["refresh_token"] = antwort["refresh_token"]
        self._token = neu
        try:
            self.token_datei.write_text(json.dumps(neu), encoding="utf-8")
        except OSError:
            # z. B. gemeinsames Token ohne Schreibrechte: Token bleibt im Speicher gueltig
            pass

    def _token_anfrage(self, formular: dict) -> dict:
        daten = urllib.parse.urlencode(formular).encode("ascii")
        anfrage = urllib.request.Request(TOKEN_URL, data=daten, method="POST")
        try:
            with urllib.request.urlopen(anfrage, timeout=15) as antwort:
                return json.loads(antwort.read())
        except urllib.error.HTTPError as exc:
            raise SpotifyFehler(
                f"Anmeldung fehlgeschlagen (HTTP {exc.code}): "
                f"{exc.read().decode('utf-8', 'replace')[:200]}") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise SpotifyFehler(f"Spotify nicht erreichbar: {exc}") from exc

    def anmelden(self, timeout: float = 180.0) -> None:
        """
        Oeffnet den Browser zur Anmeldung und wartet auf den Rueckruf.
        Blockiert bis zu 'timeout' Sekunden -> in einem Thread aufrufen!
        """
        if not self.client_id:
            raise SpotifyFehler("Bitte zuerst die Client-ID eintragen.")

        # PKCE: zufaelliger "Verifier" und dessen SHA256-Hash als "Challenge"
        verifier = secrets.token_urlsafe(64)[:100]
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode()
        zustand = secrets.token_urlsafe(16)
        ergebnis: dict[str, str] = {}

        class RueckrufHandler(http.server.BaseHTTPRequestHandler):
            """Faengt die Weiterleitung von Spotify mit dem 'code' ab."""
            def do_GET(self):  # noqa: N802
                abfrage = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                for schluessel in ("code", "state", "error"):
                    if schluessel in abfrage:
                        ergebnis[schluessel] = abfrage[schluessel][0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write("<html><body style='font-family:sans-serif'>"
                                 "<h2>Raumfeld Remote</h2>"
                                 "<p>Anmeldung abgeschlossen – dieses Fenster kann "
                                 "geschlossen werden.</p></body></html>".encode("utf-8"))

            def log_message(self, fmt, *args):  # keine Konsolenausgabe
                return

        try:
            server = http.server.HTTPServer(("127.0.0.1", REDIRECT_PORT), RueckrufHandler)
        except OSError as exc:
            raise SpotifyFehler(f"Port {REDIRECT_PORT} ist belegt: {exc}") from exc
        server.timeout = 1.0

        parameter = urllib.parse.urlencode({
            "client_id": self.client_id, "response_type": "code",
            "redirect_uri": REDIRECT_URI, "scope": SCOPES,
            "code_challenge_method": "S256", "code_challenge": challenge,
            "state": zustand})
        webbrowser.open(f"{AUTH_URL}?{parameter}")

        ende = time.monotonic() + timeout
        try:
            while "code" not in ergebnis and "error" not in ergebnis \
                    and time.monotonic() < ende:
                server.handle_request()
        finally:
            server.server_close()

        if "error" in ergebnis:
            raise SpotifyFehler(f"Anmeldung abgelehnt: {ergebnis['error']}")
        if "code" not in ergebnis:
            raise SpotifyFehler("Zeitüberschreitung bei der Anmeldung.")
        if ergebnis.get("state") != zustand:
            raise SpotifyFehler("Ungültige Antwort (state stimmt nicht überein).")

        self._token_speichern(self._token_anfrage({
            "client_id": self.client_id, "grant_type": "authorization_code",
            "code": ergebnis["code"], "redirect_uri": REDIRECT_URI,
            "code_verifier": verifier}))

    def _gueltiges_token(self) -> str:
        """Liefert ein gueltiges Access-Token (erneuert es bei Bedarf)."""
        if not self.angemeldet():
            raise SpotifyFehler("Nicht bei Spotify angemeldet.")
        if time.time() >= self._token.get("laeuft_ab", 0):
            self._token_speichern(self._token_anfrage({
                "client_id": self.client_id, "grant_type": "refresh_token",
                "refresh_token": self._token["refresh_token"]}))
        return self._token["access_token"]

    # ------------------------------------------------------------ API-Zugriff
    def _anfrage(self, methode: str, pfad: str, parameter: dict | None = None,
                 body: dict | None = None):
        """Allgemeiner API-Aufruf. Liefert geparstes JSON oder None (bei 204)."""
        url = pfad if pfad.startswith("http") else API + pfad
        if parameter:
            url += "?" + urllib.parse.urlencode(parameter)
        daten = json.dumps(body).encode("utf-8") if body is not None else None
        anfrage = urllib.request.Request(
            url, data=daten, method=methode,
            headers={"Authorization": f"Bearer {self._gueltiges_token()}",
                     "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(anfrage, timeout=15) as antwort:
                inhalt = antwort.read()
                return json.loads(inhalt) if inhalt else None
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", "replace")[:250]
            raise SpotifyFehler(f"Spotify-API Fehler HTTP {exc.code}: {text}") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise SpotifyFehler(f"Spotify nicht erreichbar: {exc}") from exc

    # ------------------------------------------------------------ Funktionen
    def geraete(self) -> list[dict]:
        """Verfuegbare Spotify-Connect-Geraete: [{'id','name','is_active',...}]"""
        antwort = self._anfrage("GET", "/me/player/devices") or {}
        return antwort.get("devices", [])

    def playlists(self, maximal: int = 200) -> list[dict]:
        """Playlists des Kontos: [{'id','name','tracks'...}]"""
        ergebnis: list[dict] = []
        offset = 0
        while offset < maximal:
            seite = self._anfrage("GET", "/me/playlists",
                                  {"limit": 50, "offset": offset}) or {}
            eintraege = seite.get("items", [])
            ergebnis.extend(e for e in eintraege if e)
            if not seite.get("next") or not eintraege:
                break
            offset += 50
        return ergebnis

    def playlist_titel(self, playlist_id: str, maximal: int = 500) -> list[str]:
        """
        Liefert 'Kuenstler - Titel' fuer jeden Eintrag der Playlist.
        Hinweis: Spotify hat die API fuer Entwickler-Apps in den letzten Jahren
        mehrfach eingeschraenkt. Ich weiss nicht sicher, welcher Endpunkt aktuell
        fuer welche Playlists erlaubt ist - darum wird '/tracks' und danach
        '/items' versucht.
        """
        letzter_fehler: SpotifyFehler | None = None
        for endpunkt in ("tracks", "items"):
            try:
                return self._titel_seiten(f"/playlists/{playlist_id}/{endpunkt}", maximal)
            except SpotifyFehler as exc:
                letzter_fehler = exc
        raise letzter_fehler or SpotifyFehler("Playlist konnte nicht gelesen werden.")

    def _titel_seiten(self, pfad: str, maximal: int) -> list[str]:
        namen: list[str] = []
        offset = 0
        while offset < maximal:
            seite = self._anfrage("GET", pfad, {"limit": 100, "offset": offset}) or {}
            eintraege = seite.get("items", [])
            for eintrag in eintraege:
                # Je nach Endpunkt heisst das Feld 'track' oder 'item'
                t = eintrag.get("track") or eintrag.get("item")
                if not t or not t.get("name"):
                    continue  # lokale/entfernte Titel ueberspringen
                kuenstler = ", ".join(k["name"] for k in t.get("artists", []))
                namen.append(f"{kuenstler} - {t['name']}" if kuenstler else t["name"])
            if not seite.get("next") or not eintraege:
                break
            offset += 100
        return namen

    def wiedergabe_starten(self, geraet_id: str, playlist_id: str) -> None:
        """Playlist auf einem Spotify-Connect-Geraet starten."""
        # Erst Wiedergabe auf das Geraet uebertragen (Geraet ggf. aufwecken) ...
        self._anfrage("PUT", "/me/player", body={"device_ids": [geraet_id], "play": False})
        time.sleep(0.8)
        # ... dann die Playlist starten
        self._anfrage("PUT", "/me/player/play", {"device_id": geraet_id},
                      {"context_uri": f"spotify:playlist:{playlist_id}"})

    def pause(self, geraet_id: str) -> None:
        self._anfrage("PUT", "/me/player/pause", {"device_id": geraet_id})

    def fortsetzen(self, geraet_id: str) -> None:
        self._anfrage("PUT", "/me/player/play", {"device_id": geraet_id})

    def naechster(self, geraet_id: str) -> None:
        self._anfrage("POST", "/me/player/next", {"device_id": geraet_id})

    def voriger(self, geraet_id: str) -> None:
        self._anfrage("POST", "/me/player/previous", {"device_id": geraet_id})

    def lautstaerke(self, geraet_id: str, prozent: int) -> None:
        self._anfrage("PUT", "/me/player/volume",
                      {"volume_percent": max(0, min(100, int(prozent))),
                       "device_id": geraet_id})
