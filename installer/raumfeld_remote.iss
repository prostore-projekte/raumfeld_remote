; ===========================================================================
; raumfeld_remote.iss - Inno-Setup-Skript fuer den zentralen Dienst
;
; Installiert fuer ALLE Benutzer (Administratorrechte noetig):
;   - Programm nach C:\Program Files\RaumfeldRemote (Dienst-EXE, yt-dlp, ffmpeg, deno)
;   - Windows-Dienst "Raumfeld Remote" (WinSW), startet automatisch mit Windows
;   - Firewall-Regeln: TCP 8080 (Web-Oberflaeche) und TCP 8765 (Stream an die Lautsprecher)
;   - Datenordner C:\ProgramData\RaumfeldRemote, nur fuer SYSTEM und Administratoren lesbar
;     (enthaelt Passwort-Hash und ggf. YouTube-Cookies)
;   - Startmenue-Verknuepfung zur Web-Oberflaeche fuer alle Benutzer
;
; Bauen:  iscc /DAppVersion=0.8.0 installer\raumfeld_remote.iss
; Erwartet die fertigen Dateien im Ordner ..\paket_dienst (siehe GitHub-Workflow).
; Lautlos installieren:  RaumfeldRemote-Setup-x.y.z.exe /VERYSILENT /SUPPRESSMSGBOXES
; ===========================================================================

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define WebPort "8080"
#define StreamPort "8765"
#define DienstExe "RaumfeldRemote-Dienst.exe"

[Setup]
AppId={{6C1E2B7A-3F4D-4E8B-9A51-2D7C0E4B9F13}
AppName=Raumfeld Remote
AppVersion={#AppVersion}
AppVerName=Raumfeld Remote {#AppVersion}
DefaultDirName={autopf}\RaumfeldRemote
DefaultGroupName=Raumfeld Remote
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist_installer
OutputBaseFilename=RaumfeldRemote-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
SetupLogging=yes
UninstallDisplayName=Raumfeld Remote

[Languages]
Name: "de"; MessagesFile: "compiler:Languages\German.isl"

[Files]
; Alles aus dem vorbereiteten Paketordner (Dienst-EXE + _internal, tools, WinSW)
Source: "..\paket_dienst\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Dirs]
Name: "{commonappdata}\RaumfeldRemote"

[INI]
; Internet-Verknuepfung zur Web-Oberflaeche (fuer das Startmenue)
Filename: "{app}\Raumfeld Remote.url"; Section: "InternetShortcut"; Key: "URL"; String: "http://localhost:{#WebPort}/"

[Icons]
Name: "{commonprograms}\Raumfeld Remote"; Filename: "{app}\Raumfeld Remote.url"

[Run]
; Datenordner absichern: nur SYSTEM (S-1-5-18) und Administratoren (S-1-5-32-544)
Filename: "{sys}\icacls.exe"; Parameters: """{commonappdata}\RaumfeldRemote"" /inheritance:r /grant:r *S-1-5-18:(OI)(CI)F *S-1-5-32-544:(OI)(CI)F"; Flags: runhidden waituntilterminated; StatusMsg: "Datenordner wird abgesichert …"
; Firewall-Regeln (vorher evtl. vorhandene gleichnamige entfernen, damit sie nicht doppelt sind)
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""Raumfeld Remote Web"""; Flags: runhidden waituntilterminated
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""Raumfeld Remote Web"" dir=in action=allow protocol=TCP localport={#WebPort} profile=domain,private"; Flags: runhidden waituntilterminated; StatusMsg: "Firewall-Regeln werden gesetzt …"
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""Raumfeld Remote Stream"""; Flags: runhidden waituntilterminated
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""Raumfeld Remote Stream"" dir=in action=allow protocol=TCP localport={#StreamPort} profile=domain,private"; Flags: runhidden waituntilterminated
; Dienst einrichten und starten
Filename: "{app}\{#DienstExe}"; Parameters: "install"; Flags: runhidden waituntilterminated; StatusMsg: "Dienst wird eingerichtet …"
Filename: "{app}\{#DienstExe}"; Parameters: "start"; Flags: runhidden waituntilterminated; StatusMsg: "Dienst wird gestartet …"
; Am Ende: Web-Oberflaeche oeffnen, um das Passwort festzulegen (nur bei sichtbarer Installation)
Filename: "http://localhost:{#WebPort}/"; Description: "Web-Oberfläche öffnen und Passwort festlegen"; Flags: postinstall shellexec nowait skipifsilent

[UninstallRun]
Filename: "{app}\{#DienstExe}"; Parameters: "stop"; Flags: runhidden waituntilterminated; RunOnceId: "DienstStop"
Filename: "{app}\{#DienstExe}"; Parameters: "uninstall"; Flags: runhidden waituntilterminated; RunOnceId: "DienstEntfernen"
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""Raumfeld Remote Web"""; Flags: runhidden waituntilterminated; RunOnceId: "FwWeb"
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""Raumfeld Remote Stream"""; Flags: runhidden waituntilterminated; RunOnceId: "FwStream"

[UninstallDelete]
; Vom Programm erzeugte Dateien im Programmordner (z. B. aktualisiertes yt-dlp, WinSW-Logs)
Type: filesandordirs; Name: "{app}\tools"
Type: files; Name: "{app}\*.log"
; Hinweis: C:\ProgramData\RaumfeldRemote (Einstellungen) bleibt bewusst erhalten.

[Code]
// Bei einem Update: laufenden Dienst vor dem Kopieren stoppen und abmelden,
// sonst sind die Dateien gesperrt. Wird danach im [Run]-Abschnitt neu eingerichtet.
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Dienst: String;
  Ergebnis: Integer;
begin
  Result := '';
  Dienst := ExpandConstant('{app}\{#DienstExe}');
  if FileExists(Dienst) then
  begin
    Exec(Dienst, 'stop', '', SW_HIDE, ewWaitUntilTerminated, Ergebnis);
    Exec(Dienst, 'uninstall', '', SW_HIDE, ewWaitUntilTerminated, Ergebnis);
  end;
end;
