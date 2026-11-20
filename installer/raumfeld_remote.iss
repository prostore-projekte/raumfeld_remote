; ===========================================================================
; raumfeld_remote.iss - Inno-Setup-Skript fuer den zentralen Dienst
;
; Installiert fuer ALLE Benutzer (Administratorrechte noetig):
;   - Programm nach C:\Program Files\RaumfeldRemote (Dienst-EXE, yt-dlp, ffmpeg, deno)
;   - Windows-Dienst "Raumfeld Remote" (WinSW), startet automatisch mit Windows
;   - Firewall-Regel "Raumfeld Remote Dienst" fuer das Programm RaumfeldRemoteDienst.exe
;     (eingehend, Profile Domaene/Privat). Gilt fuer alle Ports des Programms: Web-Oberflaeche
;     (Standard 8766), Stream (8765) und die UDP-Antworten der Lautsprecher bei der Suche.
;   - Port der Web-Oberflaeche waehlbar (Seite im Assistenten bzw. Parameter /WEBPORT=nnnn)
;   - Datenordner C:\ProgramData\RaumfeldRemote, nur fuer SYSTEM und Administratoren lesbar
;     (enthaelt Passwort-Hash und ggf. YouTube-Cookies)
;   - Startmenue-Verknuepfung zur Web-Oberflaeche fuer alle Benutzer
;
; Bauen:  iscc /DAppVersion=0.8.0 installer\raumfeld_remote.iss
; Erwartet die fertigen Dateien im Ordner ..\paket_dienst (siehe GitHub-Workflow).
; Lautlos installieren:  RaumfeldRemote-Setup-x.y.z.exe /VERYSILENT /SUPPRESSMSGBOXES [/WEBPORT=8766]
; ===========================================================================

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
; Standard-Port der Web-Oberflaeche (bewusst nicht 8080, dort laufen oft andere Dienste)
#define StandardWebPort "8766"
#define StreamPort "8765"
#define ProgrammExe "RaumfeldRemoteDienst.exe"
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
Filename: "{app}\Raumfeld Remote.url"; Section: "InternetShortcut"; Key: "URL"; String: "http://localhost:{code:WebPort}/"

[Icons]
Name: "{commonprograms}\Raumfeld Remote"; Filename: "{app}\Raumfeld Remote.url"

