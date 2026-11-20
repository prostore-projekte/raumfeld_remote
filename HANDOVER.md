# Handover – Raumfeld Remote

Stand: 20.11.2026 · Version 0.14.0 · Repo: <https://github.com/prostore-projekte/raumfeld_remote> (Branch `claude/ecstatic-mayer-gfo8yn`)

**Kurz:** Zwei Varianten – Desktop-Programm (Einzelplatz, funktioniert bei Sascha) und **zentraler Dienst mit
Web-Oberfläche + Installer** fürs Büro (Hauptweg, Abschnitt 7a; auf dem Terminalserver noch nicht installiert).
Nächste Schritte: Abschnitt 8.

Dieses Dokument fasst alles zusammen, was bisher passiert ist, damit eine neue Sitzung ohne Vorgeschichte weiterarbeiten kann.

## 1. Ziel
Teufel-Raumfeld-Lautsprecher (z. B. Stereo Cubes) **ohne Raumfeld-App** steuern. Der Nutzer hat dafür ein funktionierendes Linux-Skript (`raumcast.py`) und wollte eine **Windows-11-Version mit GUI**.

Anforderungen des Nutzers:
- Windows 11
- Menü zum **Verknüpfen von YT Music, YouTube und Spotify**
- **Übersichtliche GUI**
- **Lautstärke** der Boxen einstellbar
- Tool **sucht die Boxen im Netzwerk** selbst

## 2. Ausgangslage
- `raumcast.py` (Linux, Kommandozeile) wurde vom Nutzer **getestet, funktioniert**.
- Funktionsprinzip: SSDP-Suche → lokaler HTTP-Server → `yt-dlp` holt Audio → `ffmpeg` wandelt live in MP3 → Lautsprecher bekommt per UPnP/SOAP `SetAVTransportURI` + `Play`.
- Getesteter Aufruf (Linux):
  ```
  python3 raumcast.py --location http://192.168.20.145:60092/b5c2b4ff-de1d-4a91-90f5-346d33e801e2.xml \
      play 'https://music.youtube.com/playlist?list=PLB6JGtWhYe2dB4-Bp7D2uRa9_wq4mWFgX' --volume 10
  ```
- Entwicklungssystem des Nutzers: TUXEDO OS (KDE Plasma 6.7.4, Wayland), Zielplattform des Tools: Windows 11.

## 3. Was gebaut wurde
Komplettes Projekt, geliefert als `raumfeld_remote.zip` (Ordner `raumfeld_remote/`):

| Datei | Inhalt |
|---|---|
| `raumfeld_remote/upnp.py` | SSDP-Suche **über jede lokale IPv4-Adresse einzeln** (Windows hat oft mehrere Adapter), Geräte-XML lesen, SOAP-Aufrufe, Lautstärke lesen/setzen, DIDL-Metadaten |
| `raumfeld_remote/quellen.py` | `yt-dlp`/`ffmpeg` finden (Ordner `tools` neben der App, sonst PATH), Cookie-Argumente, Links/Playlists/Suchbegriffe/Dateien → Titelliste (`Titel`) |
| `raumfeld_remote/stream_server.py` | HTTP-Server `yt-dlp → ffmpeg → MP3`, Windows-tauglich (`CREATE_NO_WINDOW`, `stderr=DEVNULL`, `ConnectionError` abgefangen) |
| `raumfeld_remote/player.py` | `Wiedergabe`: Warteschlange im Thread, Weiter/Zurück/Pause/Stop |
| `raumfeld_remote/spotify.py` | OAuth mit PKCE (Redirect `http://127.0.0.1:8888/callback`), Playlists, Connect-Geräte, Wiedergabesteuerung, Titelnamen lesen |
| `raumfeld_remote/einstellungen.py` | JSON-Einstellungen in `%APPDATA%/RaumfeldRemote/` |
| `raumfeld_remote/gui.py` | customtkinter-Oberfläche |
| `start.pyw`, `start.bat`, `installieren.bat`, `build_exe.bat` | Starter, Einrichtung, optionale `.exe` (PyInstaller) |
| `README.md`, `CHANGELOG.md`, `requirements.txt`, `.gitignore` | Doku und Projektdateien |
| `CLAUDE.md`, `HANDOVER.md` | Arbeitsanweisungen für Claude, dieses Übergabedokument (seit 0.1.1) |

