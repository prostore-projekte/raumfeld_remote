# Raumfeld Remote

Raumfeld-Lautsprecher (z. B. Teufel Stereo Cubes) steuern – ohne Raumfeld-App.
Für das Büro gibt es einen **zentralen Dienst mit Web-Oberfläche** (Windows Server, alle bedienen per Browser);
daneben weiterhin das Desktop-Programm für Einzelplätze.
Basiert auf dem Linux-Skript `raumcast.py`: Der PC startet einen kleinen Stream-Server, `yt-dlp` holt das
Audio von YouTube, `ffmpeg` wandelt es live in MP3 um, und der Lautsprecher spielt den Stream per UPnP ab.

**Version:** 0.9.1 · Änderungen siehe [CHANGELOG.md](CHANGELOG.md)

## Büro-Installation: zentraler Dienst mit Web-Oberfläche (empfohlen)
Ein Dienst auf dem Server (z. B. Terminalserver, Windows Server 2025) übernimmt Suche, Wiedergabe, Warteschlange,
Ruhezeiten und alle Einstellungen. Alle Kolleginnen und Kollegen bedienen ihn im Browser:
**`http://<servername>:8766`** – nichts pro Benutzer installieren, geht auch vom Handy.
(8766 ist der Standard-Port; änderbar im Installer und unter **⚙ Einstellungen → Ports**.)

**Installation (einmalig, als Administrator):**
1. `RaumfeldRemote-Setup-x.y.z.exe` herunterladen – direkt hier:
   **<https://github.com/prostore-projekte/raumfeld_remote/releases/latest>** → unter **Assets** die Setup-EXE.
   (Auf der Repository-Startseite steht derselbe Link rechts unter **Releases**.) Bauen musst du nichts – die
   Setup-EXE entsteht automatisch bei jedem Stand auf `main`, siehe „Setup-EXE selbst bauen“ weiter unten.
   Wichtig: **nicht** den Quellcode-Download mit `installieren.bat`/`start.bat` verwenden – das ist die alte
   Einzelplatz-Variante und richtet keinen Dienst ein.
2. Installer ausführen. Er richtet ein:
   - Programm in `C:\Program Files\RaumfeldRemote` inkl. `yt-dlp`, `ffmpeg`, `deno`
   - Windows-Dienst **„Raumfeld Remote“** (startet automatisch mit Windows, Neustart bei Absturz)
   - Firewall-Regel **„Raumfeld Remote Dienst“** für das Programm (Profile Domäne/Privat) – gilt für Web-Oberfläche,
     Stream und die Antworten der Lautsprecher bei der Suche, auch nach einer Portänderung
   - Eine Seite im Assistenten fragt den **Port der Web-Oberfläche** ab (Standard 8766)
   - Datenordner `C:\ProgramData\RaumfeldRemote` (nur SYSTEM und Administratoren haben Zugriff)
   - Startmenü-Eintrag „Raumfeld Remote“ für alle Benutzer
3. Am Ende öffnet sich `http://localhost:8766` (bzw. der gewählte Port) – dort das **Zugangspasswort** festlegen. Das geht aus Sicherheitsgründen
   nur direkt am Server.
4. In der Web-Oberfläche unter **⚙ Einstellungen**: weitere Netze (z. B. `192.168.20.0/24`), Ruhezeiten;
   unter **🔑 Konten**: YouTube, Spotify, Tidal anmelden (einmalig, bleibt gespeichert).

Lautlos installieren (z. B. Softwareverteilung): `RaumfeldRemote-Setup-x.y.z.exe /VERYSILENT /SUPPRESSMSGBOXES`
(anderer Port: zusätzlich `/WEBPORT=9000`)

**Port ändern:** **⚙ Einstellungen → Ports** → speichern → **Dienst jetzt neu starten**. Nach ca. 15 Sekunden springt
die Seite auf den neuen Port. Die Startmenü-Verknüpfung passt sich an.

