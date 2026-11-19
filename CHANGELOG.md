# Änderungsprotokoll

Alle nennenswerten Änderungen. Versionierung nach [SemVer](https://semver.org/lang/de/):
MAJOR.MINOR.PATCH (Fehlerbehebung/Doku → PATCH, neue Funktion → MINOR).

## 0.4.1 – 19.11.2026
### Behoben
- `start.bat`: Downloads deutlich schneller – nutzt `curl.exe` (mit Fortschrittsbalken), sonst PowerShell ohne
  bremsende Fortschrittsanzeige; Entpacken von ffmpeg ebenfalls ohne Fortschrittsanzeige
- `start.bat`: korrekte Größenangabe für ffmpeg (ca. 200 MB statt 100 MB)

## 0.4.0 – 19.11.2026
### Hinzugefügt
- Terminalserver-Betrieb: Einstellungen „für alle Benutzer“ (`%PROGRAMDATA%\RaumfeldRemote`, anderer Ort per
  `RAUMFELD_REMOTE_GEMEINSAM`), Schaltfläche „Für alle Benutzer speichern“; geteilt werden Netze, Lautsprecher,
  Favoriten, Konten (inkl. Spotify-Anmeldung) und Stream-Optionen
- Benutzereinstellungen speichern nur noch selbst geänderte Werte (gemeinsame Werte werden nicht überdeckt)
- Stream-Server weicht bei belegtem Port automatisch auf den nächsten freien aus (mehrere Sitzungen gleichzeitig)
- `start.bat` prüft Python, `.venv`, Pakete, `yt-dlp` und `ffmpeg` und installiert Fehlendes nach
- Windows-Build testet zusätzlich `start.bat` von einem frischen Stand aus
- Startfehler werden nicht mehr verschluckt: Meldungsfenster und Protokoll `%APPDATA%\RaumfeldRemote\fehler.log`
### Geändert
- Firewall-Befehl gilt für den Port-Bereich 8765–8814 und die Profile „Privat“ und „Domäne“
- Spotify-Token: Schreibfehler (z. B. gemeinsames Token ohne Schreibrechte) führen nicht mehr zum Abbruch

## 0.3.0 – 19.11.2026
### Hinzugefügt
- Lautsprechersuche über Netzgrenzen (Router/VPN): Einstellung „Weitere Netze“ (z. B. `192.168.20.0/24`);
  dorthin wird die SSDP-Anfrage per Unicast an jede Adresse geschickt
- Manuell eingetragene Geräte-URLs werden gespeichert und bei jeder Suche erneut abgefragt,
  ebenso der zuletzt benutzte Lautsprecher
### Geändert
- Hinweistext bei „Nichts gefunden“ nennt die neue Einstellung

## 0.2.0 – 19.11.2026
### Hinzugefügt
- GitHub-Actions-Workflow „Windows-Build“: baut auf Windows `RaumfeldRemote.exe` (PyInstaller), legt `yt-dlp.exe` und
  `ffmpeg.exe` in den Ordner `tools` und stellt alles als Zip zum Download bereit; inklusive Import- und Starttest
- README: Schnellstart mit der fertigen .exe
### Geändert
- `installieren.bat` bevorzugt den Python-Launcher `py`
- `.gitattributes`: `.bat`-Dateien mit Windows-Zeilenenden (CRLF)

## 0.1.1 – 19.11.2026
### Hinzugefügt
- `CLAUDE.md`: Arbeitsanweisungen für Claude (token-sparendes Vorgehen, Code-Regeln, Pflichtschritte)
- `HANDOVER.md`: Übergabedokument mit Stand, Entscheidungen, Teststand und offenen Punkten
### Geändert
- Projekt erstmals ins Git-Repository eingepflegt
- README um Abschnitte „Projektstand“ und „Projektdokumente“ ergänzt
- Versionsnummer auf 0.1.1

## 0.1.0 – erste Version
- Windows-11-Oberfläche (customtkinter) mit Lautsprechersuche per SSDP über alle Netzwerkadapter
- Lautstärkeregler (UPnP RenderingControl) mit Auslesen des aktuellen Werts
- YouTube / YouTube Music: Links, Playlists, Suchbegriffe, lokale Dateien, Favoriten
- Konten: YouTube über Browser-Cookies oder cookies.txt, Spotify per OAuth (PKCE)
- Spotify: Wiedergabe über Spotify Connect oder ersatzweise über YouTube-Suche
- Transport: Zurück / Pause / Stop / Weiter