### GUI-Aufbau
- **Links:** Lautsprecher (Suchbutton, Liste, manuelles Hinzufügen per Geräte-URL), Lautstärkeregler (mit Entprellen, liest beim Auswählen den aktuellen Wert).
- **Rechts, Reiter:** *YouTube / YT Music* (Link/Suchbegriff/Datei, „Nur diesen Titel“, Zufall, Favoriten) · *Spotify* · *Konten* · *Einstellungen* (Port, Bitrate, Programmstatus, Firewall-Befehl).
- **Unten:** Titelanzeige, Statuszeile, Tasten ⏮ ⏸ ⏹ ⏭.
- Threading: Netzwerk-/Prozessarbeit nur in Hintergrund-Threads; GUI-Updates über eine Queue (`_ui` / `_ui_pumpe`).

### Verknüpfung der Dienste (Reiter „Konten“)
- **YouTube / YT Music:** `yt-dlp` liest Cookies aus dem Browser (Auswahl: firefox, chrome, edge, brave, …) oder aus einer `cookies.txt`. Test-Button prüft die Playlist „LM“ (Gefällt mir).
- **Spotify:** Client-ID aus eigener Spotify-Developer-App eintragen, Anmeldung im Browser. Zwei Wiedergabewege:
  1. **Spotify Connect** (Spotify spielt selbst, Tool steuert per Web API)
  2. **Via YT Music** (Titelnamen von Spotify lesen, per `ytsearch1:` bei YouTube suchen und abspielen)

## 4. Entscheidungen und Begründungen
- Spotify-Audio ist DRM-geschützt → nicht per `yt-dlp` ladbar → deshalb die zwei Wege oben.
- MP3-Umweg über `ffmpeg` beibehalten (wie im Linux-Skript bewährt): praktisch jeder UPnP-Renderer spielt MP3.
- customtkinter statt Qt/Web: einzige Abhängigkeit, läuft auf Windows 11 ohne Zusatzaufwand.
- Spotify per PKCE: kein Client-Secret nötig.

## 5. Teststand (ehrlich)
- ✔ Syntaxprüfung aller Dateien, `pyflakes` ohne Befund
- ✔ Stream-Server mit lokaler WAV-Datei → lieferte gültigen MP3-Stream (Linux-Sandbox)
- ✔ Windows 11 (Nutzer, 19.11.2026): `installieren.bat` läuft durch (customtkinter 6.0.0), Programm startet, Suche findet aber nur einen Samsung-TV
- ✔ Unicast-Suche (0.3.0): Nutzer meldet „Läuft“ (Boxen über VPN gefunden)
- ✔ 0.4.0: Zwei-Ebenen-Einstellungen lokal getestet (anderer Benutzer sieht gemeinsame Werte); `start.bat` wird im
  Windows-Build von frischem Stand getestet.
  CI-Lauf 1: Installation durch `start.bat` erfolgreich, Prüfung im Folgeschritt fand kein `pythonw` →
  Prüfung in denselben Schritt verlegt; CI-Lauf 2 grün (Oberfläche läuft nach 10 s). Zusätzlich:
  `start.pyw` schreibt jetzt Startfehler nach `%APPDATA%\RaumfeldRemote\fehler.log`, CI gibt es aus.
  Auf echtem Terminalserver mit mehreren Benutzern **ungetestet**.
