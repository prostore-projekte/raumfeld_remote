# Handover – Raumfeld Remote

Stand: 20.11.2026 · Version 0.9.0 · Repo: <https://github.com/prostore-projekte/raumfeld_remote> (Branch `claude/ecstatic-mayer-gfo8yn`)

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
- Stand 20.11.2026: PRs #1–#12 gemergt, `main` = **0.9.0**.
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
  per `cookies.txt`-Upload; Ports fest 8080/8765 (Firewall-Regeln im Installer).
- Desktop-Programm (`gui.py`, `start.bat`, `installieren.bat`) bleibt für Einzelplätze erhalten.

## 8. Offene Punkte / nächste Schritte
1. **Release v0.9.0 prüfen** (Repo-Seite → Releases) – erstes automatisch angelegtes Release.
2. **Installer auf dem Terminalserver installieren** (Release-Datei, nicht den Quellcode/`installieren.bat`!),
   am Server `http://localhost:8080` → Passwort setzen; Netz `192.168.20.0/24`, Ruhezeiten einstellen; von einem Büro-PC
   `http://<server>:8080` öffnen und abspielen. Bei Problemen: Protokoll aus der Web-Oberfläche.
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
| 20.11.2026 | 0.9.0 | HANDOVER aufgeräumt (GitHub-Stand, Architektur, offene Punkte), README nach Varianten gegliedert |
