# -*- coding: utf-8 -*-
"""
web.py - Web-Oberflaeche und JSON-API des zentralen Dienstes (Flask).

Sicherheit:
  - Zugang nur mit Passwort (PBKDF2-SHA256, gesalzen, im Datenordner gespeichert)
  - Ersteinrichtung des Passworts NUR direkt am Server (Zugriff von 127.0.0.1/::1),
    damit niemand im Netz das erste Passwort vergeben kann
  - Sitzungs-Cookie: HttpOnly, SameSite=Strict (Schutz gegen fremde Seiten)
  - Fehlversuche beim Anmelden werden pro IP-Adresse gebremst
"""

from __future__ import annotations

import collections
import hashlib
import hmac
import secrets
import threading
import time
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, redirect, request, send_file, session

from . import __version__
from .einstellungen import konfig_ordner
from .protokoll import abonnieren, protokoll
from .spotify import SpotifyFehler
from .zentrale import Zentrale

WEB_ORDNER = Path(__file__).resolve().parent / "web"   # HTML-Seiten
LOKAL = {"127.0.0.1", "::1"}                            # Zugriffe direkt am Server

# ---------------------------------------------------------------------------
# Passwort-Hash
# ---------------------------------------------------------------------------
ITERATIONEN = 200_000


def passwort_hash(passwort: str) -> str:
    """Erzeugt 'pbkdf2$<iterationen>$<salz>$<hash>' (alles hex)."""
    salz = secrets.token_bytes(16)
    wert = hashlib.pbkdf2_hmac("sha256", passwort.encode("utf-8"), salz, ITERATIONEN)
    return f"pbkdf2${ITERATIONEN}${salz.hex()}${wert.hex()}"


def passwort_pruefen(passwort: str, gespeichert: str) -> bool:
    """Vergleicht in konstanter Zeit (kein Rueckschluss ueber die Antwortzeit)."""
    try:
        _, iterationen, salz, wert = gespeichert.split("$")
        neu = hashlib.pbkdf2_hmac("sha256", passwort.encode("utf-8"),
                                  bytes.fromhex(salz), int(iterationen))
        return hmac.compare_digest(neu.hex(), wert)
    except (ValueError, AttributeError):
        return False