- Nutzer (Terminalserver): ffmpeg-Download über PowerShell 5.1 sehr langsam (Fortschrittsanzeige) → 0.4.1 nutzt `curl.exe`.
- **Offen (Nutzer, Terminalserver):** Lautstärke regeln funktioniert, YouTube-Konto-Test ok, Anzeige „spielt“, aber **kein Ton**.
  Ursache unbekannt. Vermutung: Box erreicht den Stream-Server auf dem Terminalserver nicht (Firewall/VPN-Routing)
  oder yt-dlp/ffmpeg scheitern. 0.5.0 bringt Diagnose (Stream-Protokoll, Abruf-Prüfung).
  **Befund:** Auf dem Terminalserver gab es **keine Firewall-Regel** „Raumfeld Remote“ → sehr wahrscheinliche Ursache.
  Nutzer soll Regel setzen; `start.bat` legt sie ab 0.5.0 als Administrator selbst an.
  **Nachtrag:** Regel gesetzt – trotzdem **kein Ton**. Ursache weiter offen. 0.6.0: Live-Protokoll in der GUI
  (UPnP-Befehle, Zustände, Abrufe, yt-dlp/ffmpeg-Fehler).
  **Ursache gefunden (Protokoll des Nutzers):** Box ruft Stream ab (Netz/Firewall OK), aber yt-dlp meldet
  „Signature/n challenge solving failed … JavaScript runtime“ und „Requested format is not available“ → 0 KB.
  0.7.0: deno als JavaScript-Laufzeit (`--js-runtimes deno:PFAD`, Option in yt-dlp 2026.10.26 geprüft),
  `start.bat` lädt deno und aktualisiert yt-dlp. Lokaler Test gegen YouTube nicht möglich (Sandbox-Freigabe verweigert).
  ✔ **Bestätigt (Sascha, 20.11.2026): „Läuft“** – Desktop-Programm spielt mit deno über VPN auf den Boxen.
- Der Konto-Test (Playlist „LM“) prüft nur das Lesen der Playlist, nicht das Abspielen – „Konto ok“ heißt nicht „Audio ok“.
- ✘ **GUI vor 19.11.2026 nie ausgeführt** (der Sandbox fehlte `tkinter`, Installation hing)
- ✔ Desktop-Programm auf Windows mit echten Boxen (VPN) getestet; ✘ Spotify-Konto noch nie echt getestet
- ✘ `build_exe.bat` ungetestet
- Ab 0.2.0: Workflow `.github/workflows/windows-build.yml` baut die .exe auf `windows-latest` und prüft pyflakes,
  GUI-Import und einen 10-Sekunden-Starttest. Ergebnis siehe GitHub Actions (kein Test mit echter Hardware).

## 6. Unsicherheiten und Annahmen
- **Einsatz:** Programm soll auf einem **Terminalserver** laufen (mehrere Benutzer gleichzeitig). Gemeinsame Einstellungen
  in `%PROGRAMDATA%\RaumfeldRemote` – Annahme: normale Benutzer haben dort nur Leserechte, Admin speichert „für alle“.
- `winget install -e --id Python.Python.3.12 --scope machine` in `start.bat`: Paket-ID und `--scope machine` **nicht verifiziert**;
  auf Windows Server ist winget oft nicht installiert (dann Hinweis auf python.org).
- Spotify-Login-Callback auf Port 8888 ist pro Rechner nur einmal gleichzeitig nutzbar.
- **Netz des Nutzers:** PC in `192.168.10.0/24`, Lautsprecher in `192.168.20.0/24`, verbunden per VPN; Ping 10 → 20 geht.
  Multicast-SSDP kommt nicht über das VPN → Lösung 0.3.0: Unicast-M-SEARCH. Ob Raumfeld-Boxen auf Unicast antworten, ist **unbekannt**.
  Ob die Boxen den Stream-Server auf dem PC (Port 8765, über VPN) erreichen, ist **ungetestet**.
