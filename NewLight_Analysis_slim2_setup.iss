; Inno Setup script for the PyInstaller-slimmed experimental package.
; Source: dist_slim2_20260804\NewLight_Analysis

#define MyAppName "NewLight_Analysis"
#define MyAppVersion "1.0-slim2"
#define MyAppPublisher "Azu"
#define MyAppExeName "NewLight_Analysis.exe"
#define SourceRoot "E:\WorkSpace\NewLight_Analysis\dist_slim2_20260804\NewLight_Analysis"

[Setup]
AppId={{86DE2D1D-33B1-4BAA-9A8D-4C46039E2DA4
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=E:\WorkSpace\NewLight_Analysis\Output
OutputBaseFilename=NewLight_Analysis_slim2_setup
SetupIconFile=E:\WorkSpace\NewLight_Analysis\xhr.ico
Password=xhr8880601
Encryption=yes
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes
LZMAAlgorithm=1
LZMANumFastBytes=273
LZMANumBlockThreads=2
WizardStyle=modern
Uninstallable=yes
ChangesAssociations=no
AllowNoIcons=yes

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; Flags: unchecked

[Files]
Source: "{#SourceRoot}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent
