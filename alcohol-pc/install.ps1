# 음주측정 PC 설치 — 한 번만 돌리면 이후는 스스로 갱신한다. UTF-8 BOM 으로 저장.
# 화면에 단계마다 글을 찍고, 같은 내용을 바탕화면 '음주PC설치결과.txt' 에도 남긴다 (실패해도 그 파일을 보면 된다).
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch { }
$ErrorActionPreference = 'Stop'
$desk = [Environment]::GetFolderPath('Desktop')
$logFile = Join-Path $desk '음주PC설치결과.txt'
try { Start-Transcript -Path $logFile -Force | Out-Null } catch { }
try {
    $Dir    = Join-Path $env:ProgramData 'AlcoholWatch'
    $Git    = 'https://raw.githubusercontent.com/psw9715-debug/busyardapp/main/alcohol-pc/watch.ps1'
    $NasDir = '\\192.168.35.22\sctc17\유틸리티\음주PC에이전트'
    $bom = New-Object Text.UTF8Encoding $true
    $report = New-Object Collections.Generic.List[string]

    Write-Host "[1/5] 폴더 만들기: $Dir"
    New-Item -ItemType Directory -Path $Dir -Force | Out-Null

    Write-Host '[2/5] 에이전트 받기 (GitHub, 안 되면 NAS)'
    $code = $null
    try { $b = (Invoke-WebRequest -Uri ($Git + '?t=' + [DateTime]::Now.Ticks) -UseBasicParsing -TimeoutSec 15).Content
          $code = if ($b -is [byte[]]) { [Text.Encoding]::UTF8.GetString($b) } else { [string]$b }; $report.Add('인터넷(GitHub): 됨') } catch { $report.Add('인터넷(GitHub): 안 됨 - ' + $_.Exception.Message) }
    if (-not $code) { try { $p = Join-Path $NasDir 'watch.ps1'; if (Test-Path $p) { $code = [IO.File]::ReadAllText($p, [Text.Encoding]::UTF8); $report.Add('NAS(공유 폴더): 됨') } else { $report.Add('NAS(공유 폴더): 안 됨') } } catch { $report.Add('NAS(공유 폴더): 안 됨') } }
    if (-not $code) { throw ('에이전트를 받지 못했습니다. ' + ($report -join ' / ')) }
    [IO.File]::WriteAllText((Join-Path $Dir 'watch.ps1'), $code.TrimStart([char]0xFEFF), $bom)
    Write-Host '      받았습니다.'

    Write-Host '[3/5] 측정 서버 로그인 확인'
    $login = Join-Path $Dir 'login.json'
    if (-not (Test-Path $login)) {
        $pw = Read-Host '측정 웹 admin 비밀번호를 입력하고 엔터'
        [IO.File]::WriteAllText($login, (@{ user = 'admin'; pass = $pw } | ConvertTo-Json), $bom)
    }
    $cfg = Get-Content $login -Raw -Encoding UTF8 | ConvertFrom-Json
    $apiOk = $false
    foreach ($h in 'http://127.0.0.1:8080', 'http://192.168.35.23:8080') {
        try { $r = Invoke-RestMethod -Uri "$h/Wellcom.Alcohol.Measure.Web/account/login" -Method Post -ContentType 'application/json' `
                  -Body (@{ username = $cfg.user; password = $cfg.pass } | ConvertTo-Json) -TimeoutSec 5
              if ($r.token) { $apiOk = $true; $report.Add("측정 서버 로그인($h): 됨"); break } } catch { }
    }
    if (-not $apiOk) { $report.Add('측정 서버 로그인: 안 됨 (비밀번호나 주소 확인 - 에이전트는 설치함)') }
    try { Add-Type -AssemblyName System.Speech
          $ko = (New-Object Speech.Synthesis.SpeechSynthesizer).GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -eq 'ko-KR' }
          $report.Add($(if ($ko) { '한국어 음성: 있음' } else { '한국어 음성: 없음 (소리 경보만)' })) } catch { $report.Add('음성: 확인 못 함') }

    Write-Host '[4/5] 켤 때 저절로 시작하게 등록'
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

    Write-Host '[5/5] 지금 시작'
    Get-CimInstance Win32_Process -Filter "Name='wscript.exe'" | Where-Object { $_.CommandLine -like '*AlcoholWatch*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
    Start-Process wscript.exe -ArgumentList "`"$(Join-Path $Dir 'run.vbs')`""
    Start-Sleep 5
    $running = [bool](Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" | Where-Object { $_.CommandLine -like '*AlcoholWatch*watch.ps1*' })
    $report.Add($(if ($running) { '지킴이 실행 중: 예' } else { '지킴이 실행 중: 아니오 (잠시 뒤 다시 확인 필요)' }))
    $report.Add('설치 폴더(숨김 폴더): ' + $Dir)
    Write-Host ''
    Write-Host '===== 설치 결과 ====='
    $report | ForEach-Object { Write-Host $_ }
}
catch {
    Write-Host ''
    Write-Host '!!!!! 설치 실패 !!!!!' -ForegroundColor Red
    Write-Host $_.Exception.Message
    Write-Host ($_.ScriptStackTrace)
}
try { Stop-Transcript | Out-Null } catch { }
Write-Host ''
Write-Host "이 내용은 바탕화면의 '음주PC설치결과.txt' 에도 있습니다. 이 글(또는 그 파일)을 클로드에게 알려 주세요."
Read-Host '엔터를 누르면 닫힙니다'