[Run]
; Datenordner absichern: nur SYSTEM (S-1-5-18) und Administratoren (S-1-5-32-544)
Filename: "{sys}\icacls.exe"; Parameters: """{commonappdata}\RaumfeldRemote"" /inheritance:r /grant:r *S-1-5-18:(OI)(CI)F *S-1-5-32-544:(OI)(CI)F"; Flags: runhidden waituntilterminated; StatusMsg: "Datenordner wird abgesichert …"
; Firewall: alte Port-Regeln (bis 0.9.x) entfernen ...
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""Raumfeld Remote Web"""; Flags: runhidden waituntilterminated; StatusMsg: "Firewall-Regeln werden gesetzt …"
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""Raumfeld Remote Stream"""; Flags: runhidden waituntilterminated
; ... und eine Regel fuer das Programm setzen (vorher entfernen, damit sie nicht doppelt ist).
; Wichtig fuer die Suche: Die Lautsprecher antworten per UDP; ohne Programmregel verwirft die
; Windows-Firewall diese Antworten, weil der Dienst (anders als das Desktop-Programm) nie
; den Firewall-Dialog "Zugriff zulassen" zeigt.
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""Raumfeld Remote Dienst"""; Flags: runhidden waituntilterminated
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""Raumfeld Remote Dienst"" dir=in action=allow program=""{app}\{#ProgrammExe}"" enable=yes profile=domain,private"; Flags: runhidden waituntilterminated
; Gewaehlten Port der Web-Oberflaeche in dienst.json eintragen (vor dem Dienststart)
Filename: "{app}\{#ProgrammExe}"; Parameters: "--web-port-setzen {code:WebPort} --daten ""{commonappdata}\RaumfeldRemote"""; Flags: runhidden waituntilterminated; StatusMsg: "Port wird eingetragen …"
; Dienst einrichten und starten
Filename: "{app}\{#DienstExe}"; Parameters: "install"; Flags: runhidden waituntilterminated; StatusMsg: "Dienst wird eingerichtet …"
Filename: "{app}\{#DienstExe}"; Parameters: "start"; Flags: runhidden waituntilterminated; StatusMsg: "Dienst wird gestartet …"
; Am Ende: Web-Oberflaeche oeffnen, um das Passwort festzulegen (nur bei sichtbarer Installation)
Filename: "http://localhost:{code:WebPort}/"; Description: "Web-Oberfläche öffnen und Passwort festlegen"; Flags: postinstall shellexec nowait skipifsilent

[UninstallRun]
Filename: "{app}\{#DienstExe}"; Parameters: "stop"; Flags: runhidden waituntilterminated; RunOnceId: "DienstStop"
Filename: "{app}\{#DienstExe}"; Parameters: "uninstall"; Flags: runhidden waituntilterminated; RunOnceId: "DienstEntfernen"
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""Raumfeld Remote Web"""; Flags: runhidden waituntilterminated; RunOnceId: "FwWeb"
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""Raumfeld Remote Stream"""; Flags: runhidden waituntilterminated; RunOnceId: "FwStream"
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""Raumfeld Remote Dienst"""; Flags: runhidden waituntilterminated; RunOnceId: "FwDienst"

[UninstallDelete]
; Vom Programm erzeugte Dateien im Programmordner (z. B. aktualisiertes yt-dlp, WinSW-Logs)
Type: filesandordirs; Name: "{app}\tools"
Type: files; Name: "{app}\*.log"
; Verknuepfung wird vom Dienst nach Portaenderungen neu geschrieben
Type: files; Name: "{app}\Raumfeld Remote.url"
; Hinweis: C:\ProgramData\RaumfeldRemote (Einstellungen) bleibt bewusst erhalten.

[Code]
var
  // Assistentenseite "Port der Web-Oberflaeche"
  PortSeite: TInputQueryWizardPage;

// Vorschlag fuer den Port: bei einem Update der bisherige (aus der Verknuepfung im
// Programmordner, die der Dienst aktuell haelt), sonst der Standard. 8080 aus alten
// Versionen wird bewusst durch den neuen Standard ersetzt.
function PortVorschlag(): String;
var
  Url: String;
  Stelle: Integer;
begin
  Result := '{#StandardWebPort}';
  Url := GetIniString('InternetShortcut', 'URL', '', WizardDirValue() + '\Raumfeld Remote.url');
  Stelle := Pos('localhost:', Url);
  if Stelle > 0 then
  begin
    Url := Copy(Url, Stelle + Length('localhost:'), 10);
    StringChangeEx(Url, '/', '', True);
    if (StrToIntDef(Url, 0) >= 1024) and (Url <> '8080') then
      Result := Url;
  end;
end;

// Gueltiger Port? 1024..49151 und nicht der Stream-Port
function PortGueltig(Wert: String): Boolean;
var
  Zahl: Integer;
begin
  Zahl := StrToIntDef(Trim(Wert), 0);
  Result := (Zahl >= 1024) and (Zahl <= 49151) and (Zahl <> {#StreamPort});
end;

procedure InitializeWizard();
begin
  PortSeite := CreateInputQueryPage(wpSelectDir,
    'Port der Web-Oberfläche',
    'Unter welchem Port soll die Web-Oberfläche im Netz erreichbar sein?',
    'Standard ist {#StandardWebPort}. Nur ändern, wenn der Port schon belegt ist. ' +
    'Später jederzeit in der Web-Oberfläche unter Einstellungen → Ports änderbar.');
  PortSeite.Add('Port (1024 bis 49151):', False);
  // Lautlose Installation: Port per Parameter /WEBPORT=nnnn
  PortSeite.Values[0] := ExpandConstant('{param:WEBPORT|}');
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if (CurPageID = PortSeite.ID) and (PortSeite.Values[0] = '') then
    PortSeite.Values[0] := PortVorschlag();
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = PortSeite.ID) and not PortGueltig(PortSeite.Values[0]) then
  begin
    MsgBox('Bitte einen Port zwischen 1024 und 49151 angeben (nicht {#StreamPort}, der ist für den Stream).',
      mbError, MB_OK);
    Result := False;
  end;
end;

// Wird in [INI] und [Run] als {code:WebPort} verwendet
function WebPort(Param: String): String;
begin
  if not PortGueltig(PortSeite.Values[0]) then
    PortSeite.Values[0] := PortVorschlag();   // z. B. lautlos ohne oder mit falschem /WEBPORT
  Result := Trim(PortSeite.Values[0]);
end;

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