**Lautsprecher im anderen Netz werden nicht gefunden?** Unter **⚙ Einstellungen → Netzwerk** das Netz eintragen
(z. B. `192.168.20.0/24`) und speichern – die Suche startet dann sofort. Im Protokoll steht danach, wie viele Adressen
angefragt wurden und welche geantwortet haben. Kommt keine Antwort: das Gerät unter „Gerät per URL hinzufügen“ fest eintragen.
Der Dienst übernimmt beim ersten Start die Geräte, die sich die Einzelplatz-Variante gemerkt hat (zuletzt benutzte
und fest eingetragene Lautsprecher aller Benutzer), und merkt sich jedes gefundene Gerät. Diese Adressen fragt er bei
jeder Suche direkt ab – das klappt auch dann, wenn die Netzsuche über VPN/Router keine Antwort bekommt.

### Setup-EXE selbst bauen
Normalerweise nicht nötig. Die Setup-EXE wird von GitHub Actions (Workflow **Windows-Build**, Job `dienst-installer`,
Datei `.github/workflows/windows-build.yml`) auf einem Windows-Rechner gebaut, dort probehalber installiert, geprüft
und wieder deinstalliert. Wo du sie danach findest:
- **Stand auf `main`** → Release `vX.Y.Z` unter **Releases** (siehe oben).
- **Jeder andere Lauf** (z. B. ein Pull Request) → Reiter **Actions** → Lauf anklicken → unten bei **Artifacts**
  die Datei **RaumfeldRemote-Setup** herunterladen (Zip mit der Setup-EXE, Anmeldung bei GitHub nötig).
- **Neu bauen ohne Code-Änderung**: **Actions** → **Windows-Build** → **Run workflow**.

