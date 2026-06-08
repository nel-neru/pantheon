; Inno Setup script — Pantheon インストーラ (Pantheon-Setup.exe)
; ビルド: packaging\build.ps1 が PyInstaller の出力 dist\Pantheon\ を取り込んでコンパイルする。
;   手動: iscc packaging\pantheon.iss
; 前提: 先に dist\Pantheon\Pantheon.exe が生成済みであること。

#define AppName "Pantheon"
#define AppVersion "0.1.0"
#define AppPublisher "nel"
#define AppExeName "Pantheon.exe"
#define AppUrl "https://github.com/nel-neru/pantheon"

[Setup]
AppId={{8F3A1C2D-5E6B-4A7C-9D1E-2F3A4B5C6D7E}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppUrl}
AppSupportURL={#AppUrl}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; 個人ツールなので管理者権限なしでインストール可能にする（UAC を出さない）
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=Pantheon-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; PyInstaller の onedir 出力一式（Pantheon.exe + _internal\ + 同梱データ）
Source: "..\dist\Pantheon\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
; ダブルクリックで GUI（人間用可視化サイト）が起動しブラウザが自動で開く
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Comment: "Pantheon Web GUI を起動"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[Code]
function ClaudeAvailable(): Boolean;
var
  ResultCode: Integer;
begin
  Result := Exec('cmd.exe', '/C where claude', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    if not ClaudeAvailable() then
      MsgBox(
        'Pantheon の生成機能（コード分析・チャット・改善適用）には、外部の Claude Code CLI が必要です。' + #13#10 +
        'まだ導入していない場合は `claude` をインストールし、一度 `claude` を実行してログインしてください。' + #13#10#13#10 +
        'GUI・ダッシュボード・各種閲覧機能は claude なしでも動作します。',
        mbInformation, MB_OK);
  end;
end;
