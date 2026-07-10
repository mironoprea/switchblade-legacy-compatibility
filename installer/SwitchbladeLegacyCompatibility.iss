; Owned application installer only. User data is deliberately never deleted.
#define AppName "Switchblade Legacy Compatibility"
#define AppVersion "0.1.0"
#define AppPublisher "mironoprea"
#define AppExeName "SwitchbladeLegacyCompatibility.exe"

[Setup]
AppId={{D20E4B8E-88F5-4A6D-BD9B-8B5519D57F73}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\Switchblade Legacy Compatibility
DefaultGroupName=Switchblade Legacy Compatibility
DisableDirPage=no
OutputDir=..\dist\installer
OutputBaseFilename=SwitchbladeLegacyCompatibilitySetup
Compression=lzma
SolidCompression=yes
UninstallDisplayName={#AppName}

[Files]
Source: "..\dist\app\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\Switchblade Legacy Compatibility"; Filename: "{app}\{#AppExeName}"
Name: "{autoprograms}\Switchblade Legacy Compatibility\Uninstall"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
