# Handover – Raumfeld Remote

Stand: 19.11.2026 · Version 0.2.0 · Repo: <https://github.com/prostore-projekte/raumfeld_remote> (Branch `claude/ecstatic-mayer-gfo8yn`)

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
- ✘ **GUI nie ausgeführt** (der Sandbox fehlte `tkinter`, Installation hing)
- ✘ Nichts auf Windows, mit echter Raumfeld-Hardware oder mit Spotify-Konto getestet
- ✘ `build_exe.bat` ungetestet
- Ab 0.2.0: Workflow `.github/workflows/windows-build.yml` baut die .exe auf `windows-latest` und prüft pyflakes,
  GUI-Import und einen 10-Sekunden-Starttest. Ergebnis siehe GitHub Actions (kein Test mit echter Hardware).

## 6. Unsicherheiten und Annahmen
- Ob Raumfeld-Boxen in der Spotify-Geräteliste (Connect) erscheinen, ist **unbekannt** (hängt von Modell/Firmware ab). Die automatische Zuordnung Box ↔ Connect-Gerät per Namensvergleich ist eine **Annahme**.
- Spotify-Web-API-Wiedergabesteuerung braucht nach Kenntnisstand **Premium**.
- Spotify hat die API für Entwickler-Apps mehrfach eingeschränkt; welche Playlist-Endpunkte aktuell erlaubt sind, ist unklar. Code probiert `/tracks`, dann `/items`.
- Chrome/Edge-Cookies können an Verschlüsselung/gesperrter Datei scheitern; Firefox gilt als zuverlässiger (Kenntnisstand, nicht geprüft).
- Ob die Cookie-Testprüfung („LM“) bei jedem Konto funktioniert, ist ungetestet.
- winget-Paketnamen `yt-dlp.yt-dlp` und `Gyan.FFmpeg` aus dem Gedächtnis, nicht verifiziert.
- Ob der Lautstärkeregler pro Box oder pro Raumfeld-Zone wirkt, ist unbekannt.
- Das Spotify-Token liegt unverschlüsselt in `%APPDATA%/RaumfeldRemote/spotify_token.json`.

## 7. GitHub-Stand
- Repo: **`prostore-projekte/raumfeld_remote`** (vom Nutzer bestätigt; `berion1982/raumfeld_remote` ist hinfällig).
- `main` enthält nur einen leeren Startcommit (nötig als PR-Ziel, Repo war leer).
- Projekt liegt auf Branch `claude/ecstatic-mayer-gfo8yn`, PR nach `main` erstellt (noch nicht gemergt).
- Regel: Nach jedem Schritt pushen und PR erstellen/aktualisieren.

## 8. Offene Punkte / nächste Schritte
1. PR nach `main` prüfen und mergen (siehe Abschnitt 7).
2. **Erster Start auf Windows 11** → Fehlermeldungen aus der Statuszeile zurückmelden.
3. Windows-Firewall-Regel für Port 8765 (privates Netz) setzen; Netzwerkprofil „Privat“ prüfen.
4. Prüfen, ob die Boxen per SSDP gefunden werden; sonst Geräte-URL manuell (Muster siehe Abschnitt 2).
5. Spotify-App im Developer Dashboard anlegen, Redirect-URI eintragen, Client-ID einfügen, beide Wiedergabewege testen.
6. Fehlende Funktionen (bewusst weggelassen): **Warteschlangenansicht**, **Fortschrittsanzeige**, Zonen-/Gruppenverwaltung von Raumfeld.
7. Fertige .exe aus GitHub Actions (Artifact „RaumfeldRemote-windows“) auf Windows 11 testen.

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
