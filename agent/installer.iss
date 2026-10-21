; 차고지 받아쓰기 — 설치 프로그램 (Inno Setup)
;   컴파일:  "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
;
; 받는 쪽(A 컴퓨터)은 이 설치 파일 하나만 누르면 된다.
; 파이썬도, pywin32 도, 따로 설치할 것이 없다 — exe 안에 전부 들어 있다.

#define AppName "차고지 받아쓰기"
#define AppVer "1.3.0"
#define AppExe "BusyardAgent.exe"

[Setup]
AppId={{7A1C5E42-9B3D-4C77-8E21-5C0B2F8A6D31}
AppName={#AppName}
AppVersion={#AppVer}
AppPublisher=세종도시교통공사 상황실
DefaultDirName={autopf}\차고지받아쓰기
DefaultGroupName={#AppName}
; 누를 것을 없앤다 — 눌러서 넘길 것이 없으니 실수로 잘못 고를 일도 없다.
; 받는 쪽(A 컴퓨터)에서는 파일을 두 번 누르면 그대로 깔리고 바로 시작한다.
DisableWelcomePage=yes
DisableProgramGroupPage=yes
DisableDirPage=yes
DisableReadyPage=yes
DisableFinishedPage=yes
OutputDir=dist
OutputBaseFilename=차고지받아쓰기_Setup_{#AppVer}
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible

[Code]
// 보이지 않게 돌고 있으면 파일을 덮어쓸 수 없다. 깔기 전에 조용히 끈다.
function InitializeSetup(): Boolean;
var rc: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/im {#AppExe} /f',
       '', SW_HIDE, ewWaitUntilTerminated, rc);
  Result := True;
end;

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Files]
Source: "dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion
; isreadme 를 떼었다 — 다 깔고 나서 읽어보기 창이 뜨지 않게
Source: "읽어보기.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
; 창도 트레이 아이콘도 없는 프로그램이다. 끌 길은 시작 메뉴에 둔다.
Name: "{group}\{#AppName} 끄기"; Filename: "{sys}\taskkill.exe"; Parameters: "/im {#AppExe} /f"; IconFilename: "{app}\{#AppExe}"
Name: "{group}\{#AppName} 기록 보기"; Filename: "{localappdata}\차고지받아쓰기\받아쓰기.log"
Name: "{group}\{#AppName} 제거"; Filename: "{uninstallexe}"
; 켤 때 저절로 뜬다 — 고를 것도 없이 늘 그렇게 한다
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExe}"

[Run]
; 묻지 않고 바로 시작한다 (postinstall 은 "완료" 쪽의 체크 상자라 뺀다)
Filename: "{app}\{#AppExe}"; Flags: nowait

; 보이지 않게 돌고 있으므로, 지우기 전에 먼저 끈다 (안 돌고 있어도 탈이 없다)
[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/im {#AppExe} /f"; Flags: runhidden; RunOnceId: "stopagent"

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\차고지받아쓰기"
