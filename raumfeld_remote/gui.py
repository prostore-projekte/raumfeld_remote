# -*- coding: utf-8 -*-
"""
gui.py - Grafische Oberflaeche (customtkinter) fuer Raumfeld Remote.

Aufbau:
  links   : Lautsprecher (Suche, Auswahl, Lautstaerke)
  rechts  : Reiter  YouTube / YT Music | Spotify | Konten | Einstellungen
  unten   : Player-Leiste (Titel, Zurueck / Pause / Stop / Weiter, Status)

Thread-Regel: Netzwerk- und Prozessarbeit laeuft immer in Hintergrund-Threads
(Methode _hintergrund). Diese duerfen die Oberflaeche NICHT direkt anfassen,
sondern legen ueber _ui(...) eine Funktion in eine Queue, die der Hauptthread
regelmaessig abarbeitet (_ui_pumpe).
"""

from __future__ import annotations

import queue
import subprocess
import threading
from tkinter import filedialog, messagebox
from typing import Callable

import customtkinter as ctk

from .einstellungen import Einstellungen, gemeinsamer_ordner, konfig_ordner
from .player import Wiedergabe
from .quellen import (KEIN_FENSTER, Titel, cookie_argumente, finde_programm,
                      titel_liste_aufbauen)
from .spotify import Spotify, SpotifyFehler, playlist_id_aus_text
from .stream_server import StreamServer
from .upnp import (Renderer, hole_lautstaerke, lokale_ip_zu, netz_adressen,
                   renderer_laden, renderer_suchen, setze_lautstaerke)

BROWSER_AUSWAHL = ["keiner", "firefox", "chrome", "edge", "brave",
                   "chromium", "opera", "vivaldi"]
BITRATEN = ["128k", "192k", "256k", "320k"]

# Auf einem Terminalserver braucht jede Sitzung einen eigenen Stream-Port:
# ist der eingestellte Port belegt, wird der naechste freie aus diesem Bereich genommen.
PORT_BEREICH = 50
# Firewall-Regel fuer den ganzen Port-Bereich; "domain" fuer Server im Firmennetz
FIREWALL_BEFEHL = ('netsh advfirewall firewall add rule name="Raumfeld Remote" '
                   'dir=in action=allow protocol=TCP localport={port}-{ende} profile=private,domain')