# ---------------------------------------------------------------------------
# Protokoll-Puffer fuer die Anzeige im Browser
# ---------------------------------------------------------------------------
class ProtokollPuffer:
    """Haelt die letzten 500 Protokollzeilen mit fortlaufender Nummer."""

    def __init__(self) -> None:
        self._zeilen: collections.deque = collections.deque(maxlen=500)
        self._nummer = 0
        self._sperre = threading.Lock()
        abonnieren(self._neu)

    def _neu(self, zeile: str) -> None:
        with self._sperre:
            self._nummer += 1
            self._zeilen.append((self._nummer, zeile))

    def ab(self, nummer: int) -> list:
        """Alle Zeilen mit einer Nummer groesser als 'nummer'."""
        with self._sperre:
            return [[n, z] for n, z in self._zeilen if n > nummer]


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
def app_erzeugen(zentrale: Zentrale) -> Flask:
    """Baut die Flask-App fuer die uebergebene Zentrale."""
    app = Flask(__name__)
    app.secret_key = zentrale.einst["geheimschluessel"]
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        PERMANENT_SESSION_LIFETIME=30 * 24 * 3600,   # 30 Tage angemeldet bleiben
        MAX_CONTENT_LENGTH=2 * 1024 * 1024,          # z. B. cookies.txt-Upload
    )
    puffer = ProtokollPuffer()
    fehlversuche: dict[str, list[float]] = collections.defaultdict(list)

    def wer() -> str:
        """Kennung fuer das Protokoll: IP-Adresse des Browsers."""
        return request.remote_addr or "?"

    def angemeldet(funktion):
        """Dekorator: nur mit gueltiger Anmeldung; sonst 401 (API) bzw. Login-Seite."""
        @wraps(funktion)
        def huelle(*args, **kwargs):
            if not zentrale.einst["passwort_hash"]:
                return redirect("/einrichten")
            if not session.get("angemeldet"):
                if request.path.startswith("/api/"):
                    return jsonify(fehler="Nicht angemeldet."), 401
                return redirect("/login")
            return funktion(*args, **kwargs)
        return huelle

    def api(funktion):
        """Dekorator fuer API-Aufrufe: Fehler als JSON {"fehler": ...} statt Absturz."""
        @wraps(funktion)
        def huelle(*args, **kwargs):
            try:
                return funktion(*args, **kwargs)
            except (ValueError, SpotifyFehler) as exc:
                return jsonify(fehler=str(exc)), 400
            except RuntimeError as exc:   # z. B. Lautsprecher nicht erreichbar
                return jsonify(fehler=str(exc)), 502
        return angemeldet(huelle)

    def daten() -> dict:
        """JSON-Koerper der Anfrage (leeres Dict, wenn keiner da ist)."""
        return request.get_json(silent=True) or {}

    # ------------------------------------------------------------ Seiten
    @app.get("/")
    @angemeldet
    def startseite():
        return send_file(WEB_ORDNER / "index.html")

    @app.get("/login")
    def login_seite():
        if not zentrale.einst["passwort_hash"]:
            return redirect("/einrichten")
        return send_file(WEB_ORDNER / "login.html")

    @app.post("/login")
    def login():
        ip = wer()
        # Bremse: nach 5 Fehlversuchen in 10 Minuten werden weitere Versuche abgelehnt
        jetzt = time.time()
        fehlversuche[ip] = [t for t in fehlversuche[ip] if jetzt - t < 600]
        if len(fehlversuche[ip]) >= 5:
            return redirect("/login?fehler=gesperrt")
        if passwort_pruefen(request.form.get("passwort", ""), zentrale.einst["passwort_hash"]):
            session.clear()
            session["angemeldet"] = True
            session.permanent = True
            protokoll(f"Anmeldung von {ip}")
            return redirect("/")
        fehlversuche[ip].append(jetzt)
        time.sleep(1)  # Ausprobieren zusaetzlich verlangsamen
        protokoll(f"✗ Fehlgeschlagene Anmeldung von {ip}")
        return redirect("/login?fehler=falsch")

    @app.get("/logout")
    def logout():
        session.clear()
        return redirect("/login")

    @app.route("/einrichten", methods=["GET", "POST"])
    def einrichten():
        """Ersteinrichtung des Passworts – nur direkt am Server moeglich."""
        if zentrale.einst["passwort_hash"]:
            return redirect("/")
        if request.remote_addr not in LOKAL:
            return ("Raumfeld Remote ist noch nicht eingerichtet. Bitte die Seite einmal direkt "
                    "auf dem Server öffnen: http://localhost:" + str(zentrale.einst["web_port"]),
                    403, {"Content-Type": "text/plain; charset=utf-8"})
        if request.method == "POST":
            pw1, pw2 = request.form.get("passwort", ""), request.form.get("passwort2", "")
            if len(pw1) < 8 or pw1 != pw2:
                return redirect("/einrichten?fehler=1")
            zentrale.einst.setzen(passwort_hash=passwort_hash(pw1))
            protokoll("Zugangspasswort eingerichtet.")
            session.clear()
            session["angemeldet"] = True
            return redirect("/")
        return send_file(WEB_ORDNER / "einrichten.html")

    # ------------------------------------------------------------ API: Zustand
    @app.get("/api/zustand")
    @api
    def api_zustand():
        zustand = zentrale.zustand()
        zustand["version"] = __version__
        return jsonify(zustand)

    @app.get("/api/protokoll")
    @api
    def api_protokoll():
        return jsonify(zeilen=puffer.ab(int(request.args.get("ab", 0))))

    # ------------------------------------------------------------ API: Lautsprecher
    @app.post("/api/suchen")
    @api
    def api_suchen():
        zentrale.suchen_im_hintergrund()
        return jsonify(ok=True)

    @app.post("/api/box")
    @api
    def api_box():
        name = zentrale.box_hinzufuegen(str(daten().get("url", "")).strip())
        return jsonify(meldung=f"„{name}“ hinzugefügt.")

    @app.get("/api/lautstaerke")
    @api
    def api_lautstaerke_lesen():
        return jsonify(wert=zentrale.lautstaerke_lesen(request.args.get("box", "")))

    @app.post("/api/lautstaerke")
    @api
    def api_lautstaerke():
        d = daten()
        zentrale.lautstaerke_setzen(str(d.get("box", "")), int(d.get("wert", 0)))
        return jsonify(ok=True)

    # ------------------------------------------------------------ API: Wiedergabe
    @app.post("/api/abspielen")
    @api
    def api_abspielen():
        d = daten()
        meldung = zentrale.abspielen(str(d.get("box", "")), str(d.get("eingabe", "")),
                                     bool(d.get("einzeln")), bool(d.get("zufall")), wer())
        return jsonify(meldung=meldung)

    @app.post("/api/steuern")
    @api
    def api_steuern():
        d = daten()
        zentrale.steuern(str(d.get("box", "")), str(d.get("aktion", "")), int(d.get("index", -1)))
        return jsonify(ok=True)

    # ------------------------------------------------------------ API: Einstellungen
    @app.get("/api/einstellungen")
    @api
    def api_einstellungen_lesen():
        return jsonify(zentrale.einstellungen_lesen())

    @app.post("/api/einstellungen")
    @api
    def api_einstellungen():
        zentrale.einstellungen_speichern(daten())
        return jsonify(meldung="Gespeichert – gilt für alle.")

    @app.post("/api/cookies")
    @api
    def api_cookies():
        """cookies.txt (Netscape-Format) fuer die YouTube-Anmeldung hochladen bzw. loeschen."""
        ziel = konfig_ordner() / "cookies.txt"
        if request.args.get("loeschen"):
            ziel.unlink(missing_ok=True)
            protokoll(f"{wer()}: YouTube-Anmeldung (cookies.txt) entfernt.")
            return jsonify(meldung="YouTube-Anmeldung entfernt.")
        datei = request.files.get("datei")
        if datei is None:
            raise ValueError("Keine Datei übermittelt.")
        inhalt = datei.read()
        if b"youtube.com" not in inhalt:
            raise ValueError("Das sieht nicht nach einer cookies.txt mit YouTube-Cookies aus.")
        ziel.write_bytes(inhalt)
        protokoll(f"{wer()}: YouTube-Anmeldung (cookies.txt) hochgeladen.")
        return jsonify(meldung="YouTube-Anmeldung gespeichert – gilt für alle.")

    # ------------------------------------------------------------ API: Spotify
    @app.get("/api/spotify")
    @api
    def api_spotify_status():
        return jsonify(zentrale.spotify_status())

    @app.post("/api/spotify/client_id")
    @api
    def api_spotify_client_id():
        zentrale.spotify_client_id_setzen(str(daten().get("client_id", "")))
        return jsonify(meldung="Client-ID gespeichert.")

    @app.post("/api/spotify/anmelden")
    @api
    def api_spotify_anmelden():
        return jsonify(url=zentrale.spotify_anmelden_start())

    @app.post("/api/spotify/code")
    @api
    def api_spotify_code():
        zentrale.spotify_anmelden_ende(str(daten().get("adresse", "")), wer())
        return jsonify(meldung="Spotify verbunden – gilt für alle.")

    @app.post("/api/spotify/abmelden")
    @api
    def api_spotify_abmelden():
        zentrale.spotify_abmelden(wer())
        return jsonify(meldung="Spotify getrennt.")

    @app.get("/api/spotify/playlists")
    @api
    def api_spotify_playlists():
        return jsonify(playlists=zentrale.spotify_playlists())

    @app.get("/api/spotify/geraete")
    @api
    def api_spotify_geraete():
        return jsonify(geraete=zentrale.spotify_geraete())

    @app.post("/api/spotify/abspielen")
    @api
    def api_spotify_abspielen():
        d = daten()
        playlist = str(d.get("playlist", ""))
        if not playlist:
            raise ValueError("Bitte eine Playlist wählen.")
        if d.get("weg") == "connect":
            meldung = zentrale.spotify_connect_abspielen(str(d.get("geraet", "")), playlist, wer())
        else:
            meldung = zentrale.spotify_via_youtube(str(d.get("box", "")), playlist,
                                                   bool(d.get("zufall")), wer())
        return jsonify(meldung=meldung)

    @app.post("/api/spotify/steuern")
    @api
    def api_spotify_steuern():
        d = daten()
        zentrale.spotify_steuern(str(d.get("geraet", "")), str(d.get("aktion", "")))
        return jsonify(ok=True)

    @app.post("/api/passwort")
    @api
    def api_passwort():
        d = daten()
        if not passwort_pruefen(str(d.get("alt", "")), zentrale.einst["passwort_hash"]):
            raise ValueError("Das bisherige Passwort ist falsch.")
        neu = str(d.get("neu", ""))
        if len(neu) < 8:
            raise ValueError("Das neue Passwort muss mindestens 8 Zeichen haben.")
        zentrale.einst.setzen(passwort_hash=passwort_hash(neu))
        protokoll(f"{wer()}: Zugangspasswort geändert.")
        return jsonify(meldung="Passwort geändert.")

    return app
