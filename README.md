# Raumfeld Remote

Raumfeld-Lautsprecher (z. B. Teufel Stereo Cubes) unter **Windows 11** steuern – ohne Raumfeld-App.
Basiert auf dem Linux-Skript `raumcast.py`: Der PC startet einen kleinen Stream-Server, `yt-dlp` holt das
Audio von YouTube, `ffmpeg` wandelt es live in MP3 um, und der Lautsprecher spielt den Stream per UPnP ab.

**Version:** 0.2.0 · Änderungen siehe [CHANGELOG.md](CHANGELOG.md)

## Projektstand
Frühe Version, **noch nicht unter Windows oder mit echter Hardware getestet** (Details in [HANDOVER.md](HANDOVER.md)).
Rückmeldungen aus der Statuszeile beim ersten Start helfen bei der Fehlersuche.

## Funktionen
- Lautsprecher im Netzwerk **suchen** (SSDP), Auswahl per Klick, manuelles Hinzufügen per URL
- **Lautstärke** per Regler
- **YouTube / YouTube Music**: Link, Playlist, Suchbegriff oder Datei, Zufallswiedergabe, Favoriten
- **Konten-Menü**: YouTube (Browser-Anmeldung) und Spotify (OAuth)
- Zurück / Pause / Stop / Weiter

## Schnellstart unter Windows (fertige .exe, ohne Python)
1. Auf GitHub im Repository den Reiter **Actions** öffnen → Workflow **Windows-Build** → letzten erfolgreichen Lauf (grüner Haken) anklicken.
2. Unten bei **Artifacts** die Datei **RaumfeldRemote-windows** herunterladen (Anmeldung bei GitHub nötig) und entpacken.
3. `RaumfeldRemote\RaumfeldRemote.exe` starten. `yt-dlp.exe` und `ffmpeg.exe` liegen bereits im Ordner `tools` daneben.
4. Beim ersten Start die Windows-Firewall für **private Netzwerke** zulassen (siehe unten).

Hinweis: Die .exe ist nicht signiert. Windows SmartScreen kann warnen → „Weitere Informationen“ → „Trotzdem ausführen“.
Artefakte werden von GitHub nach einiger Zeit gelöscht (standardmäßig 90 Tage); dann den Workflow über „Run workflow“ neu starten.

## Installation (mit Python, für Entwicklung)
1. **Python 3.10+** von python.org installieren (Haken bei „Add Python to PATH“).
2. `installieren.bat` ausführen (legt `.venv` an, installiert `customtkinter`).
3. `yt-dlp` und `ffmpeg` installieren:
   ```
   winget install yt-dlp.yt-dlp
   winget install Gyan.FFmpeg
   ```
   Alternativ die `.exe`-Dateien in den Ordner `tools` neben `start.pyw` legen.
   (Die winget-Paketnamen sind nach meinem Wissen korrekt, bitte bei Fehlern mit `winget search` prüfen.)
4. `start.bat` ausführen (oder `python -m raumfeld_remote`).

## Windows-Firewall
Der Lautsprecher muss den Stream-Server auf deinem PC erreichen (Standard: TCP-Port 8765).
Beim ersten Start fragt Windows evtl. nach – „Privates Netzwerk“ zulassen. Sonst als Administrator:
```
netsh advfirewall firewall add rule name="Raumfeld Remote" dir=in action=allow protocol=TCP localport=8765 profile=private
```
Das Netzwerk muss als „Privat“ eingestuft sein.

## YouTube-Konto verknüpfen
Reiter **Konten → YouTube**: Browser wählen, in dem du bei YouTube angemeldet bist, dann „Speichern & testen“.
- Nach meinem Kenntnisstand ist **Firefox** am zuverlässigsten. Bei Chrome/Edge kann das Auslesen der Cookies
  an deren Verschlüsselung oder an einer gesperrten Cookie-Datei scheitern (Browser dann schließen).
  Alternative: eine `cookies.txt` exportieren und im Feld darunter auswählen.