- **Dienst findet Boxen im anderen Netz nicht** (Sascha, 0.9.x, Netz eingetragen). Vermutete Ursache (**Annahme**, nicht
  verifiziert): Der Dienst hatte nur TCP-Port-Regeln; die UDP-Antworten auf die SSDP-Anfrage verwirft die Firewall.
  Das Desktop-Programm lief, weil Windows beim Start „Zugriff zulassen“ anbot (Programmregel inkl. UDP).
  0.10.0: Programmregel im Installer + Suchdiagnose im Protokoll. Weitere mögliche Ursache: Netzprofil „Öffentlich“
  (Regel gilt nur für Domäne/Privat).
  **Befund 0.11.0 (Sascha):** „254 Adressen angefragt, Antworten von keiner Adresse“, keine Sendefehler (Route da).
  Neue Vermutung (**Annahme**): Das Desktop-Programm fand die Boxen gar nicht per SSDP, sondern über die gemerkte
  `letzte_box`/`manuelle_boxen` (direkter HTTP-Abruf der Geräte-XML). Ob Raumfeld-Boxen auf Unicast-M-SEARCH antworten,
  bleibt unbekannt. 0.11.1: Dienst übernimmt diese URLs einmalig aus `%PROGRAMDATA%` und `C:\Users\*\AppData\Roaming\
  RaumfeldRemote\einstellungen.json` in `bekannte_boxen` und merkt sich jedes gefundene Gerät.
  **Befund 0.11.0 mit Firewall-Regel UDP/alle Profile (Sascha):** weiterhin keine Antwort → Firewall ist **nicht** die
  Ursache. Boxen antworten nicht auf Unicast-M-SEARCH über das VPN (oder Router filtert). Manuell eingetragen läuft es
  (`http://192.168.20.145:54631/<uuid>.xml`). **Achtung:** Port der Geräte-URL war früher `:60092`, jetzt `:54631` →
  ändert sich vermutlich bei Neustart der Box; gemerkte URLs können veralten. 0.13.0: `upnp.port_neu_suchen` tastet
  bei nicht antwortender gemerkter URL die Ports 49152–65535 des Hosts ab (256 parallel, 0,5 s Timeout) und ruft
  `/<uuid>.xml` ab; `Zentrale._ports_neu_suchen` ersetzt die URL in `manuelle_boxen`/`bekannte_boxen`.
  Portbereich ist eine **Annahme** (beide beobachteten Ports lagen darin). Lokal getestet, nicht mit echten Boxen.
- **Langsamer Start (Sascha, 0.11.0):** Playlist laden ~1 min, danach ~30 s Stille. Protokoll: Box ruft sofort ab,
  aber yt-dlp liefert in 20 s nur 64 KB (YouTube-Auswertung mit deno). 0.12.0: Playlist zweistufig (25 + Rest im
  Hintergrund, `Wiedergabe.anhaengen`), Titel vorab per `yt-dlp -j` vorbereitet (`StreamServer.vorbereiten`,
  `--load-info-json`, 3 h gültig), nächster Titel im Hintergrund. Nur mit nachgebautem yt-dlp getestet.
- Ob der Port in der Raumfeld-Geräte-URL (z. B. `:60092`) nach einem Neustart der Box gleich bleibt, ist **unbekannt**.
- Ob Raumfeld-Boxen in der Spotify-Geräteliste (Connect) erscheinen, ist **unbekannt** (hängt von Modell/Firmware ab). Die automatische Zuordnung Box ↔ Connect-Gerät per Namensvergleich ist eine **Annahme**.
- Spotify-Web-API-Wiedergabesteuerung braucht nach Kenntnisstand **Premium**.
- Spotify hat die API für Entwickler-Apps mehrfach eingeschränkt; welche Playlist-Endpunkte aktuell erlaubt sind, ist unklar. Code probiert `/tracks`, dann `/items`.
- Chrome/Edge-Cookies können an Verschlüsselung/gesperrter Datei scheitern; Firefox gilt als zuverlässiger (Kenntnisstand, nicht geprüft).
- Ob die Cookie-Testprüfung („LM“) bei jedem Konto funktioniert, ist ungetestet.
- winget-Paketnamen `yt-dlp.yt-dlp` und `Gyan.FFmpeg` aus dem Gedächtnis, nicht verifiziert.
- Ob der Lautstärkeregler pro Box oder pro Raumfeld-Zone wirkt, ist unbekannt.
- Das Spotify-Token liegt unverschlüsselt in `%APPDATA%/RaumfeldRemote/spotify_token.json`.

