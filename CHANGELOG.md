# Änderungsprotokoll

Alle nennenswerten Änderungen. Versionierung nach [SemVer](https://semver.org/lang/de/):
MAJOR.MINOR.PATCH (Fehlerbehebung/Doku → PATCH, neue Funktion → MINOR).

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
