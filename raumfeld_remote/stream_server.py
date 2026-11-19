# -*- coding: utf-8 -*-
"""
stream_server.py - Lokaler HTTP-Server, der Titel als MP3-Stream ausliefert.

Ablauf pro Anfrage des Lautsprechers auf /stream/<nummer>.mp3:
    yt-dlp (laedt Audio) -> ffmpeg (wandelt live in MP3) -> HTTP-Antwort
"""

from __future__ import annotations

import http.server
import os
import socketserver
import subprocess
import threading
import urllib.parse

from .quellen import KEIN_FENSTER, finde_programm


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
        if self._quelle() is None:
            self.send_error(404)
            return
        self._kopfzeilen_senden()

    def do_GET(self):  # noqa: N802
        quelle = self._quelle()
        if quelle is None:
            self.send_error(404)
            return
        self._kopfzeilen_senden()

        prozesse = self._pipeline_starten(quelle)
        if not prozesse:
            return
        ffmpeg = prozesse[-1]
        try:
            # MP3-Daten blockweise an den Lautsprecher weiterreichen
            while True:
                block = ffmpeg.stdout.read(16 * 1024)
                if not block:
                    break
                self.wfile.write(block)
        except (ConnectionError, OSError):
            # Lautsprecher hat die Verbindung beendet (Stop, naechster Titel ...)
            # Unter Windows ist das meist ConnectionAbortedError/ResetError.
            pass
        finally:
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

        if os.path.isfile(quelle):
            # Lokale Datei: ffmpeg liest direkt
            ffmpeg = subprocess.Popen(
                [ffmpeg_exe, "-hide_banner", "-loglevel", "error", "-nostdin",
                 "-i", quelle, *ausgabe],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                creationflags=KEIN_FENSTER)
            return [ffmpeg]

        ytdlp_exe = finde_programm("yt-dlp")
        if ytdlp_exe is None:
            return []
        # yt-dlp schreibt das beste Audio nach stdout ("-o -")
        ytdlp_befehl = [ytdlp_exe, "--quiet", "--no-warnings", "--no-playlist",
                        *self.server.cookie_args,  # type: ignore[attr-defined]
                        "-f", "bestaudio/best", "-o", "-", quelle]
        ytdlp = subprocess.Popen(ytdlp_befehl, stdout=subprocess.PIPE,
                                 stdin=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL,
                                 creationflags=KEIN_FENSTER)
        ffmpeg = subprocess.Popen(
            [ffmpeg_exe, "-hide_banner", "-loglevel", "error",
             "-i", "pipe:0", *ausgabe],
            stdin=ytdlp.stdout, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, creationflags=KEIN_FENSTER)
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
        self._thread: threading.Thread | None = None

    def starten(self) -> None:
        """Startet den Server im Hintergrund."""
        self._thread = threading.Thread(target=self.serve_forever, daemon=True)
        self._thread.start()

    def beenden(self) -> None:
        """Stoppt den Server und gibt den Port frei."""
        self.shutdown()
        self.server_close()
