# -*- coding: utf-8 -*-
"""
stream_server.py - Lokaler HTTP-Server, der Titel als MP3-Stream ausliefert.

Ablauf pro Anfrage des Lautsprechers auf /stream/<nummer>.mp3:
    yt-dlp (laedt Audio) -> ffmpeg (wandelt live in MP3) -> HTTP-Antwort

Diagnose: Jede Anfrage, die Menge der gesendeten Daten sowie Fehlermeldungen
von yt-dlp und ffmpeg landen im Protokoll %APPDATA%/RaumfeldRemote/stream.log.
"""

from __future__ import annotations

import http.server
import os
import socketserver
import subprocess
import tempfile
import threading
import time
import urllib.parse
from pathlib import Path

from .protokoll import protokoll
from .quellen import KEIN_FENSTER, finde_programm, js_runtime_argumente


def _fehler_mitlesen(name: str, strom) -> None:
    """Liest die Fehlerausgabe eines Prozesses zeilenweise und schreibt sie ins Protokoll."""
    for roh in iter(strom.readline, b""):
        text = roh.decode("utf-8", errors="replace").strip()
        if text:
            protokoll(f"  {name}: {text}")
    strom.close()


def _starte(name: str, befehl: list[str], **optionen) -> subprocess.Popen:
    """
    Startet einen Prozess ohne Konsolenfenster. Seine Fehlerausgabe (stderr)
    wird in einem eigenen Thread mitgelesen und landet im Protokoll
    (Datei + aufklappbares Protokoll in der Oberflaeche).
    """
    prozess = subprocess.Popen(befehl, stderr=subprocess.PIPE,
                               creationflags=KEIN_FENSTER, **optionen)
    threading.Thread(target=_fehler_mitlesen, args=(name, prozess.stderr),
                     daemon=True).start()
    return prozess


