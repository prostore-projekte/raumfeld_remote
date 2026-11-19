# Änderungsprotokoll

Alle nennenswerten Änderungen. Versionierung nach [SemVer](https://semver.org/lang/de/):
MAJOR.MINOR.PATCH (Fehlerbehebung/Doku → PATCH, neue Funktion → MINOR).

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
