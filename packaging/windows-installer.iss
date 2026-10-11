#ifndef AppVersion
  #define AppVersion "0.3.5"
#endif
[Setup]
AppId=easycrawl.EasyCrawl
AppName=EasyCrawl
AppVersion={#AppVersion}
AppPublisher=EasyCrawl
AppPublisherURL=https://github.com/RJ2320/easycrawl
AppUpdatesURL=https://github.com/RJ2320/easycrawl/releases/latest
DefaultDirName={localappdata}\Programs\EasyCrawl
DefaultGroupName=EasyCrawl
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist\installer
OutputBaseFilename=EasyCrawl-Setup-{#AppVersion}-windows
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\EasyCrawl.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
[Files]
Source: "..\dist\EasyCrawl\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{autoprograms}\EasyCrawl"; Filename: "{app}\EasyCrawl.exe"; AppUserModelID: "easycrawl.EasyCrawl"
Name: "{autodesktop}\EasyCrawl"; Filename: "{app}\EasyCrawl.exe"; Tasks: desktopicon; AppUserModelID: "easycrawl.EasyCrawl"
[Run]
Filename: "{app}\EasyCrawl.exe"; Description: "Open EasyCrawl"; Flags: nowait postinstall skipifsilent
