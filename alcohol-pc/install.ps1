# 음주측정 PC 설치 — 한 번만 돌리면 이후는 스스로 갱신한다. UTF-8 BOM 으로 저장.
#   powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/psw9715-debug/busyardapp/main/alcohol-pc/install.ps1 | iex"
$ErrorActionPreference = 'Stop'
$Dir    = Join-Path $env:ProgramData 'AlcoholWatch'
$Git    = 'https://raw.githubusercontent.com/psw9715-debug/busyardapp/main/alcohol-pc/watch.ps1'
$NasDir = '\\192.168.35.22\sctc17\유틸리티\음주PC에이전트'
New-Item -ItemType Directory -Path $Dir -Force | Out-Null
$bom = New-Object Text.UTF8Encoding $true
$report = New-Object Collections.Generic.List[string]

# 1) 에이전트 받기 — GitHub, 안 되면 NAS
$code = $null
try { $b = (Invoke-WebRequest -Uri ($Git + '?t=' + [DateTime]::Now.Ticks) -UseBasicParsing -TimeoutSec 15).Content
      $code = if ($b -is [byte[]]) { [Text.Encoding]::UTF8.GetString($b) } else { [string]$b }; $report.Add('인터넷(GitHub): 됨') } catch { $report.Add('인터넷(GitHub): 안 됨') }
if (-not $code) { try { $p = Join-Path $NasDir 'watch.ps1'; if (Test-Path $p) { $code = [IO.File]::ReadAllText($p, [Text.Encoding]::UTF8); $report.Add('NAS(공유 폴더): 됨') } } catch { } }
if (-not $code) { Write-Host ($report -join "`n"); Write-Host 'NAS(공유 폴더): 안 됨 — 에이전트를 받지 못했습니다.'; Start-Sleep 15; exit 1 }
[IO.File]::WriteAllText((Join-Path $Dir 'watch.ps1'), $code.TrimStart([char]0xFEFF), $bom)

# 2) 측정 웹 로그인 정보 (이 PC 의 측정 프로그램이 이미 쓰는 계정)
$login = Join-Path $Dir 'login.json'
if (-not (Test-Path $login)) {
    $pw = Read-Host '측정 웹 admin 비밀번호'
    [IO.File]::WriteAllText($login, (@{ user = 'admin'; pass = $pw } | ConvertTo-Json), $bom)
}
$cfg = Get-Content $login -Raw -Encoding UTF8 | ConvertFrom-Json
$apiOk = $false
foreach ($h in 'http://127.0.0.1:8080', 'http://192.168.35.23:8080') {
    try { $r = Invoke-RestMethod -Uri "$h/Wellcom.Alcohol.Measure.Web/account/login" -Method Post -ContentType 'application/json' `
              -Body (@{ username = $cfg.user; password = $cfg.pass } | ConvertTo-Json) -TimeoutSec 5
          if ($r.token) { $apiOk = $true; $report.Add("측정 서버 로그인($h): 됨"); break } } catch { }
}
if (-not $apiOk) { $report.Add('측정 서버 로그인: 안 됨 (비밀번호나 주소 확인)') }
try { Add-Type -AssemblyName System.Speech
      $ko = (New-Object Speech.Synthesis.SpeechSynthesizer).GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -eq 'ko-KR' }
      $report.Add($(if ($ko) { '한국어 음성: 있음' } else { '한국어 음성: 없음 (소리 경보만)' })) } catch { $report.Add('음성: 확인 못 함') }

# 3) 보이지 않게 돌리는 실행기 — 꺼지면 다시 띄우고, 새 판이 계속 죽으면 이전 판으로 되돌린다
$vbs = @"
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
d = "$Dir"
fast = 0
Do
  t = Timer
  sh.Run "powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & d & "\watch.ps1""", 0, True
  If Timer - t < 20 Then fast = fast + 1 Else fast = 0
  If fast >= 3 And fso.FileExists(d & "\watch.prev.ps1") Then
    fso.CopyFile d & "\watch.prev.ps1", d & "\watch.ps1", True
    fast = 0
  End If
  WScript.Sleep 5000
Loop
"@
[IO.File]::WriteAllText((Join-Path $Dir 'run.vbs'), $vbs, [Text.Encoding]::ASCII)
Copy-Item (Join-Path $Dir 'run.vbs') (Join-Path ([Environment]::GetFolderPath('Startup')) 'AlcoholWatch.vbs') -Force

# 4) 지금 시작 (옛것이 돌고 있으면 끄고)
Get-CimInstance Win32_Process -Filter "Name='wscript.exe'" | Where-Object { $_.CommandLine -like '*AlcoholWatch*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Start-Process wscript.exe -ArgumentList "`"$(Join-Path $Dir 'run.vbs')`""
$report.Add('설치 끝 — 이 창은 닫아도 됩니다. 보이지 않게 돌고, 켤 때 저절로 시작합니다.')
Add-Type -AssemblyName System.Windows.Forms
[Windows.Forms.MessageBox]::Show(($report -join "`r`n"), '음주PC 지킴이 설치 결과') | Out-Null