class App(ctk.CTk):
    """Hauptfenster."""

    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("system")      # folgt dem Windows-Design (hell/dunkel)
        ctk.set_default_color_theme("blue")
        self.title("Raumfeld Remote")
        self.geometry("1060x720")
        self.minsize(940, 640)

        # --- Zustand -------------------------------------------------------
        self.einst = Einstellungen()
        self.boxen: list[Renderer] = []            # gefundene Lautsprecher
        self.gewaehlt: Renderer | None = None      # aktuell gewaehlter Lautsprecher
        self.server: StreamServer | None = None
        self._server_basisport = 0                 # eingestellter Port beim Serverstart
        self.player: Wiedergabe | None = None
        # Spotify-Token: eigenes Token des Benutzers, sonst ein "fuer alle" gespeichertes
        eigenes_token = konfig_ordner() / "spotify_token.json"
        gemeinsames_token = gemeinsamer_ordner() / "spotify_token.json"
        token_datei = (gemeinsames_token if not eigenes_token.exists() and gemeinsames_token.exists()
                       else eigenes_token)
        self.spotify = Spotify(token_datei, self.einst["spotify_client_id"])
        self.modus = "upnp"                        # "upnp" (YouTube) oder "spotify"
        self.spotify_geraete: dict[str, str] = {}  # Anzeigename -> Geraete-ID
        self.pausiert = False
        self._ui_queue: queue.Queue[Callable[[], None]] = queue.Queue()
        self._vol_job: str | None = None           # Entprell-Timer fuer den Regler
        self.var_box = ctk.StringVar(value="")

        self._baue_oberflaeche()
        self.after(100, self._ui_pumpe)
        self.protocol("WM_DELETE_WINDOW", self._beenden)

        self._spotify_status_aktualisieren()
        self._boxen_suchen()                       # beim Start automatisch suchen

    # ====================================================================
    # Hilfsfunktionen: Threads und Statuszeile
    # ====================================================================
    def _ui(self, funktion: Callable[[], None]) -> None:
        """Aus Threads aufrufen: fuehrt 'funktion' spaeter im Hauptthread aus."""
        self._ui_queue.put(funktion)

    def _ui_pumpe(self) -> None:
        """Arbeitet alle wartenden Oberflaechen-Aufgaben ab (alle 100 ms)."""
        try:
            while True:
                self._ui_queue.get_nowait()()
        except queue.Empty:
            pass
        self.after(100, self._ui_pumpe)

    def _hintergrund(self, funktion: Callable[[], None]) -> None:
        """Fuehrt 'funktion' in einem Thread aus; Fehler landen in der Statuszeile."""
        def huelle() -> None:
            try:
                funktion()
            except (RuntimeError, SpotifyFehler, OSError) as exc:
                self._status(f"Fehler: {exc}")
            except Exception as exc:  # noqa: BLE001 - nichts darf den Thread still beenden
                self._status(f"Unerwarteter Fehler: {exc!r}")
        threading.Thread(target=huelle, daemon=True).start()

    def _status(self, text: str) -> None:
        """Setzt die Statuszeile (thread-sicher)."""
        self._ui(lambda: self.lbl_status.configure(text=text))

    # ====================================================================
    # Oberflaeche aufbauen
    # ====================================================================
    def _baue_oberflaeche(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._baue_seitenleiste()

        # Rechter Bereich mit Reitern
        self.reiter = ctk.CTkTabview(self)
        self.reiter.grid(row=0, column=1, sticky="nsew", padx=(0, 12), pady=(12, 6))
        for name in ("YouTube / YT Music", "Spotify", "Konten", "Einstellungen"):
            self.reiter.add(name)
        self._baue_reiter_youtube(self.reiter.tab("YouTube / YT Music"))
        self._baue_reiter_spotify(self.reiter.tab("Spotify"))
        self._baue_reiter_konten(self.reiter.tab("Konten"))
        self._baue_reiter_einstellungen(self.reiter.tab("Einstellungen"))

        self._baue_playerleiste()

    # ---------------------------------------------------------------- links
    def _baue_seitenleiste(self) -> None:
        leiste = ctk.CTkFrame(self, width=290)
        leiste.grid(row=0, column=0, sticky="nsw", padx=12, pady=(12, 6))
        leiste.grid_propagate(False)
        leiste.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(leiste, text="Lautsprecher",
                     font=ctk.CTkFont(size=18, weight="bold")
                     ).grid(row=0, column=0, sticky="w", padx=14, pady=(14, 6))

        self.btn_suchen = ctk.CTkButton(leiste, text="🔍  Im Netzwerk suchen",
                                        command=self._boxen_suchen)
        self.btn_suchen.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 8))

        # Liste der gefundenen Geraete (Auswahl per Radio-Button)
        self.box_liste = ctk.CTkScrollableFrame(leiste, label_text="Gefundene Geräte")
        self.box_liste.grid(row=2, column=0, sticky="nsew", padx=10, pady=4)
        leiste.grid_columnconfigure(0, weight=1)

        # Manuelles Hinzufuegen per URL (falls die Suche nichts findet)
        self.ent_location = ctk.CTkEntry(leiste, placeholder_text="Gerät-URL manuell (…xml)")
        self.ent_location.grid(row=3, column=0, sticky="ew", padx=14, pady=(8, 2))
        ctk.CTkButton(leiste, text="Manuell hinzufügen", height=26,
                      fg_color="transparent", border_width=1,
                      text_color=("gray10", "gray90"),
                      command=self._box_manuell).grid(row=4, column=0, sticky="ew",
                                                      padx=14, pady=(0, 10))

        # Lautstaerke
        ctk.CTkLabel(leiste, text="Lautstärke",
                     font=ctk.CTkFont(size=14, weight="bold")
                     ).grid(row=5, column=0, sticky="w", padx=14)
        self.lbl_vol = ctk.CTkLabel(leiste, text="– %")
        self.lbl_vol.grid(row=5, column=0, sticky="e", padx=14)
        self.slider_vol = ctk.CTkSlider(leiste, from_=0, to=100, number_of_steps=100,
                                        command=self._lautstaerke_geaendert)
        self.slider_vol.set(10)
        self.slider_vol.grid(row=6, column=0, sticky="ew", padx=14, pady=(2, 14))

    # ---------------------------------------------------------- Reiter YouTube
    def _baue_reiter_youtube(self, tab) -> None:
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(4, weight=1)

        ctk.CTkLabel(tab, text="Link, Playlist, Suchbegriff oder Datei:"
                     ).grid(row=0, column=0, sticky="w", padx=8, pady=(8, 2))
        self.ent_quelle = ctk.CTkEntry(
            tab, placeholder_text="https://music.youtube.com/playlist?list=…  oder  Suchbegriff")
        self.ent_quelle.grid(row=1, column=0, sticky="ew", padx=8)
        ctk.CTkButton(tab, text="Datei…", width=80,
                      command=self._datei_waehlen).grid(row=1, column=1, padx=(6, 8))

        optionen = ctk.CTkFrame(tab, fg_color="transparent")
        optionen.grid(row=2, column=0, columnspan=2, sticky="ew", padx=8, pady=8)
        self.var_einzeln = ctk.BooleanVar(value=self.einst["nur_einzeltitel"])
        self.var_zufall = ctk.BooleanVar(value=self.einst["zufall"])
        ctk.CTkCheckBox(optionen, text="Nur diesen Titel (nicht die ganze Playlist)",
                        variable=self.var_einzeln,
                        command=self._optionen_speichern).pack(side="left", padx=(0, 18))
        ctk.CTkCheckBox(optionen, text="Zufällige Reihenfolge", variable=self.var_zufall,
                        command=self._optionen_speichern).pack(side="left")

        knoepfe = ctk.CTkFrame(tab, fg_color="transparent")
        knoepfe.grid(row=3, column=0, columnspan=2, sticky="ew", padx=8)
        ctk.CTkButton(knoepfe, text="▶  Abspielen", width=140,
                      command=self._youtube_abspielen).pack(side="left", padx=(0, 8))
        ctk.CTkButton(knoepfe, text="★  Als Favorit speichern", width=180,
                      fg_color="transparent", border_width=1,
                      text_color=("gray10", "gray90"),
                      command=self._favorit_speichern).pack(side="left")

        self.fav_liste = ctk.CTkScrollableFrame(tab, label_text="Favoriten")
        self.fav_liste.grid(row=4, column=0, columnspan=2, sticky="nsew", padx=8, pady=10)
        self._favoriten_anzeigen()

    # ----------------------------------------------------------- Reiter Spotify
    def _baue_reiter_spotify(self, tab) -> None:
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(4, weight=1)

        self.lbl_sp_status = ctk.CTkLabel(tab, text="", anchor="w")
        self.lbl_sp_status.grid(row=0, column=0, columnspan=3, sticky="ew", padx=8, pady=(8, 2))

        # Zeile: Spotify-Connect-Geraet waehlen
        zeile = ctk.CTkFrame(tab, fg_color="transparent")
        zeile.grid(row=1, column=0, columnspan=3, sticky="ew", padx=8, pady=4)
        ctk.CTkLabel(zeile, text="Spotify-Connect-Gerät:").pack(side="left")
        self.opt_sp_geraet = ctk.CTkOptionMenu(zeile, values=["(keine gefunden)"], width=260)
        self.opt_sp_geraet.pack(side="left", padx=8)
        ctk.CTkButton(zeile, text="↻ Aktualisieren", width=120,
                      command=self._spotify_aktualisieren).pack(side="left")

        # Zeile: Playlist per Link
        zeile2 = ctk.CTkFrame(tab, fg_color="transparent")
        zeile2.grid(row=2, column=0, columnspan=3, sticky="ew", padx=8, pady=4)
        zeile2.grid_columnconfigure(0, weight=1)
        self.ent_sp_link = ctk.CTkEntry(zeile2, placeholder_text="Spotify-Playlist-Link einfügen")
        self.ent_sp_link.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(zeile2, text="▶ Spotify Connect", width=130,
                      command=lambda: self._spotify_link(True)).grid(row=0, column=1, padx=4)
        ctk.CTkButton(zeile2, text="▶ via YT Music", width=120,
                      command=lambda: self._spotify_link(False)).grid(row=0, column=2)

        ctk.CTkLabel(tab, justify="left", anchor="w", text_color=("gray35", "gray65"),
                     text="Spotify Connect: Spotify steuert den Lautsprecher selbst (Premium nötig).\n"
                          "via YT Music: Titelnamen werden von Spotify gelesen und bei YouTube "
                          "gesucht – ohne Premium, aber Treffer können abweichen."
                     ).grid(row=3, column=0, columnspan=3, sticky="ew", padx=8, pady=4)

        self.sp_liste = ctk.CTkScrollableFrame(tab, label_text="Deine Spotify-Playlists")
        self.sp_liste.grid(row=4, column=0, columnspan=3, sticky="nsew", padx=8, pady=8)

    # ------------------------------------------------------------ Reiter Konten
    def _baue_reiter_konten(self, tab) -> None:
        tab.grid_columnconfigure(0, weight=1)

        # --- YouTube / YouTube Music --------------------------------------
        yt = ctk.CTkFrame(tab)
        yt.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        yt.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(yt, text="YouTube / YouTube Music",
                     font=ctk.CTkFont(size=15, weight="bold")
                     ).grid(row=0, column=0, columnspan=3, sticky="w", padx=12, pady=(10, 2))
        ctk.CTkLabel(yt, justify="left", anchor="w", text_color=("gray35", "gray65"),
                     text="Für private Playlists, „Gefällt mir“-Titel oder Premium: yt-dlp liest "
                          "die Anmeldung aus deinem Browser.\nMeldest du dich dort bei YouTube an, "
                          "gilt das hier mit. Ohne Anmeldung funktionieren öffentliche Links."
                     ).grid(row=1, column=0, columnspan=3, sticky="ew", padx=12)
        ctk.CTkLabel(yt, text="Browser:").grid(row=2, column=0, sticky="w", padx=12, pady=6)
        self.opt_browser = ctk.CTkOptionMenu(yt, values=BROWSER_AUSWAHL, width=160)
        self.opt_browser.set(self.einst["browser_cookies"])
        self.opt_browser.grid(row=2, column=1, sticky="w")
        ctk.CTkLabel(yt, text="oder cookies.txt:").grid(row=3, column=0, sticky="w", padx=12)
        self.ent_cookies = ctk.CTkEntry(yt)
        self.ent_cookies.insert(0, self.einst["cookies_datei"])
        self.ent_cookies.grid(row=3, column=1, sticky="ew", padx=(0, 6))
        ctk.CTkButton(yt, text="Durchsuchen…", width=110,
                      command=self._cookies_datei_waehlen).grid(row=3, column=2, padx=(0, 12))
        zeile = ctk.CTkFrame(yt, fg_color="transparent")
        zeile.grid(row=4, column=0, columnspan=3, sticky="w", padx=12, pady=10)
        ctk.CTkButton(zeile, text="Speichern & testen",
                      command=self._yt_konto_testen).pack(side="left")
        self.lbl_yt_konto = ctk.CTkLabel(zeile, text="")
        self.lbl_yt_konto.pack(side="left", padx=12)

        # --- Spotify -------------------------------------------------------
        sp = ctk.CTkFrame(tab)
        sp.grid(row=1, column=0, sticky="ew", padx=8, pady=8)
        sp.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(sp, text="Spotify", font=ctk.CTkFont(size=15, weight="bold")
                     ).grid(row=0, column=0, columnspan=3, sticky="w", padx=12, pady=(10, 2))
        ctk.CTkLabel(sp, justify="left", anchor="w", text_color=("gray35", "gray65"),
                     text="Einmalig: im Spotify Developer Dashboard eine App anlegen, als Redirect-URI\n"
                          "http://127.0.0.1:8888/callback eintragen und die Client-ID hier einfügen "
                          "(Details: README)."
                     ).grid(row=1, column=0, columnspan=3, sticky="ew", padx=12)
        ctk.CTkLabel(sp, text="Client-ID:").grid(row=2, column=0, sticky="w", padx=12, pady=6)
        self.ent_client_id = ctk.CTkEntry(sp)
        self.ent_client_id.insert(0, self.einst["spotify_client_id"])
        self.ent_client_id.grid(row=2, column=1, columnspan=2, sticky="ew", padx=(0, 12))
        zeile = ctk.CTkFrame(sp, fg_color="transparent")
        zeile.grid(row=3, column=0, columnspan=3, sticky="w", padx=12, pady=10)
        ctk.CTkButton(zeile, text="Bei Spotify anmelden",
                      command=self._spotify_anmelden).pack(side="left")
        ctk.CTkButton(zeile, text="Abmelden", width=100, fg_color="transparent", border_width=1,
                      text_color=("gray10", "gray90"),
                      command=self._spotify_abmelden).pack(side="left", padx=8)
        self.lbl_sp_konto = ctk.CTkLabel(zeile, text="")
        self.lbl_sp_konto.pack(side="left", padx=8)

    # ------------------------------------------------------- Reiter Einstellungen
    def _baue_reiter_einstellungen(self, tab) -> None:
        tab.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(tab, text="Stream-Port:").grid(row=0, column=0, sticky="w", padx=12, pady=(14, 6))
        self.ent_port = ctk.CTkEntry(tab, width=100)
        self.ent_port.insert(0, str(self.einst["port"]))
        self.ent_port.grid(row=0, column=1, sticky="w")

        ctk.CTkLabel(tab, text="MP3-Bitrate:").grid(row=1, column=0, sticky="w", padx=12, pady=6)
        self.opt_bitrate = ctk.CTkOptionMenu(tab, values=BITRATEN, width=100)
        self.opt_bitrate.set(self.einst["bitrate"])
        self.opt_bitrate.grid(row=1, column=1, sticky="w")

        # Weitere Netze fuer die Suche (Lautsprecher hinter Router/VPN)
        ctk.CTkLabel(tab, text="Weitere Netze:").grid(row=2, column=0, sticky="w", padx=12, pady=6)
        self.ent_netze = ctk.CTkEntry(tab, placeholder_text="z. B. 192.168.20.0/24 (mehrere mit Komma)")
        self.ent_netze.insert(0, ", ".join(self.einst["such_netze"]))
        self.ent_netze.grid(row=2, column=1, sticky="ew", padx=(0, 12))

        ctk.CTkButton(tab, text="Speichern", width=120,
                      command=self._einstellungen_speichern
                      ).grid(row=3, column=0, sticky="w", padx=12, pady=10)
        # Fuer alle Benutzer speichern (Terminalserver): Netze, Geraete, Konten, Stream-Optionen
        ctk.CTkButton(tab, text="Für alle Benutzer speichern", width=200,
                      command=self._fuer_alle_speichern
                      ).grid(row=3, column=1, sticky="w", pady=10)

        # Programm-Status: ffmpeg und yt-dlp muessen vorhanden sein
        ffmpeg = finde_programm("ffmpeg")
        ytdlp = finde_programm("yt-dlp")
        ctk.CTkLabel(tab, justify="left", anchor="w", text=(
            f"ffmpeg:  {ffmpeg or 'NICHT GEFUNDEN'}\n"
            f"yt-dlp:  {ytdlp or 'NICHT GEFUNDEN'}\n\n"
            "Fehlt etwas: in der Eingabeaufforderung  winget install yt-dlp.yt-dlp  und\n"
            "winget install Gyan.FFmpeg  ausführen (danach Programm neu starten),\n"
            "oder die .exe-Dateien in den Ordner „tools“ neben dieser Anwendung legen."
        )).grid(row=4, column=0, columnspan=2, sticky="ew", padx=12, pady=6)

        ctk.CTkLabel(tab, anchor="w",
                     text="Windows-Firewall: Lässt Windows die Lautsprecher nicht auf den Stream "
                          "zugreifen,\nin einer Eingabeaufforderung als Administrator ausführen:"
                     ).grid(row=5, column=0, columnspan=2, sticky="ew", padx=12, pady=(14, 2))
        self.txt_firewall = ctk.CTkTextbox(tab, height=60, wrap="word")
        self.txt_firewall.grid(row=6, column=0, columnspan=2, sticky="ew", padx=12)
        self.txt_firewall.insert("1.0", FIREWALL_BEFEHL.format(port=self.einst["port"],
                                                            ende=self.einst["port"] + PORT_BEREICH - 1))

    # ------------------------------------------------------------ Player-Leiste
    def _baue_playerleiste(self) -> None:
        leiste = ctk.CTkFrame(self)
        leiste.grid(row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 12))
        leiste.grid_columnconfigure(0, weight=1)

        self.lbl_titel = ctk.CTkLabel(leiste, text="Keine Wiedergabe", anchor="w",
                                      font=ctk.CTkFont(size=15, weight="bold"))
        self.lbl_titel.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 0))
        self.lbl_status = ctk.CTkLabel(leiste, text="Bereit.", anchor="w",
                                       text_color=("gray35", "gray65"))
        self.lbl_status.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 10))

        tasten = ctk.CTkFrame(leiste, fg_color="transparent")
        tasten.grid(row=0, column=1, rowspan=2, padx=14)
        ctk.CTkButton(tasten, text="⏮", width=48, command=self._voriger).pack(side="left", padx=3)
        self.btn_pause = ctk.CTkButton(tasten, text="⏸", width=48, command=self._pause_umschalten)
        self.btn_pause.pack(side="left", padx=3)
        ctk.CTkButton(tasten, text="⏹", width=48, command=self._stoppen).pack(side="left", padx=3)
        ctk.CTkButton(tasten, text="⏭", width=48, command=self._naechster).pack(side="left", padx=3)

    # ====================================================================
    # Lautsprecher: suchen, waehlen, Lautstaerke
    # ====================================================================
    def _boxen_suchen(self) -> None:
        self.btn_suchen.configure(state="disabled", text="Suche läuft …")
        self._status("Suche Lautsprecher im Netzwerk …")

        def arbeit() -> None:
            # Zusaetzlich: Netze hinter Router/VPN per Unicast absuchen und
            # bekannte Geraete-URLs (manuell + zuletzt benutzt) direkt abfragen
            bekannte = list(self.einst["manuelle_boxen"]) + [self.einst["letzte_box"]]
            gefunden = renderer_suchen(timeout=4.0,
                                       zusatz_netze=list(self.einst["such_netze"]),
                                       bekannte_urls=bekannte)
            self._ui(lambda: self._boxen_anzeigen(gefunden))
        self._hintergrund(arbeit)

    def _boxen_anzeigen(self, gefunden: list[Renderer]) -> None:
        """Traegt die Suchergebnisse in die Liste ein (Hauptthread)."""
        self.btn_suchen.configure(state="normal", text="🔍  Im Netzwerk suchen")
        # Manuell hinzugefuegte Geraete behalten, die die Suche nicht gefunden hat
        bekannt = {r.location for r in gefunden}
        self.boxen = gefunden + [r for r in self.boxen if r.location not in bekannt
                                 and getattr(r, "manuell", False)]
        for widget in self.box_liste.winfo_children():
            widget.destroy()
        if not self.boxen:
            ctk.CTkLabel(self.box_liste, justify="left", text_color=("gray35", "gray65"),
                         text="Nichts gefunden.\nAnderes Netz (VPN)? Dann unter\n"
                              "„Einstellungen“ das Netz der\nLautsprecher eintragen.\n"
                              "Notfalls die Geräte-URL\nmanuell eintragen."
                         ).pack(padx=6, pady=6)
            self._status("Keine Lautsprecher gefunden.")
            return
        for r in self.boxen:
            ctk.CTkRadioButton(self.box_liste, text=f"{r.name}\n{r.host}",
                               variable=self.var_box, value=r.location,
                               command=self._box_gewaehlt).pack(anchor="w", padx=6, pady=5)
        self._status(f"{len(self.boxen)} Gerät(e) gefunden.")
        # Zuletzt benutzten Lautsprecher automatisch wieder auswaehlen
        letzte = self.einst["letzte_box"]
        if any(r.location == letzte for r in self.boxen):
            self.var_box.set(letzte)
            self._box_gewaehlt()

    def _box_manuell(self) -> None:
        url = self.ent_location.get().strip()
        if not url:
            return

        def arbeit() -> None:
            r = renderer_laden(url)
            if r is None:
                self._status("Unter dieser URL wurde kein nutzbares Gerät gefunden.")
                return
            r.manuell = True  # type: ignore[attr-defined]
            # URL dauerhaft merken, damit das Geraet bei jeder Suche wieder erscheint
            liste = list(self.einst["manuelle_boxen"])
            if url not in liste:
                liste.append(url)
                self.einst["manuelle_boxen"] = liste
            def eintragen() -> None:
                self.boxen = [x for x in self.boxen if x.location != r.location] + [r]
                self._boxen_anzeigen(list(self.boxen))
                self.var_box.set(r.location)
                self._box_gewaehlt()
            self._ui(eintragen)
        self._hintergrund(arbeit)

    def _box_gewaehlt(self) -> None:
        """Ein Lautsprecher wurde angeklickt: merken und Lautstaerke auslesen."""
        location = self.var_box.get()
        self.gewaehlt = next((r for r in self.boxen if r.location == location), None)
        if not self.gewaehlt:
            return
        self.einst["letzte_box"] = location
        box = self.gewaehlt
        self._status(f"Ausgewählt: {box.name}")

        def arbeit() -> None:
            try:
                wert = hole_lautstaerke(box)
            except RuntimeError:
                return  # Lautstaerke nicht lesbar -> Regler bleibt unveraendert
            self._ui(lambda: (self.slider_vol.set(wert),
                              self.lbl_vol.configure(text=f"{wert} %")))
        self._hintergrund(arbeit)

    def _lautstaerke_geaendert(self, wert: float) -> None:
        """Regler bewegt: Anzeige sofort, Senden erst nach kurzer Ruhe (Entprellen)."""
        self.lbl_vol.configure(text=f"{int(wert)} %")
        if self._vol_job:
            self.after_cancel(self._vol_job)
        self._vol_job = self.after(300, self._lautstaerke_senden)

    def _lautstaerke_senden(self) -> None:
        wert = int(self.slider_vol.get())
        box = self.gewaehlt
        modus = self.modus
        geraet = self._spotify_geraete_id()

        def arbeit() -> None:
            if modus == "spotify" and geraet:
                self.spotify.lautstaerke(geraet, wert)
            elif box:
                setze_lautstaerke(box, wert)
            else:
                self._status("Bitte zuerst einen Lautsprecher wählen.")
        self._hintergrund(arbeit)

    # ====================================================================
    # YouTube / YT Music
    # ====================================================================
    def _optionen_speichern(self) -> None:
        self.einst["nur_einzeltitel"] = bool(self.var_einzeln.get())
        self.einst["zufall"] = bool(self.var_zufall.get())

    def _datei_waehlen(self) -> None:
        pfad = filedialog.askopenfilename(
            title="Audiodatei wählen",
            filetypes=[("Audio", "*.mp3 *.flac *.wav *.m4a *.ogg *.opus *.aac"),
                       ("Alle Dateien", "*.*")])
        if pfad:
            self.ent_quelle.delete(0, "end")
            self.ent_quelle.insert(0, pfad)

    def _youtube_abspielen(self, text: str | None = None) -> None:
        """Eingabe aufloesen und die Wiedergabe starten."""
        eingabe = (text if text is not None else self.ent_quelle.get()).strip()
        if not eingabe:
            self._status("Bitte einen Link oder Suchbegriff eingeben.")
            return
        if not self.gewaehlt:
            self._status("Bitte zuerst links einen Lautsprecher wählen.")
            return
        einzeln = bool(self.var_einzeln.get())
        mischen = bool(self.var_zufall.get())
        cookie_args = self._cookie_args()
        self._status("Lese Titelinfos …")

        def arbeit() -> None:
            liste, fehler = titel_liste_aufbauen([eingabe], cookie_args, einzeln)
            if not liste:
                self._status(fehler[0] if fehler else "Keine abspielbaren Titel gefunden.")
                return
            self._wiedergabe_starten(liste, mischen)
        self._hintergrund(arbeit)

    def _cookie_args(self) -> list[str]:
        return cookie_argumente(self.einst["browser_cookies"], self.einst["cookies_datei"])

    # --- Favoriten ---------------------------------------------------------
    def _favorit_speichern(self) -> None:
        url = self.ent_quelle.get().strip()
        if not url:
            self._status("Zum Speichern erst einen Link eingeben.")
            return
        name = ctk.CTkInputDialog(text="Name für den Favoriten:", title="Favorit speichern").get_input()
        if name:
            favoriten = list(self.einst["favoriten"])
            favoriten.append({"name": name.strip(), "url": url})
            self.einst["favoriten"] = favoriten
            self._favoriten_anzeigen()

    def _favoriten_anzeigen(self) -> None:
        for widget in self.fav_liste.winfo_children():
            widget.destroy()
        favoriten = self.einst["favoriten"]
        if not favoriten:
            ctk.CTkLabel(self.fav_liste, text="Noch keine Favoriten.",
                         text_color=("gray35", "gray65")).pack(pady=8)
        for index, fav in enumerate(favoriten):
            zeile = ctk.CTkFrame(self.fav_liste, fg_color="transparent")
            zeile.pack(fill="x", pady=2)
            ctk.CTkLabel(zeile, text=fav["name"], anchor="w").pack(side="left", padx=6)
            ctk.CTkButton(zeile, text="🗑", width=34, fg_color="transparent", border_width=1,
                          text_color=("gray10", "gray90"),
                          command=lambda i=index: self._favorit_loeschen(i)).pack(side="right", padx=2)
            ctk.CTkButton(zeile, text="▶", width=34,
                          command=lambda u=fav["url"]: self._youtube_abspielen(u)
                          ).pack(side="right", padx=2)

    def _favorit_loeschen(self, index: int) -> None:
        favoriten = list(self.einst["favoriten"])
        if 0 <= index < len(favoriten):
            del favoriten[index]
            self.einst["favoriten"] = favoriten
            self._favoriten_anzeigen()

    # ====================================================================
    # Wiedergabe (gemeinsam fuer YouTube und Spotify-ueber-YT)
    # ====================================================================
    def _server_sicherstellen(self) -> StreamServer:
        """Startet den Stream-Server (oder startet ihn bei neuem Port/Bitrate neu)."""
        port = int(self.einst["port"])
        bitrate = self.einst["bitrate"]
        # Vergleich mit dem eingestellten Basis-Port (der Server laeuft evtl. auf einem hoeheren)
        if self.server and (self._server_basisport != port or self.server.bitrate != bitrate):
            if self.player:
                self.player.beenden()
            self.server.beenden()
            self.server = None
        if self.server is None:
            # Freien Port suchen (mehrere Sitzungen auf einem Terminalserver)
            letzter_fehler: OSError | None = None
            for kandidat in range(port, min(port + PORT_BEREICH, 65536)):
                try:
                    self.server = StreamServer(kandidat, bitrate, self._cookie_args())
                    break
                except OSError as exc:
                    letzter_fehler = exc
            if self.server is None:
                raise RuntimeError(f"Kein freier Port zwischen {port} und {port + PORT_BEREICH - 1}: "
                                   f"{letzter_fehler}")
            self._server_basisport = port
            self.server.starten()
        self.server.cookie_args = self._cookie_args()  # evtl. geaenderte Anmeldung
        return self.server

    def _wiedergabe_starten(self, liste: list[Titel], mischen: bool) -> None:
        """Im Hintergrund-Thread aufrufen: Warteschlange auf dem Lautsprecher starten."""
        box = self.gewaehlt
        if box is None:
            self._status("Bitte zuerst einen Lautsprecher wählen.")
            return
        for programm in ("ffmpeg", "yt-dlp"):
            if finde_programm(programm) is None:
                self._status(f"„{programm}“ fehlt – siehe Reiter „Einstellungen“.")
                return
        if self.player:                                  # laufende Wiedergabe beenden
            self.player.beenden()
        server = self._server_sicherstellen()
        eigene_ip = lokale_ip_zu(box.host)
        self.modus = "upnp"
        self.pausiert = False
        self._ui(lambda: self.btn_pause.configure(text="⏸"))

        def bei_titel(index: int, gesamt: int, name: str) -> None:
            self._ui(lambda: self.lbl_titel.configure(text=f"▶ {name}"))
            self._status(f"Titel {index + 1} von {gesamt} auf „{box.name}“")

        def bei_ende() -> None:
            self._ui(lambda: self.lbl_titel.configure(text="Keine Wiedergabe"))
            self._status("Warteschlange beendet.")

        self.player = Wiedergabe(box, server, eigene_ip, bei_titel, self._status, bei_ende)
        self.player.starte(liste, mischen)

    # --- Transport-Tasten (unten) -------------------------------------------
    def _pause_umschalten(self) -> None:
        modus, geraet, player = self.modus, self._spotify_geraete_id(), self.player
        pausiert = self.pausiert

        def arbeit() -> None:
            if modus == "spotify" and geraet:
                (self.spotify.fortsetzen if pausiert else self.spotify.pause)(geraet)
            elif player:
                (player.fortsetzen if pausiert else player.pause)()
            else:
                return
            self.pausiert = not pausiert
            self._ui(lambda: self.btn_pause.configure(text="▶" if self.pausiert else "⏸"))
        self._hintergrund(arbeit)

    def _naechster(self) -> None:
        modus, geraet, player = self.modus, self._spotify_geraete_id(), self.player

        def arbeit() -> None:
            if modus == "spotify" and geraet:
                self.spotify.naechster(geraet)
            elif player:
                player.naechster()
        self._hintergrund(arbeit)

    def _voriger(self) -> None:
        modus, geraet, player = self.modus, self._spotify_geraete_id(), self.player

        def arbeit() -> None:
            if modus == "spotify" and geraet:
                self.spotify.voriger(geraet)
            elif player:
                player.voriger()
        self._hintergrund(arbeit)

    def _stoppen(self) -> None:
        modus, geraet, player = self.modus, self._spotify_geraete_id(), self.player

        def arbeit() -> None:
            if modus == "spotify" and geraet:
                self.spotify.pause(geraet)   # die Web API kennt kein "Stop" - Pause genuegt
            elif player:
                player.beenden()
            self.pausiert = False
            self._ui(lambda: (self.btn_pause.configure(text="⏸"),
                              self.lbl_titel.configure(text="Keine Wiedergabe")))
            self._status("Gestoppt.")
        self._hintergrund(arbeit)

    # ====================================================================
    # Spotify
    # ====================================================================
    def _spotify_geraete_id(self) -> str | None:
        """ID des im Reiter 'Spotify' gewaehlten Connect-Geraets (oder None)."""
        return self.spotify_geraete.get(self.opt_sp_geraet.get())

    def _spotify_status_aktualisieren(self) -> None:
        if self.spotify.angemeldet():
            text = "Angemeldet ✔"
            self._spotify_aktualisieren()
        else:
            text = "Nicht angemeldet – bitte im Reiter „Konten“ anmelden."
        self.lbl_sp_status.configure(text=f"Spotify: {text}")
        self.lbl_sp_konto.configure(text=text)

    def _spotify_anmelden(self) -> None:
        client_id = self.ent_client_id.get().strip()
        if not client_id:
            messagebox.showinfo("Spotify", "Bitte zuerst die Client-ID eintragen (siehe README).")
            return
        self.einst["spotify_client_id"] = client_id
        self.spotify.client_id = client_id
        self._status("Browser öffnet sich – bitte bei Spotify anmelden …")

        def arbeit() -> None:
            self.spotify.anmelden()
            self._ui(self._spotify_status_aktualisieren)
            self._status("Spotify-Anmeldung erfolgreich.")
        self._hintergrund(arbeit)

    def _spotify_abmelden(self) -> None:
        self.spotify.abmelden()
        self.spotify_geraete = {}
        self._spotify_status_aktualisieren()
        for widget in self.sp_liste.winfo_children():
            widget.destroy()

    def _spotify_aktualisieren(self) -> None:
        """Laedt Playlists und Connect-Geraete neu."""
        def arbeit() -> None:
            playlists = self.spotify.playlists()
            geraete = self.spotify.geraete()
            self._ui(lambda: self._spotify_anzeigen(playlists, geraete))
        self._hintergrund(arbeit)

    def _spotify_anzeigen(self, playlists: list[dict], geraete: list[dict]) -> None:
        # Geraeteliste fuellen; Raumfeld-Box bevorzugen, falls der Name passt (Annahme!)
        self.spotify_geraete = {g["name"]: g["id"] for g in geraete if g.get("id")}
        namen = list(self.spotify_geraete) or ["(keine gefunden)"]
        self.opt_sp_geraet.configure(values=namen)
        passend = None
        if self.gewaehlt:
            box_name = self.gewaehlt.name.lower()
            passend = next((n for n in namen if n.lower() in box_name
                            or box_name in n.lower()), None)
        self.opt_sp_geraet.set(passend or namen[0])

        for widget in self.sp_liste.winfo_children():
            widget.destroy()
        for p in playlists:
            zeile = ctk.CTkFrame(self.sp_liste, fg_color="transparent")
            zeile.pack(fill="x", pady=2)
            ctk.CTkLabel(zeile, text=p.get("name", "?"), anchor="w").pack(side="left", padx=6)
            ctk.CTkButton(zeile, text="via YT Music", width=100,
                          command=lambda i=p["id"]: self._spotify_ueber_youtube(i)
                          ).pack(side="right", padx=2)
            ctk.CTkButton(zeile, text="Connect", width=80,
                          command=lambda i=p["id"]: self._spotify_connect(i)
                          ).pack(side="right", padx=2)
        self._status(f"Spotify: {len(playlists)} Playlists, {len(geraete)} Connect-Gerät(e).")

    def _spotify_link(self, per_connect: bool) -> None:
        playlist_id = playlist_id_aus_text(self.ent_sp_link.get())
        if not playlist_id:
            self._status("Das sieht nicht nach einem Spotify-Playlist-Link aus.")
            return
        (self._spotify_connect if per_connect else self._spotify_ueber_youtube)(playlist_id)

    def _spotify_connect(self, playlist_id: str) -> None:
        """Playlist ueber Spotify Connect auf dem gewaehlten Geraet starten."""
        geraet = self._spotify_geraete_id()
        if not geraet:
            self._status("Kein Spotify-Connect-Gerät gewählt/gefunden (↻ Aktualisieren).")
            return

        def arbeit() -> None:
            if self.player:                    # evtl. laufende YouTube-Wiedergabe beenden
                self.player.beenden()
            self.spotify.wiedergabe_starten(geraet, playlist_id)
            self.modus = "spotify"
            self.pausiert = False
            self._ui(lambda: (self.btn_pause.configure(text="⏸"),
                              self.lbl_titel.configure(text="▶ Spotify Connect")))
            self._status("Spotify-Wiedergabe gestartet.")
        self._hintergrund(arbeit)

    def _spotify_ueber_youtube(self, playlist_id: str) -> None:
        """Titelnamen von Spotify lesen, bei YouTube suchen und abspielen."""
        if not self.gewaehlt:
            self._status("Bitte zuerst links einen Lautsprecher wählen.")
            return
        mischen = bool(self.var_zufall.get())
        self._status("Lese Spotify-Playlist …")

        def arbeit() -> None:
            namen = self.spotify.playlist_titel(playlist_id)
            if not namen:
                self._status("Die Playlist enthält keine lesbaren Titel.")
                return
            # "ytsearch1:" laesst yt-dlp erst beim Abspielen den ersten Treffer suchen
            liste = [Titel(f"ytsearch1:{n}", n) for n in namen]
            self._wiedergabe_starten(liste, mischen)
        self._hintergrund(arbeit)

    # ====================================================================
    # Konten / Einstellungen
    # ====================================================================
    def _cookies_datei_waehlen(self) -> None:
        pfad = filedialog.askopenfilename(title="cookies.txt wählen",
                                          filetypes=[("Text", "*.txt"), ("Alle", "*.*")])
        if pfad:
            self.ent_cookies.delete(0, "end")
            self.ent_cookies.insert(0, pfad)

    def _yt_konto_testen(self) -> None:
        """Speichert die Auswahl und prueft, ob 'Gefaellt mir'-Titel lesbar sind."""
        self.einst["browser_cookies"] = self.opt_browser.get()
        self.einst["cookies_datei"] = self.ent_cookies.get().strip()
        cookie_args = self._cookie_args()
        if not cookie_args:
            self.lbl_yt_konto.configure(text="Gespeichert (ohne Anmeldung).")
            return
        ytdlp = finde_programm("yt-dlp")
        if ytdlp is None:
            self.lbl_yt_konto.configure(text="yt-dlp nicht gefunden.")
            return
        self.lbl_yt_konto.configure(text="Teste …")

        def arbeit() -> None:
            # Playlist "LM" = "Liked Music"; nur mit gueltiger Anmeldung lesbar (Annahme)
            proc = subprocess.run(
                [ytdlp, "--flat-playlist", "--playlist-items", "1", "--no-warnings",
                 "--print", "%(title)s", *cookie_args,
                 "https://music.youtube.com/playlist?list=LM"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                creationflags=KEIN_FENSTER, timeout=90)
            if proc.stdout.strip():
                ergebnis = "Anmeldung funktioniert ✔"
            else:
                letzte = (proc.stderr.strip().splitlines() or ["unbekannter Fehler"])[-1]
                ergebnis = f"Fehlgeschlagen: {letzte[:110]}"
            self._ui(lambda: self.lbl_yt_konto.configure(text=ergebnis))
        self._hintergrund(arbeit)

    def _einstellungen_speichern(self) -> None:
        try:
            port = int(self.ent_port.get())
            if not 1024 <= port <= 65535:
                raise ValueError
        except ValueError:
            messagebox.showerror("Einstellungen", "Der Port muss zwischen 1024 und 65535 liegen.")
            return
        # Weitere Netze pruefen: jede Angabe muss ein gueltiges IPv4-Netz sein
        netze = [n.strip() for n in self.ent_netze.get().replace(";", ",").split(",") if n.strip()]
        ungueltig = [n for n in netze if not netz_adressen([n])]
        if ungueltig:
            messagebox.showerror("Einstellungen", "Ungültige Netzangabe: " + ", ".join(ungueltig)
                                 + "\nBeispiel: 192.168.20.0/24")
            return
        # Nur geaenderte Werte setzen: unveraenderte Werte bleiben so weiterhin
        # die gemeinsamen (fuer alle Benutzer) und werden nicht ueberdeckt.
        neu = {"port": port, "bitrate": self.opt_bitrate.get(), "such_netze": netze}
        for schluessel, wert in neu.items():
            if self.einst[schluessel] != wert:
                self.einst[schluessel] = wert
        self.txt_firewall.delete("1.0", "end")
        self.txt_firewall.insert("1.0", FIREWALL_BEFEHL.format(port=port, ende=port + PORT_BEREICH - 1))
        self._status("Einstellungen gespeichert (gelten ab dem nächsten Abspielen).")

    def _fuer_alle_speichern(self) -> None:
        """
        Speichert Netze, Geraete, Konten-Einstellungen und Stream-Optionen in
        die gemeinsame Datei (alle Benutzer). Ein eventuelles Spotify-Token
        wird mitkopiert. Braucht Schreibrechte (meist Administrator).
        """
        self._einstellungen_speichern()  # zuerst die Eingaben im Reiter uebernehmen
        if not messagebox.askyesno(
                "Für alle Benutzer speichern",
                "Netze, Geräte, Favoriten, YouTube-Anmeldung, Spotify-Client-ID und "
                "Stream-Einstellungen gelten danach für alle Benutzer dieses Rechners.\n\n"
                "Ist Spotify angemeldet, wird auch die Anmeldung geteilt – alle Benutzer "
                "steuern dann dasselbe Spotify-Konto.\n\nFortfahren?"):
            return
        try:
            pfad = self.einst.fuer_alle_speichern()
            eigenes_token = konfig_ordner() / "spotify_token.json"
            if eigenes_token.exists():
                # Token kopieren; Datei ist danach fuer alle lesbar (nicht verschluesselt)
                (pfad.parent / "spotify_token.json").write_bytes(eigenes_token.read_bytes())
        except OSError as exc:
            messagebox.showerror(
                "Für alle Benutzer speichern",
                f"Keine Schreibrechte auf\n{self.einst.gemeinsame_datei.parent}\n\n"
                "Das Programm einmal als Administrator starten und erneut speichern.\n\n"
                f"Fehler: {exc}")
            return
        self._status(f"Für alle Benutzer gespeichert: {pfad}")

    # ====================================================================
    # Beenden
    # ====================================================================
    def _beenden(self) -> None:
        """Fenster schliessen: Wiedergabe stoppen, Server beenden."""
        try:
            if self.player:
                self.player.beenden()
            if self.server:
                self.server.beenden()
        finally:
            self.destroy()


def starten() -> None:
    """Einstiegspunkt fuer __main__ und start.pyw."""
    App().mainloop()