## 7. GitHub-Stand
- Repo: **`prostore-projekte/raumfeld_remote`** (`berion1982/raumfeld_remote` ist hinfällig).
- Arbeitsbranch `claude/ecstatic-mayer-gfo8yn`; jeder Schritt → PR nach `main`, Sascha merged selbst.
  Sascha merged `main` gelegentlich per PR zurück in den Branch → vor dem Push `git fetch` + `git merge` (kein Force-Push).
- Stand 20.11.2026: PRs #1–#14 gemergt, `main` = **0.9.2**; 0.10.0 (Ports, Firewall-Programmregel, Suchdiagnose) und 0.11.0 (Tidal, Konten) in PR #16.
- Workflow `.github/workflows/windows-build.yml`, zwei Jobs:
  - `build`: Desktop-EXE + Starttest von `start.bat` (Artifact „RaumfeldRemote-windows“)
  - `dienst-installer`: Dienst-EXE, Inno-Setup-Installer, **Installation/Prüfung/Deinstallation auf dem Runner**,
    auf `main` zusätzlich **Release `vX.Y.Z`** mit `RaumfeldRemote-Setup-X.Y.Z.exe` (Artifact „RaumfeldRemote-Setup“)

## 7a. Architektur ab 0.8.0 (Büro, mehrere Benutzer)
- Sascha (Nutzer, **duzen**): Desktop-Variante war „eher Single-User“ (start.bat, Einstellungen nicht sauber für alle).
  Ziel: **Web-Oberfläche mit Passwort** auf dem Terminalserver (**Windows Server 2025**), mehrere Nutzer im Büro,
  **Ruhezeiten** („ab 21:00 keine Musik“), richtiger **Installer für alle**, **Spotify** auch im Web.