- Der Test liest die Playlist „Gefällt mir“. Dass diese Prüfung bei jedem Konto funktioniert, habe ich nicht getestet.
- Öffentliche Links gehen auch ohne Anmeldung.

## Spotify verknüpfen
Spotify-Audio ist DRM-geschützt und lässt sich **nicht** wie YouTube per `yt-dlp` holen. Darum gibt es zwei Wege:

| Weg | Funktionsweise | Voraussetzung |
|---|---|---|
| **Spotify Connect** | Spotify spielt selbst auf dem Lautsprecher, dieses Tool steuert per Web API | Spotify Premium; Lautsprecher muss als Connect-Gerät erscheinen |
| **via YT Music** | Titelnamen werden von Spotify gelesen, dann bei YouTube gesucht und abgespielt | kein Premium nötig; Treffer können abweichen (Live-Versionen, Cover) |

Einrichtung (einmalig):
1. Auf <https://developer.spotify.com/dashboard> eine App anlegen.
2. Als **Redirect URI** exakt `http://127.0.0.1:8888/callback` eintragen.
3. Die **Client-ID** im Reiter *Konten → Spotify* einfügen und „Bei Spotify anmelden“ klicken.

Unsicherheiten (nicht getestet):
- Ob dein Raumfeld-Modell/deine Firmware in der Geräteliste von Spotify erscheint, weiß ich nicht.
- Spotify hat die Web API für Entwickler-Apps mehrfach eingeschränkt. Welche Endpunkte für Playlists
  aktuell erlaubt sind, kann ich nicht sicher sagen. Das Tool probiert `/tracks` und danach `/items`;
  Fehlermeldungen von Spotify erscheinen in der Statuszeile.
- Das Spotify-Token liegt unverschlüsselt in `%APPDATA%\RaumfeldRemote\spotify_token.json`.

## Bekannte Grenzen
- Lautstärke: Ob der Regler pro Lautsprecher oder pro Raumfeld-Zone wirkt, hängt vom gewählten Gerät ab.
- Titelwechsel dauern 1–3 Sekunden (yt-dlp muss erst starten).
- Die Fortschrittsanzeige/Warteschlangenansicht fehlt in Version 0.1.0.
- Dieses Projekt wurde ohne Zugriff auf Windows, echte Raumfeld-Hardware oder ein Spotify-Konto geschrieben.
  Ungetestet ist alles außer Syntaxprüfung und dem MP3-Stream-Server (mit lokaler Datei).

## Optional: eigene .exe
`build_exe.bat` baut mit PyInstaller eine einzelne `RaumfeldRemote.exe` (ungetestet).

## Projektstruktur
```
raumfeld_remote/
  upnp.py           SSDP-Suche, SOAP-Steuerung, Lautstärke
  quellen.py        yt-dlp/ffmpeg finden, Links/Playlists in Titel auflösen
  stream_server.py  HTTP-Server: yt-dlp -> ffmpeg -> MP3
  player.py         Warteschlange, Weiter/Zurück/Pause/Stop
  spotify.py        OAuth (PKCE) und Web-API-Aufrufe
  einstellungen.py  JSON-Einstellungen in %APPDATA%
  gui.py            Oberfläche (customtkinter)
start.pyw / start.bat / installieren.bat / build_exe.bat
```

## Projektdokumente
| Datei | Zweck |
|---|---|
| [README.md](README.md) | Diese Anleitung |
| [CHANGELOG.md](CHANGELOG.md) | Änderungsprotokoll mit Versionsnummern |
| [HANDOVER.md](HANDOVER.md) | Übergabe: Stand, Entscheidungen, Teststand, offene Punkte |
| [CLAUDE.md](CLAUDE.md) | Arbeitsanweisungen für Claude Code |

## Rechtlicher Hinweis
Nutzung von YouTube-Inhalten über `yt-dlp` kann gegen die Nutzungsbedingungen von YouTube verstoßen.
Nutzung auf eigene Verantwortung, nur für private Zwecke.
