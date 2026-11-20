# CLAUDE.md – Arbeitsanweisungen für Claude

Raumfeld Remote: Windows-11-GUI (Python, customtkinter) zum Steuern von Teufel-Raumfeld-Lautsprechern
per UPnP; Audio über `yt-dlp → ffmpeg → MP3`-Stream. Details/Historie: `HANDOVER.md`.

## Sitzungsstart (token-sparend)
1. Nur `HANDOVER.md` lesen (Abschnitte „Teststand“, „Offene Punkte“). Nicht den ganzen Code einlesen.
2. Code erst bei Bedarf: `grep -n` nach Bezeichner → gezielt `Read` mit `offset`/`limit`.
3. `gui.py` ist groß (~800 Zeilen) – nie komplett lesen.

## Modulkarte (statt Dateien zu öffnen)
| Datei | Zuständig für |
|---|---|
| `raumfeld_remote/upnp.py` | SSDP-Suche, Geräte-XML, SOAP, Lautstärke, DIDL |
| `raumfeld_remote/quellen.py` | yt-dlp/ffmpeg finden, Cookies, Links → `Titel`-Liste |
| `raumfeld_remote/stream_server.py` | HTTP-Server yt-dlp → ffmpeg → MP3 |
| `raumfeld_remote/player.py` | `Wiedergabe`: Warteschlange, Transport |
| `raumfeld_remote/spotify.py` | OAuth PKCE, Web-API |
| `raumfeld_remote/tidal.py` | Tidal über `tidalapi` (inoffiziell): Geräte-Code-Login, Playlists/Suche, Stream-Adresse |
| `raumfeld_remote/einstellungen.py` | JSON in `%APPDATA%/RaumfeldRemote/` |
| `raumfeld_remote/gui.py` | Oberfläche; GUI-Updates nur über Queue (`_ui` / `_ui_pumpe`) |
| `raumfeld_remote/protokoll.py` | `protokoll()` → `stream.log` + Live-Protokoll in der GUI (`abonnieren`) |
| `raumfeld_remote/zentrale.py` | **Dienst**: Lautsprecher, eine `Wiedergabe` pro Box, Ruhezeiten, `dienst.json` |
| `raumfeld_remote/web.py` + `web/*.html` | **Dienst**: Flask-API, Passwort/Login, Web-Oberfläche (Vanilla JS) |
| `raumfeld_remote/dienst.py` | **Dienst**: Startpunkt (waitress), setzt Datenordner vor den Imports |
| `installer/` | Inno-Setup-Skript, WinSW-XML (Windows-Dienst) |
| `raumfeld_remote/__init__.py` | `__version__` |

## Code-Regeln
- Kleine Edits, bestehende Dateien nie komplett neu schreiben.
- Detaillierte Kommentare, lesbarer Code.
- Bezeichner/Kommentare deutsch **ohne Umlaute** (ae, oe, ue, ss); Oberflächentexte, README, CHANGELOG mit Umlauten.
- Netzwerk/Prozesse nur in Hintergrund-Threads, nie im Tk-Hauptthread.
- Windows-Ziel beachten: `CREATE_NO_WINDOW`, Pfade über `pathlib`/`os.path`.

## Prüfen (Ausgaben gefiltert)
```bash
python3 -m py_compile raumfeld_remote/*.py && echo OK
python3 -m pyflakes raumfeld_remote 2>&1 | head -20
```
- Keine kompletten Logs in den Kontext; `| tail -20` oder `| grep -iE "error|fail"`.
- Desktop-GUI (tkinter) lässt sich in der Sandbox nicht testen. Der **Dienst** schon: Flask-Testclient,
  `python -m raumfeld_remote.dienst --port 8093` mit `RAUMFELD_REMOTE_DATEN=<tmp>` + Playwright-Screenshot.
- Python-Hilfsskripte für Edits: Suchtexte vorher auf Eindeutigkeit prüfen (Abbruch mittendrin = halber Stand).

## Pflicht nach jedem Arbeitsschritt
1. `HANDOVER.md` aktualisieren (Stand/Datum, Version, Teststand, offene Punkte) – nur betroffene Abschnitte editieren.
2. `CHANGELOG.md` ergänzen; Version nach SemVer:
   - Fehlerbehebung/Doku → PATCH (0.1.x), neue Funktion → MINOR (0.x.0).
   - `__version__` in `raumfeld_remote/__init__.py` gleich halten.
3. `README.md` anpassen, wenn sich Bedienung/Installation ändert.
4. Commit mit aussagekräftiger deutscher Nachricht, pushen und **immer einen PR nach `main` erstellen**
   (bzw. bestehenden PR des Branches aktualisieren).

## Antwortstil
- Nutzer heißt **Sascha** – **duzen**.
- Deutsch, knapp. Unsicheres klar kennzeichnen, nichts erfinden („Dazu habe ich keine gesicherten Informationen“).
- Keine Wiederholung bereits geklärter Fakten aus `HANDOVER.md`.