- Umsetzung: zentraler Dienst `zentrale.py` + Flask `web.py` + `dienst.py` (waitress), Windows-Dienst per **WinSW v2.12.0**,
  Installer **Inno Setup** (`installer/raumfeld_remote.iss`). Daten in `C:\ProgramData\RaumfeldRemote`
  (`dienst.json`, `cookies.txt`, `spotify_token.json`, `stream.log`, `logs\`; icacls: nur SYSTEM/Admins).
- Spotify (0.9.0): ein gemeinsames Konto; Anmeldung per eingefügter Rückruf-Adresse `http://127.0.0.1:8888/callback?code=…`
  (Dienst hat keinen Browser, Spotify verlangt HTTPS oder Loopback als Redirect). Wiedergabe über YouTube-Suche auf
  Raumfeld-Boxen oder per Spotify Connect; Ruhezeit pausiert Connect.
- Lokal getestet: API mit Flask-Testclient (Login, Sperre, Ruhezeit, Einstellungen, Spotify mit simulierten Antworten),
  Ablauf mit simuliertem UPnP-Renderer, Oberfläche per Playwright. Installer/Dienst nur im CI auf Windows.
- **Nicht** getestet: echter Windows Server 2025, echte Boxen über den Dienst, echtes Spotify-Konto.
- Entscheidungen: ein Passwort für alle (keine Rollen); Ersteinrichtung nur von localhost; YouTube-Anmeldung im Dienst nur
  per `cookies.txt`-Upload. Ab 0.10.0: Ports einstellbar (Standard Web 8766, Stream 8765), Firewall als
  Programmregel „Raumfeld Remote Dienst“; Neustart per `os._exit(1)` → WinSW `onfailure restart` (im CI getestet).
- Desktop-Programm (`gui.py`, `start.bat`, `installieren.bat`) bleibt für Einzelplätze erhalten.

### Tidal (ab 0.11.0)
- Sascha wollte ausdrücklich **echten Tidal-Ton** (Weg 2), nicht YouTube-Ersatz; die Raumfeld-App kann Tidal heute noch.
  Tidal-Webseite/Firefox-Add-on wurden verworfen: Browser spielt nur lokal, Ton ist DRM-geschützt.
- `tidal.py`: `tidalapi` (inoffiziell), Anmeldung per Geräte-Code, Zugang in `tidal_sitzung.json` (wird bei Erneuerung
  neu gespeichert). Warteschlange: Quelle `tidal:<ID>`; der Stream-Server löst sie erst beim Abruf über
  `StreamServer.aufloeser` auf (Adressen sind kurz gültig) → ffmpeg → MP3. MPD-Streams als temporäre HLS-Liste.
- Getestet nur mit simulierter Sitzung (Flask-Testclient, Stream-Server mit lokaler Datei, Playwright). **Kein echtes Konto.**
- „Konten“: Passwort speichern ist bei YouTube/Spotify/Tidal nicht möglich (nur Anmeldung über deren Seite);
  stattdessen wird der Zugang dauerhaft gespeichert. Sascha: „passt so“.

### „Was läuft gerade“ (ab 0.14.0)
- Sascha (0.13.0 „läuft erst mal“): wünscht Auslesen, was aktuell läuft. Umsetzung: `upnp.hole_wiedergabe_info`
  (GetTransportInfo + GetPositionInfo, DIDL: title/artist|creator/album/albumArtURI, `*streamContent` für Radio =
  **Annahme**), `Zentrale._anzeige_waechter` alle 3 s parallel je Box, nur wenn `/api/zustand` < 30 s alt.
  Fremde Wiedergabe: Tasten → UPnP direkt; Ruhezeit stoppt auch fremde Wiedergabe.
- Getestet mit simulierter UPnP-Box (SOAP) + Playwright. **Ungeprüft:** welche Metadaten Raumfeld bei Tidal/Radio/
  App-Warteschlange wirklich liefert; ob Next/Previous bei App-Wiedergabe funktionieren; ob das Cover (URL der Box,
  192.168.20.x) im Browser der Büro-PCs erreichbar ist.

## 8. Offene Punkte / nächste Schritte
1. **0.11.1 installieren** und prüfen: Protokoll „… Gerät(e) aus der Einzelplatz-Variante übernommen“ und Boxen
   im Netz 192.168.20.0/24 sichtbar? Sonst Geräte-URL der Box (Desktop-Programm/Einstellungen) unter „Gerät per URL
   hinzufügen“ eintragen.
2a. **Tidal mit echtem Konto testen** (🔑 Konten → Tidal anmelden, Playlist abspielen). Bei Fehlern Protokoll ansehen
   (Zeilen „Tidal: …“). Unbekannt: ob die Geräte-Anmeldung von `tidalapi` 0.8.11 (eingebaute Client-ID) heute noch
   funktioniert und ob `get_url()` bei LOSSLESS eine Datei-URL liefert (sonst Weg über Stream-Manifest/HLS).
2. **Installer auf dem Terminalserver installieren** (Release-Datei, nicht den Quellcode/`installieren.bat`!),
   am Server `http://localhost:8766` → Passwort setzen; Netz `192.168.20.0/24`, Ruhezeiten einstellen; von einem Büro-PC
   `http://<server>:8766` öffnen und abspielen. Bei Problemen: Protokoll aus der Web-Oberfläche.
3. Spotify: App im Developer Dashboard (Redirect `http://127.0.0.1:8888/callback`), Client-ID + Anmeldung in der
   Web-Oberfläche, beide Wiedergabewege testen.
4. Danach entscheiden, ob Desktop-Variante/`start.bat` entfallen.
5. Ideen (nicht beauftragt): Benutzerrollen (Admin-Passwort für Einstellungen), Lautstärke-Obergrenze,
   Fortschrittsanzeige, Raumfeld-Zonen/Gruppen.

## 9. Arbeitsregeln des Nutzers (für Folgesitzungen)
- Antworten auf Deutsch; bei Unsicherem das klar sagen, nichts erfinden, Annahmen kennzeichnen.
- Quellcode: **detaillierte Kommentare**, gut lesbar.
- Bezeichner, Kommentare und Meldungen auf Deutsch; **Bezeichner und Kommentare ohne Umlaute** (ae, oe, ue, ss); sichtbare Oberflächentexte sowie README/CHANGELOG mit normalen Umlauten.
- **Kleine Edits statt ganzer Dateien**, bestehende Dateien nie komplett neu schreiben.
- Build-/Testausgaben filtern, keine kompletten Logs in den Kontext holen.
- Nur lesen, was die Aufgabe braucht (erst `grep -n`, dann gezielt Abschnitt lesen).
- Sanitizer-Builds nicht lokal bei jeder Änderung.

## 10. Verlauf
| Datum | Version | Schritt |
|---|---|---|
| 19.11.2026 | 0.1.0 | Erste Version gebaut (Zip) |
| 19.11.2026 | 0.1.1 | Ins Repo eingepflegt; `CLAUDE.md`, `HANDOVER.md` ergänzt; README/CHANGELOG aktualisiert; gepusht, PR erstellt |
| 19.11.2026 | 0.2.0 | Windows-Build per GitHub Actions (.exe + yt-dlp + ffmpeg als Zip), `.gitattributes`, `py`-Launcher |
| 19.11.2026 | 0.3.0 | Suche über VPN/Router (Unicast-SSDP, „Weitere Netze“), manuelle Geräte werden gespeichert |
| 19.11.2026 | 0.4.0 | Terminalserver: gemeinsame Einstellungen, automatische Port-Wahl, `start.bat` mit Prüfung/Nachinstallation |
| 19.11.2026 | 0.4.1 | `start.bat`: schnellere Downloads (curl.exe bzw. PowerShell ohne Fortschrittsanzeige) |
| 19.11.2026 | 0.5.0 | Diagnose „kein Ton“: Stream-Protokoll, Abruf-Prüfung nach 10 s, Fehler von yt-dlp/ffmpeg protokolliert |
| 19.11.2026 | 0.6.0 | Aufklappbares Live-Protokoll, UPnP-Befehle/Zustände protokolliert, `protokoll.py` |
| 19.11.2026 | 0.7.0 | Ursache „kein Ton“: yt-dlp ohne JavaScript-Laufzeit → deno ergänzt, yt-dlp-Update in `start.bat` |
| 20.11.2026 | 0.8.0 | Zentraler Dienst mit Web-Oberfläche, Passwort, Ruhezeiten, Installer (Inno Setup + WinSW) |
| 20.11.2026 | 0.9.0 | Spotify in der Web-Oberfläche; Releases mit Setup-EXE |
| 20.11.2026 | 0.9.1 | HANDOVER aufgeräumt (GitHub-Stand, Architektur, offene Punkte), README nach Varianten gegliedert |
| 20.11.2026 | 0.9.2 | README: Link zur Setup-EXE, Abschnitt „Setup-EXE selbst bauen“ |
| 20.11.2026 | 0.10.0 | Ports einstellbar (Standard 8766), Firewall-Programmregel, Suchdiagnose, Neusuche nach Netzänderung |
| 20.11.2026 | 0.11.0 | Tidal (inoffizielle API `tidalapi`, Geräte-Code, Ton direkt von Tidal), Bereich „Konten“ |
| 20.11.2026 | 0.11.1 | Gemerkte Geräte (Übernahme aus Einzelplatz-Variante, gefundene merken) statt nur SSDP |
| 20.11.2026 | 0.12.0 | Schnellerer Start: Playlist zweistufig, Titel vorab vorbereitet (yt-dlp -j / --load-info-json) |
| 20.11.2026 | 0.13.0 | Port-Suche für bekannte Boxen (Port wechselt nach Neustart der Box) |
| 20.11.2026 | 0.14.0 | „Was läuft gerade“ (GetPositionInfo/DIDL), Steuerung fremder Wiedergabe, Ruhezeit stoppt alles |
