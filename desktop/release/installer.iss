; Inno Setup script for quorum-gatherer (Windows).
; Built in CI (run from the desktop/ dir):
;   iscc /DAppVersion=<version> release\installer.iss
; Packages the PyInstaller onedir (desktop\dist\quorum-gatherer\) into a per-user setup .exe.
;
; UNSIGNED for now (per plan): first launch shows a SmartScreen "More info -> Run anyway"
; prompt; integrity is provided via the published SHA256SUMS.txt. To sign later, add a
; [Setup] SignTool= directive (or sign the emitted setup .exe in CI) — no other changes.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "quorum-gatherer"
#define AppPublisher "Brett Bergin"
#define AppExeName "quorum-gatherer.exe"

[Setup]
AppId={{7F3A2C9E-1B4D-4A6F-8E2C-9D5B7A1C3E4F}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Per-user install so no admin/UAC prompt is needed (autopf -> Local\Programs at lowest).
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\..
OutputBaseFilename={#AppName}-{#AppVersion}-windows-setup
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
Source: "..\dist\quorum-gatherer\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
