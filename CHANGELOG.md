# Änderungsprotokoll

Alle nennenswerten Änderungen. Versionierung nach [SemVer](https://semver.org/lang/de/):
MAJOR.MINOR.PATCH (Fehlerbehebung/Doku → PATCH, neue Funktion → MINOR).

## 0.9.2 – 20.11.2026
### Geändert
- README: direkter Link zur Setup-EXE (Releases) und neuer Abschnitt „Setup-EXE selbst bauen“
  (GitHub Actions, Artifact `RaumfeldRemote-Setup`, lokale Schritte mit PyInstaller + Inno Setup)

## 0.9.1 – 20.11.2026
### Geändert
- README nach Büro- und Einzelplatz-Variante gegliedert, Projektstand aktualisiert
- HANDOVER: Kurzüberblick, GitHub-Stand, Architektur und offene Punkte auf aktuellen Stand gebracht

## 0.9.0 – 20.11.2026
### Hinzugefügt
- **Spotify in der Web-Oberfläche**: gemeinsames Konto (Client-ID + Anmeldung per eingefügter Rückruf-Adresse),
  Playlists auf einem Raumfeld-Lautsprecher (über YouTube-Suche, normale Warteschlange) oder per Spotify Connect
  inkl. Steuerung; Ruhezeiten sperren Spotify und pausieren Connect
- **Releases**: Bei jedem Stand auf `main` legt der Workflow ein Release `vX.Y.Z` mit der Setup-EXE an
### Geändert
- README: Hinweis, dass `installieren.bat`/`start.bat` nur die Einzelplatz-Variante sind

## 0.8.0 – 20.11.2026
### Hinzugefügt
- **Zentraler Dienst mit Web-Oberfläche** für den Mehrbenutzer-Betrieb im Büro (`raumfeld_remote/zentrale.py`,
  `web.py`, `dienst.py`, `web/*.html`):
  - Zugang mit gemeinsamem Passwort (PBKDF2), Ersteinrichtung nur direkt am Server, Sperre nach Fehlversuchen
  - eine gemeinsame Wiedergabe und Warteschlange pro Lautsprecher, für alle sichtbar; mehrere Lautsprecher parallel
  - **Ruhezeiten** (Wochentage + Uhrzeit, auch über Mitternacht): stoppt laufende Musik, sperrt Abspielen
  - zentrale Einstellungen (Netze, Geräte, Favoriten, Bitrate, YouTube-`cookies.txt`) für alle
  - Protokoll in der Oberfläche; tägliches automatisches `yt-dlp`-Update
- **Installer** (Inno Setup, `installer/`): Programm für alle Benutzer, Windows-Dienst (WinSW), Firewall-Regeln
  8080/8765, abgesicherter Datenordner, Startmenü-Eintrag; lautlose Installation möglich
- GitHub-Workflow baut `RaumfeldRemote-Setup-x.y.z.exe` und testet Installation, Dienst, Web-Oberfläche und
  Deinstallation auf einem Windows-Runner
### Geändert
- `Wiedergabe` (player.py): Stream-Präfix pro Wiedergabe, damit mehrere Lautsprecher sich den Stream-Server teilen;
  Warteschlange abfragbar, Sprung zu einem Titel
- Datenordner per Umgebungsvariable `RAUMFELD_REMOTE_DATEN` wählbar

## 0.7.0 – 19.11.2026
### Behoben
- Kein Ton bei YouTube: `yt-dlp` konnte die JavaScript-Aufgaben von YouTube nicht lösen („Signature/n challenge
  solving failed“, „Requested format is not available“). Jetzt wird die JavaScript-Laufzeit **deno** genutzt
  (`--js-runtimes deno:<Pfad>`)
### Hinzugefügt
- `start.bat` lädt `deno.exe` in den Ordner `tools` und aktualisiert als Administrator `tools\yt-dlp.exe` (`-U`)
- Windows-Paket aus GitHub Actions enthält `deno.exe`
- Reiter Einstellungen zeigt, ob deno gefunden wurde; Hinweis im Protokoll, wenn es fehlt

## 0.6.0 – 19.11.2026
### Hinzugefügt
- Aufklappbares Live-Protokoll unten im Fenster („▸ Protokoll anzeigen“), Hinweis „(Fehler!)“ bei zugeklapptem Protokoll
- Protokolliert werden zusätzlich: UPnP-Befehle an den Lautsprecher mit Ergebnis, Zustandswechsel des Lautsprechers,
  alle Statusmeldungen
### Geändert
- Fehlerausgaben von `yt-dlp`/`ffmpeg` werden zeilenweise mitgelesen (Kennzeichnung, welches Programm meldet)
- Neues Modul `protokoll.py` bündelt das Protokoll (Datei + Anzeige)

## 0.5.0 – 19.11.2026
### Hinzugefügt
- Stream-Protokoll `%APPDATA%\RaumfeldRemote\stream.log`: Abrufe der Lautsprecher, gesendete Datenmenge und
  Fehlermeldungen von `yt-dlp`/`ffmpeg` (wurden bisher verworfen); Schaltfläche „Stream-Protokoll öffnen“
- Meldung in der Statuszeile, wenn der Lautsprecher den Stream 10 Sekunden nach dem Start nicht abgerufen hat
- README: Abschnitt zur Fehlersuche „Anzeige läuft, aber nichts zu hören“
- `start.bat` legt die Firewall-Regel „Raumfeld Remote“ (TCP 8765–8814, Privat/Domäne) an, wenn sie fehlt
  und `start.bat` als Administrator läuft

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