Lokal unter Windows bauen (dieselben Schritte wie im Workflow; lokal so noch nicht ausprobiert):
1. Python 3.12 und [Inno Setup 6](https://jrsoftware.org/isinfo.php) installieren.
2. Im Projektordner: `pip install -r requirements-dienst.txt pyinstaller`
3. Dienst bauen:
   `pyinstaller --noconfirm --onedir --name RaumfeldRemoteDienst --add-data "raumfeld_remote/web;raumfeld_remote/web" --hidden-import tidalapi --collect-submodules tidalapi dienst_start.py`
4. Ordner `paket_dienst` anlegen und füllen:
   - Inhalt von `dist\RaumfeldRemoteDienst\` hineinkopieren, dazu `installer\RaumfeldRemote-Dienst.xml`, `README.md`, `CHANGELOG.md`
   - [WinSW-x64.exe v2.12.0](https://github.com/winsw/winsw/releases/tag/v2.12.0) als `paket_dienst\RaumfeldRemote-Dienst.exe` speichern
   - In `paket_dienst\tools\`: `yt-dlp.exe`, `ffmpeg.exe`, `ffprobe.exe`, `deno.exe`
5. Installer erzeugen (Version wie in `raumfeld_remote/__init__.py`):
   `"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" /DAppVersion=0.11.1 installer\raumfeld_remote.iss`
6. Ergebnis: `dist_installer\RaumfeldRemote-Setup-0.11.1.exe`

**Funktionen der Web-Oberfläche:**
- Anmeldung mit einem gemeinsamen Passwort (30 Tage angemeldet bleiben; Sperre nach 5 Fehlversuchen für 10 Minuten)
- Lautsprecher wählen, Lautstärke, Abspielen (Link, Playlist, Suchbegriff), ⏮ ⏯ ⏹ ⏭, Favoriten
- **Alle sehen dasselbe**: pro Lautsprecher genau eine Wiedergabe und Warteschlange (Klick auf einen Titel springt dorthin);
  mehrere Lautsprecher können gleichzeitig Verschiedenes spielen
- **Ruhezeiten**: z. B. Mo–Fr 21:00–07:00 – laufende Musik wird automatisch gestoppt, Abspielen ist gesperrt
- Einstellungen gelten für alle; Protokoll zum Aufklappen
- `yt-dlp` wird beim Start des Dienstes und danach täglich automatisch aktualisiert

**Daten und Protokolle:** `C:\ProgramData\RaumfeldRemote` – `dienst.json` (Einstellungen, Passwort-Hash),
`cookies.txt` (YouTube-Anmeldung), `stream.log` (Protokoll), `logs\` (Ausgabe des Dienstes).
Beim Deinstallieren bleibt dieser Ordner erhalten.

**Passwort vergessen?** Als Administrator in `dienst.json` den Wert `passwort_hash` leeren (`""`), Dienst neu starten
(`services.msc` → „Raumfeld Remote“) und am Server `http://localhost:8766` (bzw. deinen Port) öffnen.

**Spotify in der Web-Oberfläche** (ein gemeinsames Konto für alle):
1. Auf [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) eine App anlegen, als Redirect-URI
   `http://127.0.0.1:8888/callback` eintragen, die **Client-ID** kopieren.
2. Web-Oberfläche → 🔑 Konten → **Spotify**: Client-ID speichern, **„Bei Spotify anmelden“**.
3. Nach der Anmeldung zeigt der Browser „Seite nicht erreichbar“ (`127.0.0.1:8888`) – das ist richtig. Die komplette
   Adresse aus der Adresszeile kopieren, einfügen, **„Anmeldung abschließen“**.
4. Karte **Spotify**: Playlist wählen und abspielen –
   - **auf dem Raumfeld-Lautsprecher**: Titelnamen kommen von Spotify, das Audio über die YouTube-Suche
     (Spotify-Audio selbst ist kopiergeschützt); landet in der normalen Warteschlange
   - **Spotify Connect**: Spotify spielt selbst auf einem Spotify-Gerät (nach Kenntnisstand Premium nötig)
- Ruhezeiten gelten auch für Spotify (Connect wird pausiert).
- Das Token liegt in `C:\ProgramData\RaumfeldRemote\spotify_token.json` (nur Admins/SYSTEM).

**Tidal in der Web-Oberfläche** (ein gemeinsames Konto für alle, Tidal-Abo nötig):
1. 🔑 Konten → **Tidal** → **„Bei Tidal anmelden“**. Es öffnet sich `link.tidal.com` mit einem Code (geht auch am Handy):
   bei Tidal anmelden und bestätigen. Die Web-Oberfläche merkt die Anmeldung von selbst.
2. Karte **Tidal**: Playlist wählen (inkl. „Meine Titel“) **oder** Interpret, Titel bzw. Tidal-Link eingeben
   (Playlist, Album, Titel, Interpret) → **▶ Abspielen**. Der Ton kommt **direkt von Tidal** (nicht über YouTube)
   und landet in der normalen Warteschlange des gewählten Lautsprechers.
3. Qualität der Quelle: verlustfrei (FLAC) oder AAC 320 kbit/s. An die Boxen geht wie immer MP3 (Bitrate siehe Einstellungen).
- **Wichtig:** Genutzt wird die **inoffizielle** Tidal-Schnittstelle (Bibliothek `tidalapi`). Sie kann sich jederzeit
  ändern, und die Nutzung verstößt vermutlich gegen Tidals Nutzungsbedingungen. Mit einem echten Konto noch **nicht getestet**.
- Ruhezeiten gelten auch für Tidal. Der Zugang liegt in `C:\ProgramData\RaumfeldRemote\tidal_sitzung.json` (nur Admins/SYSTEM).
  Ein Passwort wird nicht gespeichert – Tidal lässt die Anmeldung nur über die eigene Seite zu.

## Projektstand
- **Desktop-Programm:** unter Windows mit echten Raumfeld-Boxen über VPN getestet – Suche, Lautstärke und Wiedergabe
  laufen (seit 0.7.0 mit `deno` für YouTube).
- **Zentraler Dienst / Web-Oberfläche:** Installer, Dienst und Web-Oberfläche werden bei jedem Build automatisch auf
  einem Windows-Rechner installiert und geprüft. Auf Windows Server 2025 mit echten Boxen und mit einem echten
  Spotify-Konto **noch nicht getestet**.
- Details und offene Punkte: [HANDOVER.md](HANDOVER.md).

---

# Einzelplatz-Variante (Desktop-Programm)
Für einen einzelnen PC. Fürs Büro mit mehreren Benutzern bitte die **Büro-Installation** oben verwenden.

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

## Installation mit Python
`start.bat` ausführen – mehr ist nicht nötig. Beim Start wird geprüft und bei Bedarf nachinstalliert:
1. **Python 3.10+** (fehlt es, wird `winget install Python.Python.3.12` für alle Benutzer versucht;
   ohne winget bitte von python.org installieren, Haken bei „Add python.exe to PATH“)
2. virtuelle Umgebung `.venv` und die Pakete aus `requirements.txt`
3. `yt-dlp.exe` und `ffmpeg.exe` – werden in den Ordner `tools` heruntergeladen, falls sie weder dort noch im PATH liegen
4. `deno.exe` – JavaScript-Laufzeit, die `yt-dlp` für YouTube braucht (ohne sie: „Requested format is not available“, kein Ton)
5. Firewall-Regel „Raumfeld Remote“ (TCP 8765–8814) – wird angelegt, wenn `start.bat` als Administrator läuft
6. Als Administrator aktualisiert `start.bat` außerdem `tools\yt-dlp.exe` (YouTube ändert sich häufig)
   (ffmpeg ca. 200 MB, je nach Leitung einige Minuten)

Ist alles vorhanden, startet das Programm sofort ohne Konsolenfenster. Bei Fehlern bleibt das Fenster mit einer Meldung offen.
Stürzt das Programm beim Start ab, erscheint eine Meldung; der Fehler steht in `%APPDATA%\RaumfeldRemote\fehler.log`.
(`installieren.bat` gibt es weiterhin, wird aber nicht mehr benötigt.)

## Desktop-Programm auf einem Terminalserver (veraltet – besser den zentralen Dienst nutzen)
1. Programmordner an einen gemeinsamen Ort legen, z. B. `C:\Programme\RaumfeldRemote`.
2. Python **für alle Benutzer** installieren („Install for all users“).
3. `start.bat` **einmal als Administrator** ausführen – installiert alles in den Programmordner und legt die
   Firewall-Regel an (ohne sie spielt die Anzeige, aber es ist nichts zu hören).
   Danach starten alle Benutzer über `start.bat` (z. B. per Verknüpfung) ohne Installation.
4. Als Administrator Einstellungen vornehmen (weitere Netze, Lautsprecher, Konten) und im Reiter
   **Einstellungen** auf **„Für alle Benutzer speichern“** klicken.

Einstellungen:
- Gemeinsam: `%PROGRAMDATA%\RaumfeldRemote\einstellungen.json` (anderer Ort per Umgebungsvariable
  `RAUMFELD_REMOTE_GEMEINSAM`, z. B. ein Netzlaufwerk). Normale Benutzer können sie lesen, aber nicht ändern.
- Pro Benutzer: `%APPDATA%\RaumfeldRemote\einstellungen.json` – enthält nur, was ein Benutzer selbst geändert hat;
  diese Werte haben Vorrang vor den gemeinsamen.
- Geteilt werden: Port, Bitrate, weitere Netze, manuell eingetragene Lautsprecher, Favoriten, YouTube-Anmeldung
  (Browser bzw. `cookies.txt`), Spotify-Client-ID und – falls angemeldet – die Spotify-Anmeldung.
- Geteilte Spotify-Anmeldung: alle Benutzer steuern dasselbe Konto; das Token liegt unverschlüsselt und
  für alle lesbar in `%PROGRAMDATA%\RaumfeldRemote\spotify_token.json`.
- YouTube „aus Browser“ liest die Cookies **des jeweiligen Benutzers**. Für ein gemeinsames Konto eine
  `cookies.txt` an einem für alle lesbaren Ort verwenden.
- Jede Sitzung braucht einen eigenen Stream-Port: Ist der eingestellte Port belegt, nimmt das Programm
  automatisch den nächsten freien (bis zu 50 Ports, Standard 8765–8814).
- Die Spotify-Anmeldung nutzt kurzzeitig Port 8888 – zwei Benutzer können sich nicht gleichzeitig anmelden.

## Lautsprecher in einem anderen Netz (Router/VPN)
Die automatische Suche nutzt Multicast; das wird von Routern und VPN-Verbindungen normalerweise nicht weitergeleitet.
Stehen die Lautsprecher in einem anderen Netz (z. B. PC in `192.168.10.0/24`, Lautsprecher in `192.168.20.0/24`):

**Web-Oberfläche:** ⚙ Einstellungen → **Netzwerk** → „Weitere Netze“ `192.168.20.0/24` → speichern → 🔍 Suchen.

**Desktop-Programm:**
1. Reiter **Einstellungen** → **Weitere Netze**: `192.168.20.0/24` eintragen (mehrere mit Komma) → **Speichern**.
2. **Im Netzwerk suchen**. Das Programm fragt dann jede Adresse dieses Netzes einzeln an.
3. Antworten die Lautsprecher darauf nicht (hängt von der Firmware ab), die Geräte-URL manuell eintragen.
   Manuell eingetragene Geräte werden gespeichert und bei jeder Suche wieder abgefragt.

Wichtig: Der Lautsprecher muss den PC umgekehrt auch erreichen (Stream-Port, Standard 8765) –
Routing über das VPN und die Windows-Firewall müssen das zulassen.

## Fehlersuche: Anzeige läuft, aber nichts zu hören
- Ruft der Lautsprecher den Stream 10 Sekunden nach dem Start nicht ab, meldet das Programm das in der Statuszeile
  (mit der Stream-URL). Dann erreicht der Lautsprecher den PC nicht: Firewall-Regel (siehe unten), Routing über das VPN,
  Netzwerkprofil „Öffentlich“.
- **„▸ Protokoll anzeigen“** unten im Fenster klappt ein Live-Protokoll auf: Befehle an den Lautsprecher (→/←),
  dessen Zustand (PLAYING, STOPPED …), Stream-Abrufe, Statusmeldungen und Fehler von `yt-dlp`/`ffmpeg`.
  Bei einem Fehler zeigt die zugeklappte Schaltfläche „(Fehler!)“.
- **Einstellungen → „Stream-Protokoll öffnen“** (`%APPDATA%\RaumfeldRemote\stream.log`) zeigt jeden Abruf des
  Lautsprechers, wie viel gesendet wurde, und die Fehlermeldungen von `yt-dlp` und `ffmpeg`.
  - Kein `GET`-Eintrag → Lautsprecher erreicht den PC nicht.
  - `GET` vorhanden, aber „0 KB gesendet“ → `yt-dlp`/`ffmpeg` scheitern; die Fehlermeldung steht darüber.
    „Signature/n challenge solving failed“ + „Requested format is not available“ → `deno.exe` fehlt oder `yt-dlp`
    ist veraltet: `start.bat` als Administrator ausführen.
  - Daten gesendet, trotzdem still → Lautstärke/Zone in Raumfeld prüfen; ggf. ein anderes Gerät aus der Liste wählen.

## Windows-Firewall
Der Lautsprecher muss den Stream-Server auf dem PC erreichen (Standard: TCP-Port 8765, auf Terminalservern
bis 8814). Beim ersten Start fragt Windows evtl. nach – zulassen. Sonst als Administrator:
```
netsh advfirewall firewall add rule name="Raumfeld Remote" dir=in action=allow protocol=TCP localport=8765-8814 profile=private,domain
```
Das Netzwerk muss als „Privat“ oder „Domäne“ eingestuft sein (nicht „Öffentlich“).

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
  einstellungen.py  JSON-Einstellungen: gemeinsam (%PROGRAMDATA%) und pro Benutzer (%APPDATA%)
  protokoll.py      Protokoll (Datei + Live-Anzeige)
  zentrale.py       Zentraler Dienst: Lautsprecher, eine Wiedergabe pro Box, Ruhezeiten, Einstellungen
  web.py            Web-Oberfläche/API (Flask), Passwort, Anmeldung
  dienst.py         Startpunkt des Dienstes (waitress)
  web/              HTML-Seiten (Hauptseite, Anmeldung, Ersteinrichtung)
installer/          Inno-Setup-Skript und WinSW-Konfiguration für den Windows-Dienst
dienst_start.py     Startdatei für RaumfeldRemoteDienst.exe
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
