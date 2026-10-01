; 차고지 받아쓰기 — 설치 프로그램 (Inno Setup)
;   컴파일:  "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
;
; 받는 쪽(A 컴퓨터)은 이 설치 파일 하나만 누르면 된다.
; 파이썬도, pywin32 도, 따로 설치할 것이 없다 — exe 안에 전부 들어 있다.

#define AppName "차고지 받아쓰기"
#define AppVer "1.0.0"
#define AppExe "BusyardAgent.exe"

[Setup]
AppId={{7A1C5E42-9B3D-4C77-8E21-5C0B2F8A6D31}
AppName={#AppName}
AppVersion={#AppVer}
AppPublisher=세종도시교통공사 상황실
DefaultDirName={autopf}\차고지받아쓰기
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
OutputDir=dist
OutputBaseFilename=차고지받아쓰기_Setup_{#AppVer}
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesInstallIn64BitMode=x64compatible

[Code]
var TokenPage: TInputQueryWizardPage;

function TokenFile(): String;
begin
  Result := ExpandConstant('{localappdata}\차고지받아쓰기\토큰.txt');
end;

// 보이지 않게 돌고 있으면 파일을 덮어쓸 수 없다. 깔기 전에 조용히 끈다.
function InitializeSetup(): Boolean;
var rc: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/im {#AppExe} /f',
       '', SW_HIDE, ewWaitUntilTerminated, rc);
  Result := True;
end;

// 엑셀을 고친 뒤 "다 됐습니다" 를 폰에 돌려주려면 올릴 권한(토큰)이 있어야 한다.
// 한 번만 넣어 두면 된다. 비워 두면 엑셀은 고치고 폰에만 알리지 못한다.
procedure InitializeWizard();
var old: AnsiString;
begin
  TokenPage := CreateInputQueryPage(wpSelectTasks,
    '폰에 결과를 알리는 토큰',
    '엑셀에 적은 뒤 "다 됐습니다" 를 폰에 돌려주는 데 씁니다.',
    '휴대폰 앱의 [진단] → PC 전송에 넣은 것과 같은 토큰을 붙여 넣으세요.' + #13#10 +
    '비워 두어도 됩니다. 그러면 엑셀은 고치지만 폰에는 알리지 못합니다.');
  TokenPage.Add('토큰:', False);
  if LoadStringFromFile(TokenFile(), old) then     // 다시 깔 때는 전에 넣은 것을 보여 준다
    TokenPage.Values[0] := Trim(String(old));
end;

procedure CurStepChanged(CurStep: TSetupStep);
var tok: String;
begin
  if CurStep <> ssPostInstall then Exit;
  tok := Trim(TokenPage.Values[0]);
  if tok = '' then                                 // 조용히 깔 때는 /TOKEN=... 으로 준다
    tok := Trim(ExpandConstant('{param:TOKEN|}'));
  if tok = '' then Exit;                           // 비워 두면 전에 넣은 것을 지우지 않는다
  ForceDirectories(ExpandConstant('{localappdata}\차고지받아쓰기'));
  SaveStringToFile(TokenFile(), AnsiString(tok), False);
end;

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "startup"; Description: "윈도우를 켤 때 자동으로 시작"; GroupDescription: "추가 설정:"
Name: "desktopicon"; Description: "바탕화면에 바로가기 만들기"; GroupDescription: "추가 설정:"; Flags: unchecked

[Files]
Source: "dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "읽어보기.txt"; DestDir: "{app}"; Flags: ignoreversion isreadme

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
; 창도 트레이 아이콘도 없는 프로그램이다. 끌 길은 시작 메뉴에 둔다.
Name: "{group}\{#AppName} 끄기"; Filename: "{sys}\taskkill.exe"; Parameters: "/im {#AppExe} /f"; IconFilename: "{app}\{#AppExe}"
Name: "{group}\{#AppName} 기록 보기"; Filename: "{localappdata}\차고지받아쓰기\받아쓰기.log"
Name: "{group}\{#AppName} 제거"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: startup

[Run]
Filename: "{app}\{#AppExe}"; Description: "지금 바로 시작하기"; Flags: nowait postinstall skipifsilent

; 보이지 않게 돌고 있으므로, 지우기 전에 먼저 끈다 (안 돌고 있어도 탈이 없다)
[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/im {#AppExe} /f"; Flags: runhidden; RunOnceId: "stopagent"

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\차고지받아쓰기"