class _Handler(http.server.BaseHTTPRequestHandler):
    """Beantwortet die Anfragen der Lautsprecher."""

    # HTTP/1.0: Ende des Streams = Verbindung schliessen (keine Laenge noetig)
    protocol_version = "HTTP/1.0"

    def _quelle(self) -> str | None:
        """Quelle (URL oder Pfad) zur angefragten Nummer ermitteln."""
        name = os.path.basename(urllib.parse.urlparse(self.path).path)
        return self.server.quellen.get(name.removesuffix(".mp3"))  # type: ignore[attr-defined]

    def _kopfzeilen_senden(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        # DLNA-Header: kennzeichnen den Stream als Live-Stream
        self.send_header("transferMode.dlna.org", "Streaming")
        self.send_header("contentFeatures.dlna.org",
                         "DLNA.ORG_PN=MP3;DLNA.ORG_OP=00;"
                         "DLNA.ORG_FLAGS=01700000000000000000000000000000")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

    def do_HEAD(self):  # noqa: N802 (Name von BaseHTTPRequestHandler vorgegeben)
        """Manche Renderer pruefen vorab per HEAD, ob der Stream existiert."""
        protokoll(f"HEAD {self.path} von {self.client_address[0]}")
        if self._quelle() is None:
            self.send_error(404)
            return
        self._kopfzeilen_senden()

    def do_GET(self):  # noqa: N802
        protokoll(f"GET {self.path} von {self.client_address[0]}")
        name = os.path.basename(urllib.parse.urlparse(self.path).path).removesuffix(".mp3")
        # Merken, dass der Lautsprecher diesen Titel abgerufen hat (Pruefung im Player)
        self.server.abrufe[name] = self.server.abrufe.get(name, 0) + 1  # type: ignore[attr-defined]
        quelle = self._quelle()
        if quelle is None:
            protokoll("  -> 404, Titelnummer unbekannt")
            self.send_error(404)
            return
        self._kopfzeilen_senden()

        prozesse = self._pipeline_starten(quelle)
        if not prozesse:
            protokoll("  -> kein Stream: ffmpeg/yt-dlp fehlt oder Quelle nicht auflösbar (siehe oben)")
            return
        ffmpeg = prozesse[-1]
        gesendet = 0
        try:
            # MP3-Daten blockweise an den Lautsprecher weiterreichen
            while True:
                block = ffmpeg.stdout.read(16 * 1024)
                if not block:
                    break
                self.wfile.write(block)
                gesendet += len(block)
        except (ConnectionError, OSError):
            # Lautsprecher hat die Verbindung beendet (Stop, naechster Titel ...)
            # Unter Windows ist das meist ConnectionAbortedError/ResetError.
            pass
        finally:
            protokoll(f"  -> {gesendet // 1024} KB an {self.client_address[0]} gesendet"
                      + ("  (KEINE DATEN - siehe Fehlermeldungen oben)" if gesendet == 0 else ""))
            for p in prozesse:
                if p.poll() is None:
                    p.kill()
                p.wait()

    def _pipeline_starten(self, quelle: str) -> list[subprocess.Popen]:
        """Startet [yt-dlp ->] ffmpeg. Letzter Prozess der Liste ist ffmpeg."""
        ffmpeg_exe = finde_programm("ffmpeg")
        if ffmpeg_exe is None:
            return []
        bitrate = self.server.bitrate  # type: ignore[attr-defined]
        ausgabe = ["-vn", "-acodec", "libmp3lame", "-b:a", bitrate,
                   "-ar", "44100", "-f", "mp3", "pipe:1"]

        # Quellen mit Praefix (z. B. "tidal:12345"): Aufloeser liefert eine Eingabe fuer
        # ffmpeg (direkte URL oder Pfad einer HLS-Liste). Wird erst jetzt aufgerufen,
        # weil solche Stream-Adressen nur kurz gueltig sind.
        praefix, trenner, rest = quelle.partition(":")
        aufloeser = self.server.aufloeser.get(praefix) if trenner else None  # type: ignore[attr-defined]
        if aufloeser is not None:
            try:
                eingabe = aufloeser(rest)
            except Exception as exc:  # noqa: BLE001 - Fehler nur protokollieren
                protokoll(f"  ✗ {praefix}: {exc}")
                return []
            ffmpeg = _starte("ffmpeg",
                [ffmpeg_exe, "-hide_banner", "-loglevel", "error", "-nostdin",
                 # HLS-Listen verweisen auf https-Segmente -> Protokolle ausdruecklich erlauben
                 "-protocol_whitelist", "file,http,https,tcp,tls,crypto",
                 "-i", eingabe, *ausgabe],
                stdout=subprocess.PIPE)
            return [ffmpeg]

        if os.path.isfile(quelle):
            # Lokale Datei: ffmpeg liest direkt
            ffmpeg = _starte("ffmpeg",
                [ffmpeg_exe, "-hide_banner", "-loglevel", "error", "-nostdin",
                 "-i", quelle, *ausgabe],
                stdout=subprocess.PIPE)
            return [ffmpeg]

        ytdlp_exe = finde_programm("yt-dlp")
        if ytdlp_exe is None:
            return []
        # yt-dlp schreibt das beste Audio nach stdout ("-o -")
        # Vorbereitete Titeldaten vorhanden? Dann muss yt-dlp die YouTube-Seite nicht erneut
        # auswerten (das dauert mit JavaScript-Loesung oft 10-20 s) und laedt sofort.
        info = self.server.info_datei(quelle)  # type: ignore[attr-defined]
        eingabe = ["--load-info-json", info] if info else [quelle]
        ytdlp_befehl = [ytdlp_exe, "--quiet", "--no-playlist",  # Warnungen/Fehler -> Protokoll
                        *self.server.cookie_args,  # type: ignore[attr-defined]
                        *js_runtime_argumente(),   # JavaScript-Laufzeit fuer YouTube
                        "-f", "bestaudio/best", "-o", "-", *eingabe]
        if not js_runtime_argumente():
            protokoll("  Hinweis: deno.exe nicht gefunden - YouTube liefert ohne JavaScript-Laufzeit "
                      "oft kein Audio. start.bat erneut ausführen.")
        ytdlp = _starte("yt-dlp", ytdlp_befehl, stdout=subprocess.PIPE, stdin=subprocess.DEVNULL)
        ffmpeg = _starte("ffmpeg",
            [ffmpeg_exe, "-hide_banner", "-loglevel", "error",
             "-i", "pipe:0", *ausgabe],
            stdin=ytdlp.stdout, stdout=subprocess.PIPE)
        # Eigene Kopie des Pipe-Endes schliessen, damit yt-dlp bei
        # vorzeitigem ffmpeg-Ende ein Signal bekommt
        ytdlp.stdout.close()
        return [ytdlp, ffmpeg]

    def log_message(self, fmt, *args):
        """Kein Logging auf stderr (unter pythonw gibt es keine Konsole)."""
        return


class StreamServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """HTTP-Server mit einem Thread pro Anfrage."""
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, port: int, bitrate: str, cookie_args: list[str]) -> None:
        super().__init__(("0.0.0.0", port), _Handler)
        self.port = port
        self.bitrate = bitrate
        self.cookie_args = cookie_args
        # Nummer (als Text) -> Quelle; wird vom Player befuellt
        self.quellen: dict[str, str] = {}
        # Nummer (als Text) -> Anzahl GET-Anfragen (zeigt, ob der Lautsprecher den Stream abruft)
        self.abrufe: dict[str, int] = {}
        # Vorbereitete Titeldaten (yt-dlp-JSON): Quelle -> (Dateipfad, Zeitpunkt)
        self._infos: dict[str, tuple[Path, float]] = {}
        self._in_arbeit: dict[str, threading.Event] = {}   # laufende Vorbereitungen
        self._info_sperre = threading.Lock()
        self._info_ordner = Path(tempfile.gettempdir()) / "raumfeld_remote_infos"
        # Praefix -> Funktion, die eine Quelle wie "tidal:12345" in eine ffmpeg-Eingabe
        # (URL oder Dateipfad) umwandelt; wird von der Zentrale befuellt
        self.aufloeser: dict = {}
        protokoll(f"=== Stream-Server gestartet auf Port {port} ===")
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------ Vorbereitung
    # Gueltigkeit vorbereiteter Titeldaten. Die darin enthaltenen YouTube-Adressen
    # laufen nach einigen Stunden ab (Kenntnisstand: ca. 6 h) -> sicherheitshalber 3 h.
    INFO_GUELTIG = 3 * 3600

    @staticmethod
    def _vorbereitbar(quelle: str) -> bool:
        """Nur YouTube-Links und YouTube-Suchen (keine Dateien, keine tidal:-Quellen)."""
        return quelle.startswith(("http://", "https://", "ytsearch"))

    def info_datei(self, quelle: str) -> str | None:
        """Pfad der vorbereiteten Titeldaten, falls vorhanden und noch gueltig."""
        with self._info_sperre:
            eintrag = self._infos.get(quelle)
        if eintrag and time.time() - eintrag[1] < self.INFO_GUELTIG and eintrag[0].is_file():
            return str(eintrag[0])
        return None

    def vorbereiten(self, quelle: str, timeout: float = 60.0) -> bool:
        """
        Laesst yt-dlp die Titeldaten (Formate, Adressen) vorab ermitteln und speichert sie
        als JSON. Blockiert, bis fertig (hoechstens timeout). Mehrfache Aufrufe fuer dieselbe
        Quelle warten auf die laufende Vorbereitung statt sie doppelt zu starten.
        Rueckgabe: True, wenn Titeldaten bereitliegen.
        """
        if not self._vorbereitbar(quelle):
            return False
        if self.info_datei(quelle):
            return True
        ytdlp_exe = finde_programm("yt-dlp")
        if ytdlp_exe is None:
            return False
        with self._info_sperre:
            laufend = self._in_arbeit.get(quelle)
            if laufend is None:
                self._in_arbeit[quelle] = threading.Event()
        if laufend is not None:
            laufend.wait(timeout)          # andere Vorbereitung abwarten
            return self.info_datei(quelle) is not None

        beginn = time.monotonic()
        try:
            self._info_ordner.mkdir(parents=True, exist_ok=True)
            self._alte_infos_loeschen()
            ergebnis = subprocess.run(
                [ytdlp_exe, "--quiet", "--no-warnings", "--no-playlist", "-j",
                 *self.cookie_args, *js_runtime_argumente(), "-f", "bestaudio/best", quelle],
                capture_output=True, timeout=timeout, creationflags=KEIN_FENSTER)
            json_text = ergebnis.stdout.strip().splitlines()[0] if ergebnis.stdout.strip() else b""
            if ergebnis.returncode != 0 or not json_text:
                fehler = ergebnis.stderr.decode("utf-8", errors="replace").strip().splitlines()
                protokoll(f"  Vorbereitung fehlgeschlagen ({fehler[-1] if fehler else 'keine Ausgabe'}) – "
                          "Titel wird beim Abspielen direkt geladen.")
                return False
            datei = self._info_ordner / f"{abs(hash(quelle))}_{int(time.time())}.json"
            datei.write_bytes(json_text)
            with self._info_sperre:
                self._infos[quelle] = (datei, time.time())
            protokoll(f"  Titel vorbereitet in {time.monotonic() - beginn:.1f} s")
            return True
        except (OSError, subprocess.SubprocessError) as exc:
            protokoll(f"  Vorbereitung fehlgeschlagen: {exc}")
            return False
        finally:
            with self._info_sperre:
                self._in_arbeit.pop(quelle).set()

    def vorbereiten_im_hintergrund(self, quelle: str) -> None:
        """Wie vorbereiten(), aber ohne zu warten (z. B. fuer den naechsten Titel)."""
        if self._vorbereitbar(quelle) and not self.info_datei(quelle):
            threading.Thread(target=self.vorbereiten, args=(quelle,), daemon=True).start()

    def _alte_infos_loeschen(self) -> None:
        """Abgelaufene Titeldaten aus Speicher und Temp-Ordner entfernen."""
        grenze = time.time() - self.INFO_GUELTIG
        with self._info_sperre:
            for quelle, (datei, zeit) in list(self._infos.items()):
                if zeit < grenze:
                    del self._infos[quelle]
                    datei.unlink(missing_ok=True)

    def starten(self) -> None:
        """Startet den Server im Hintergrund."""
        self._thread = threading.Thread(target=self.serve_forever, daemon=True)
        self._thread.start()

    def beenden(self) -> None:
        """Stoppt den Server und gibt den Port frei."""
        self.shutdown()
        self.server_close()
