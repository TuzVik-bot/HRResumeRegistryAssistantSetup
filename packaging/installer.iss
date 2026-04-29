#define MyAppName "HR Resume Registry Assistant"
#define MyAppVersion "1.0.0"
#define MyAppVersionInfo "1.0.0.0"
#define MyAppDeveloper "Nikita Karpuk / AAR Group"
#define MyAppPublisher "AAR Group"
#define MyAppExeName "HRResumeRegistryAssistant.exe"

[Setup]
AppId={{85F26C8B-6E32-4F1A-A33F-6D512AF2DD30}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=HRResumeRegistryAssistantSetup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
InfoBeforeFile=installer_info_ru.txt
VersionInfoVersion={#MyAppVersionInfo}
VersionInfoCompany={#MyAppDeveloper}
VersionInfoDescription={#MyAppName} installer
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\HRResumeRegistryAssistant.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "INSTALL_INSTRUCTIONS.txt"; DestDir: "{app}"; DestName: "Инструкция.txt"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Инструкция"; Filename: "{app}\Инструкция.txt"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить {#MyAppName}"; Flags: nowait postinstall skipifsilent
