#define MyAppName "EZ Expedite"
#define MyAppVersion "0.1.1"
#define MyAppPublisher "EZ Fabricating / WMF"
#define MyAppExeName "EZ_Expedite.exe"

[Setup]
AppId={{A2C34A67-2C58-4B8E-8DA0-7C70A8F4A97B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\EZ Expedite
DefaultGroupName=EZ Expedite
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist-installer
OutputBaseFilename=EZ_Expedite_Setup_{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no
UninstallDisplayName=EZ Expedite
UninstallDisplayIcon={app}\{#MyAppExeName}
SetupLogging=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; DestName: "{#MyAppExeName}"; Flags: ignoreversion

[Icons]
Name: "{group}\EZ Expedite"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\EZ Expedite"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch EZ Expedite"; Flags: nowait postinstall skipifsilent
