# 음주측정 PC 지킴이 — 측정 서버의 기록을 '보기만' 하고, 불기 단계에서 끊기면 이 PC 화면·소리로 바로 알린다.
# 이 파일은 UTF-8 BOM 으로 저장해야 한다 (PowerShell 5.1 이 한글을 읽으려면).
# 측정 프로그램은 건드리지 않는다: 로그인과 GET 조회만 한다 (출퇴근 관리가 B PC 에서 하는 것과 같다).
param([switch]$NoRun)
$VERSION = '1.0.9'
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch { }   # 옛 .NET 은 TLS1.2 를 따로 켜야 GitHub 에 닿는다

$Dir   = if ($env:ALCOHOL_TEST_DIR) { $env:ALCOHOL_TEST_DIR } else { Join-Path $env:ProgramData 'AlcoholWatch' }
$Self  = Join-Path $Dir 'watch.ps1'
$GitUrl = 'https://raw.githubusercontent.com/psw9715-debug/busyardapp/main/alcohol-pc/watch.ps1'
$NasDir = '\\192.168.35.22\sctc17\유틸리티\음주PC에이전트'
$Hosts  = if ($env:ALCOHOL_TEST_HOST) { @($env:ALCOHOL_TEST_HOST) } else { @('http://127.0.0.1:8080', 'http://192.168.35.23:8080') }
$Base   = '/Wellcom.Alcohol.Measure.Web'
$Done   = 'Y', 'N', 'S', 'D'        # 결과가 난 것
$ClickWait = 13                     # 찰칵(준비) 뒤 이 초가 지나도 측정완료가 없으면 알린다
$MaxAge    = 90                     # 카드 뒤 이보다 지난 회차는 알리지 않는다
$OnSiteAlarm = $false               # 데이터 수집 단계: 음주측정 PC 화면 경보는 끄고 기록만 한다(alerts.log). 켜는 것은 사용자가 정한 뒤에.
$AlarmShow = 40                     # 경보를 띄워 두는 초

function Log($m) {
    try {
        $f = Join-Path $Dir 'watch.log'
        if ((Test-Path $f) -and (Get-Item $f).Length -gt 2MB) { Move-Item $f "$f.old" -Force }
        Add-Content -Path $f -Value ("{0} {1}" -f (Get-Date -Format 'MM-dd HH:mm:ss'), $m) -Encoding UTF8
    } catch { }
}

# ── 끊김 판정 (순수 함수: 시험할 수 있게 밖으로 뺐다) ────────────────────────
# $rows   : 서버가 준 행들 (empid, count, result, createdate, empname)
# $photos : "empid|count" → 사진 type 문자열 배열
# $st     : 상태 (Click: 찰칵 처음 본 시각, Told: 이미 알린 키)
function Get-Alarms($rows, $photos, $nowUtc, $st) {
    $out = @()
    $maxCount = @{}
    foreach ($r in $rows) {
        $n = 0; [void][int]::TryParse([string]$r.count, [ref]$n)
        if (-not $maxCount.ContainsKey([string]$r.empid) -or $maxCount[[string]$r.empid] -lt $n) { $maxCount[[string]$r.empid] = $n }
    }
    foreach ($r in $rows) {
        $key = "$($r.empid)|$($r.count)"
        $res = ([string]$r.result).Trim()
        $types = @(); if ($photos.ContainsKey($key)) { $types = @($photos[$key]) }
        if ($types -contains '로그인' -and -not $st.Click.ContainsKey($key)) { $st.Click[$key] = $nowUtc }
        if ($st.Told.ContainsKey($key) -or $Done -contains $res -or $types -contains '측정완료') { continue }
        $age = 0.0
        try { $age = ($nowUtc - [DateTime]::ParseExact(([string]$r.createdate).Substring(0, 19), 'yyyy-MM-ddTHH:mm:ss', [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::AssumeUniversal -bor [Globalization.DateTimeStyles]::AdjustToUniversal)).TotalSeconds } catch { }
        if ($age -gt $MaxAge) { continue }
        $n = 0; [void][int]::TryParse([string]$r.count, [ref]$n)
        if ($maxCount[[string]$r.empid] -gt $n) { continue }      # 이미 다시 찍었다 — 측정기 앞에 있다
        $why = $null
        if ($types -contains '미측정') { $why = "측정기가 '미측정'으로 끝냈습니다" }
        elseif ($st.Click.ContainsKey($key) -and ($nowUtc - $st.Click[$key]).TotalSeconds -ge $ClickWait) { $why = "불기 단계에서 끊겼습니다" }
        if ($why) { $st.Told[$key] = 1; $out += [pscustomobject]@{ Key = $key; Name = ([string]$r.empname); Empid = [string]$r.empid; Count = $n; Why = $why } }
    }
    return , $out
}

# ── 측정 프로그램 로그로 즉시 판정 (순수 함수) ───────────────────────────────
# 2026-11-13 로그 실측: 찰칵(로그인캡처 끝) 뒤 끝나지 못한 7건 중 5건은 1~6초 안에 '0x81 음주측정기 에러' 가 찍히고 프로그램이 창을 닫았다.
# 나머지는 창이 닫힘(사람이 닫기, 또는 측정기가 준비 상태로 돌아감). 정상 300건은 '측정완료캡처 시작' 이 먼저 나온다.
# 반환: $null(아무 일 없음) / 'NEW'(새 측정 시작) / 경보 사유 문자열
function Step-AppLog($line, $st) {
    if ($line -match 'readySoundPlayRunFlag') { $st.Pending = $false; $st.Fired = $false; return 'NEW' }
    if ($line -match '로그인캡처 끝') { $st.Pending = $true; return $null }
    if ($line -match '측정완료캡처 시작') { $st.Pending = $false; return $null }
    if ($st.Pending -and -not $st.Fired -and $line -match '미측정캡처 시작') { $st.Fired = $true; return '측정기가 미측정으로 끝냈습니다' }
    if ($line -match 'Close MainWindow') {
        $was = $st.Pending -and -not $st.Fired
        $st.Pending = $false
        if ($was) { $st.Fired = $true; return '측정 창이 끝나지 못하고 닫혔습니다' }
        return $null
    }
    if ($st.Pending -and -not $st.Fired -and $line -match '음주측정기 에러') { $st.Fired = $true; return '음주측정기 에러가 났습니다' }
    return $null
}

if ($NoRun) { return }

# ── 여기부터 실제로 도는 부분 ────────────────────────────────────────────────
New-Item -ItemType Directory -Path $Dir -Force | Out-Null
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
try { Add-Type -AssemblyName System.Speech } catch { }

$mutex = New-Object Threading.Mutex($false, 'Global\AlcoholWatchAgent')
if (-not $mutex.WaitOne(0)) { exit 0 }       # 이미 하나 돌고 있다

$cfg = $null
try { $cfg = Get-Content (Join-Path $Dir 'login.json') -Raw -Encoding UTF8 | ConvertFrom-Json } catch { }
$script:Host_ = $null; $script:Token = $null; $script:TokenAt = [DateTime]::MinValue; $script:Cp = $null

function Connect-Api {
    foreach ($h in $Hosts) {
        try {
            $r = Invoke-RestMethod -Uri "$h$Base/account/login" -Method Post -ContentType 'application/json' `
                -Body (@{ username = $cfg.user; password = $cfg.pass } | ConvertTo-Json) -TimeoutSec 4
            if ($r.token) { $script:Host_ = $h; $script:Token = $r.token; $script:Cp = $r.cpcode; $script:TokenAt = Get-Date; return $true }
        } catch { }
    }
    return $false
}
# (배열은 변수에 받아서 돌려줘야 한 줄씩 풀려 나온다 — 바로 return 하면 통째로 한 덩이가 된다)
function Get-Api($path) {
    if (-not $script:Token -or ((Get-Date) - $script:TokenAt).TotalMinutes -gt 50) { if (-not (Connect-Api)) { throw '로그인 못 함' } }
    try { $res = Invoke-RestMethod -Uri "$($script:Host_)$Base$path" -Headers @{ Authorization = "Bearer $($script:Token)" } -TimeoutSec 3; return $res }
    catch {
        if ($_.Exception.Response -and [int]$_.Exception.Response.StatusCode -eq 401) {
            if (-not (Connect-Api)) { throw '다시 로그인 못 함' }
            $res = Invoke-RestMethod -Uri "$($script:Host_)$Base$path" -Headers @{ Authorization = "Bearer $($script:Token)" } -TimeoutSec 3; return $res
        }
        throw
    }
}

# 화면 경보: 화면 한가운데 크게 + 소리 + (한국어 음성이 있으면) 말. 사람이 읽을 때까지 40초.
$script:Alarm = $null
function Show-Alarm($a) {
    if (-not $OnSiteAlarm -and $a.Empid -ne 'demo') {
        Log "경보 감지(화면은 꺼 둠) $($a.Name) $($a.Count)회차 — $($a.Why)"
        try { Add-Content -Path (Join-Path $Dir 'alerts.log') -Encoding UTF8 -Value ("{0} {1} {2}" -f (Get-Date -Format 'MM-dd HH:mm:ss'), $a.Name, $a.Why) } catch { }
        return
    }
    Close-Alarm
    if ($env:ALCOHOL_TEST_NOUI) { Log "경보 $($a.Name) $($a.Count)회차 — $($a.Why)"; return }
    $f = New-Object Windows.Forms.Form
    $f.FormBorderStyle = 'None'; $f.TopMost = $true; $f.StartPosition = 'CenterScreen'
    $f.Size = New-Object Drawing.Size(900, 420); $f.BackColor = [Drawing.Color]::Firebrick; $f.ShowInTaskbar = $false
    $l = New-Object Windows.Forms.Label
    $l.Dock = 'Fill'; $l.TextAlign = 'MiddleCenter'; $l.ForeColor = [Drawing.Color]::White
    $l.Font = New-Object Drawing.Font('맑은 고딕', 36, [Drawing.FontStyle]::Bold)
    $l.Text = if ($a.Text) { $a.Text } else { "$($a.Name)님`r`n음주측정이 되지 않았습니다`r`n다시 측정해 주세요" }
    $f.Controls.Add($l)
    $f.Show()
    $snd = $null
    try { $snd = New-Object Media.SoundPlayer 'C:\Windows\Media\Alarm01.wav'; $snd.PlayLooping() } catch { }
    $voice = $null
    try {
        $voice = New-Object Speech.Synthesis.SpeechSynthesizer
        $voice.SelectVoiceByHints('NotSet', 'NotSet', 0, [Globalization.CultureInfo]'ko-KR')
        $voice.SpeakAsync($(if ($a.Say) { $a.Say } else { "$($a.Name)님! 음주측정이 되지 않았습니다! 다시 측정해 주세요!" })) | Out-Null
    } catch { }
    $script:Alarm = @{ Form = $f; Snd = $snd; Voice = $voice; Until = (Get-Date).AddSeconds($AlarmShow); Empid = $a.Empid; Count = $a.Count }
    Log "경보 $($a.Name) $($a.Count)회차 — $($a.Why)"
}
function Close-Alarm {
    $x = $script:Alarm; if (-not $x) { return }
    $script:Alarm = $null
    try { if ($x.Snd) { $x.Snd.Stop() } } catch { }
    try { if ($x.Voice) { $x.Voice.SpeakAsyncCancelAll(); $x.Voice.Dispose() } } catch { }
    try { $x.Form.Close(); $x.Form.Dispose() } catch { }
}
$script:AppSt = @{ Pending = $false; Fired = $false }
$script:AppPath = $null; $script:AppPos = 0L; $script:AppRest = ''; $script:LogAlarmAt = [DateTime]::MinValue
function Poll-AppLog {
    try {
        $lines = @()
        $path = Join-Path $AppLogDir ("ManagementApp.{0}.log" -f (Get-Date -Format 'yyyyMMdd'))
        if (Test-Path $path) {
            $len = (Get-Item $path).Length
            if ($path -ne $script:AppPath) { $script:AppPath = $path; $script:AppPos = $len; $script:AppRest = '' }   # 켠 때/날이 바뀐 때는 옛 줄을 다시 읽지 않는다
            elseif ($len -lt $script:AppPos) { $script:AppPos = $len }
            elseif ($len -gt $script:AppPos) {
                $fs = [IO.File]::Open($path, 'Open', 'Read', 'ReadWrite')
                try { [void]$fs.Seek($script:AppPos, 'Begin'); $buf = New-Object byte[] ($len - $script:AppPos); $n = $fs.Read($buf, 0, $buf.Length); $script:AppPos += $n }
                finally { $fs.Dispose() }
                $parts = ($script:AppRest + [Text.Encoding]::UTF8.GetString($buf, 0, $n)) -split "`n"
                $script:AppRest = $parts[-1]
                if ($parts.Count -gt 1) { $lines = $parts[0..($parts.Count - 2)] }
            }
        }
        foreach ($ln in $lines) {
            $r = Step-AppLog $ln $script:AppSt
            if ($r -eq 'NEW') { if ($script:Alarm -and $script:Alarm.Empid -eq 'log') { Close-Alarm } }
            elseif ($r) { Raise-LogAlarm $r }
        }
    } catch { }
}
function Raise-LogAlarm($why) {
    $script:LogAlarmAt = Get-Date
    Show-Alarm ([pscustomobject]@{ Name = ''; Empid = 'log'; Count = 0; Why = "측정 프로그램 로그: $why"
        Text = "음주측정이 되지 않았습니다`r`n다시 측정해 주세요"; Say = '음주측정이 되지 않았습니다! 다시 측정해 주세요!' })
}
function Pump($sec) {
    $end = (Get-Date).AddSeconds($sec)
    while ((Get-Date) -lt $end) { [Windows.Forms.Application]::DoEvents(); Serve-One; Poll-AppLog; Start-Sleep -Milliseconds 100 }
}

# 살펴보기: 측정 프로그램의 위치·로그·튕김 흔적을 파일로 남긴다 (읽기만, 별도 작업으로 — 경보를 늦추지 않게).
function Start-Inventory {
    $out = Join-Path $Dir 'inventory.txt'
    Start-Job -ScriptBlock {
        param($out)
        $o = New-Object Collections.Generic.List[string]
        $o.Add("== 시각 $(Get-Date)  PC $env:COMPUTERNAME  사용자 $env:USERNAME")
        $o.Add("== 창이 있는 프로세스")
        Get-Process | Where-Object { $_.MainWindowTitle } | ForEach-Object { $o.Add("$($_.Id)`t$($_.ProcessName)`t$($_.MainWindowTitle)`t$($_.Path)") }
        $o.Add("== Windows 밖 프로세스(경로)")
        Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -and $_.ExecutablePath -notlike 'C:\Windows\*' } |
            ForEach-Object { $o.Add("$($_.ProcessId)`t$($_.Name)`t$($_.ExecutablePath)`t$($_.CommandLine)") }
        $o.Add("== 듣고 있는 포트")
        Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
            $p = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue; $o.Add("$($_.LocalPort)`t$($p.ProcessName)") }
        $o.Add("== 최근 이틀 바뀐 로그·음성 파일 (C:\, D:\ 3단계 안, Windows·Users·ProgramData 제외)")
        $sw = [Diagnostics.Stopwatch]::StartNew()       # 큰 자료 폴더가 있어도 1분 넘게 훑지 않는다
        foreach ($root in 'C:\', 'D:\') {
            if (-not (Test-Path $root)) { continue }
            $dirs = Get-ChildItem $root -Directory -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -notin 'Windows', 'ProgramData', 'Users', 'Documents and Settings', 'WindowsApps', 'System Volume Information' -and $_.Name -notlike '$*' }
            foreach ($d in $dirs) {
                if ($sw.Elapsed.TotalSeconds -gt 60) { $o.Add("(시간 제한으로 $($d.FullName) 앞에서 멈춤)"); break }
                Get-ChildItem $d.FullName -Recurse -Depth 2 -File -Include *.log, *.wav, *.mp3, *.txt -ErrorAction SilentlyContinue |
                    Where-Object { $_.LastWriteTime -gt (Get-Date).AddDays(-2) } | Select-Object -First 40 |
                    ForEach-Object { $o.Add("$($_.LastWriteTime.ToString('MM-dd HH:mm'))`t$($_.Length)`t$($_.FullName)") }
            }
        }
        $o.Add("== 최근 하루 응용 프로그램 오류·멈춤 (측정 프로그램이 죽었는지)")
        try {
            Get-WinEvent -FilterHashtable @{ LogName = 'Application'; Level = 1, 2; StartTime = (Get-Date).AddHours(-24) } -MaxEvents 60 -ErrorAction Stop |
                ForEach-Object { $o.Add("$($_.TimeCreated.ToString('MM-dd HH:mm:ss'))`t$($_.ProviderName)`t$(($_.Message -split "`n")[0])") }
        } catch { $o.Add("(없음 또는 읽지 못함)") }
        [IO.File]::WriteAllLines($out, $o, (New-Object Text.UTF8Encoding $true))
    } -ArgumentList $out | Out-Null
}

# 보고: NAS 에 닿으면 기록을 올려 둔다 (밖에서 읽는 길). 못 닿으면 말없이 넘어간다.
function Test-NasUp {
    try {
        $c = New-Object Net.Sockets.TcpClient
        $ar = $c.BeginConnect('192.168.35.22', 445, $null, $null)
        $ok = $ar.AsyncWaitHandle.WaitOne(1500) -and $c.Connected
        $c.Close(); return [bool]$ok
    } catch { return $false }
}
function Send-Report {
    try {
        $dst = Join-Path $NasDir '보고'
        if (-not (Test-NasUp) -or -not (Test-Path $NasDir)) { if (-not $script:NasLogged) { $script:NasLogged = $true; Log 'NAS 에 닿지 않아 보고를 못 올립니다 (판올림은 GitHub 로 받습니다)' }; return }
        New-Item -ItemType Directory -Path $dst -Force | Out-Null
        foreach ($n in 'watch.log', 'inventory.txt') {
            $s = Join-Path $Dir $n; if (Test-Path $s) { Copy-Item $s (Join-Path $dst "음주PC_$n") -Force }
        }
        Set-Content -Path (Join-Path $dst '음주PC_살아있음.txt') -Value ("{0} v{1}" -f (Get-Date -Format 'MM-dd HH:mm:ss'), $VERSION) -Encoding UTF8
    } catch { }
}

# 스스로 판올림: GitHub 에서, 안 되면 NAS 에서 더 높은 판을 받아 바꾸고 끝낸다 (run.vbs 가 새것으로 다시 띄운다).
function Get-Ver($text) { if ($text -match "\`$VERSION\s*=\s*'(\d+)\.(\d+)\.(\d+)'") { return [Version]"$($Matches[1]).$($Matches[2]).$($Matches[3])" } return [Version]'0.0.0' }
function Update-Self {
    $new = $null
    try {
        $b = (Invoke-WebRequest -Uri ($GitUrl + '?t=' + [DateTime]::Now.Ticks) -UseBasicParsing -TimeoutSec 4).Content
        if ($b -is [byte[]]) { $new = [Text.Encoding]::UTF8.GetString($b) } else { $new = [string]$b }
    } catch { }
    if (-not $new -and (Test-NasUp)) { try { $p = Join-Path $NasDir 'watch.ps1'; if (Test-Path $p) { $new = [IO.File]::ReadAllText($p, [Text.Encoding]::UTF8) } } catch { } }
    if (-not $new) { return }
    $new = $new.TrimStart([char]0xFEFF)
    if ((Get-Ver $new) -le $VERSION_V) { return }
    try { [void][scriptblock]::Create($new) } catch { Log "새 판이 읽히지 않아 건너뜀"; return }
    Copy-Item $Self (Join-Path $Dir 'watch.prev.ps1') -Force
    [IO.File]::WriteAllText($Self, $new, (New-Object Text.UTF8Encoding $true))
    Log "판올림 $VERSION → $((Get-Ver $new)) — 다시 뜹니다"
    Close-Alarm; $mutex.ReleaseMutex(); exit 0
}
$VERSION_V = [Version]$VERSION

# 시험 경보: GitHub 의 demo.txt 내용이 지난번과 다르면 화면 경보를 한 번 띄운다 (실제 측정 없이 경보가 보이는지 원격으로 확인).
# 처음 켠 때는 지금 내용을 기억만 하고 띄우지 않는다.
function Test-Demo {
    try {
        $b = (Invoke-WebRequest -Uri (($GitUrl -replace 'watch\.ps1$', 'demo.txt') + '?t=' + [DateTime]::Now.Ticks) -UseBasicParsing -TimeoutSec 4).Content
        $cur = ([string]$b).Trim().TrimStart([char]0xFEFF)
    } catch { return }
    $f = Join-Path $Dir 'demo-last.txt'
    $last = $null; if (Test-Path $f) { $last = (Get-Content $f -Raw -Encoding UTF8).Trim() }
    if ($cur -eq $last) { return }
    Set-Content -Path $f -Value $cur -Encoding UTF8
    if ($null -eq $last) { return }
    Show-Alarm ([pscustomobject]@{ Name = '시험'; Empid = 'demo'; Count = 0; Why = '원격 시험 경보'
        Text = "시험 경보입니다`r`n이 창이 보이면 정상입니다"; Say = '시험 경보입니다. 이 소리가 들리면 정상입니다.' })
}

# 끄기 쪽지: NAS 에 STOP 파일이 있으면 시작프로그램을 지우고 끝낸다 (자리에 못 가도 끌 수 있게).
function Test-Stop {
    try {
        if ((Test-NasUp) -and (Test-Path (Join-Path $NasDir 'STOP'))) {
            Remove-Item (Join-Path ([Environment]::GetFolderPath('Startup')) 'AlcoholWatch.vbs') -Force -ErrorAction SilentlyContinue
            Log 'STOP 쪽지를 보고 시작프로그램을 지우고 끝냅니다'
            Close-Alarm; $mutex.ReleaseMutex(); Stop-Process -Name wscript -ErrorAction SilentlyContinue; exit 0
        }
    } catch { }
}

# ── 증거 모으기 ──────────────────────────────────────────────────────────────
# 측정이 진행 중인 동안(카드 뒤 90초 안, 결과 없음) 화면을 1초마다 작게 저장하고, 끝난 뒤 6초까지 더 저장한다.
# → 정상 측정과 '안전운전하세요' 전에 끊긴 측정의 화면을 비교해 원인을 찾는다. 읽기 전용, 측정 프로그램은 건드리지 않는다.
Add-Type -TypeDefinition @"
using System; using System.Runtime.InteropServices; using System.Text;
public static class FgWin {
  [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  public static string Title() { var s = new StringBuilder(256); GetWindowText(GetForegroundWindow(), s, 256); return s.ToString(); }
}
"@
$ShotDir = Join-Path $Dir 'shots'
$script:ShotCount = 0; $script:ShotUntil = [DateTime]::MinValue
function Save-Shot {
    try {
        New-Item -ItemType Directory $ShotDir -Force | Out-Null
        $b = [Windows.Forms.SystemInformation]::VirtualScreen
        $bmp = New-Object Drawing.Bitmap($b.Width, $b.Height)
        $g = [Drawing.Graphics]::FromImage($bmp); $g.CopyFromScreen($b.Left, $b.Top, 0, 0, $bmp.Size); $g.Dispose()
        $small = New-Object Drawing.Bitmap($bmp, [int]($b.Width / 2), [int]($b.Height / 2))
        $enc = [Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() | Where-Object { $_.MimeType -eq 'image/jpeg' }
        $ep = New-Object Drawing.Imaging.EncoderParameters(1)
        $ep.Param[0] = New-Object Drawing.Imaging.EncoderParameter([Drawing.Imaging.Encoder]::Quality, [long]60)
        $name = (Get-Date -Format 'MMdd_HHmmss_f') + '.jpg'
        $small.Save((Join-Path $ShotDir $name), $enc, $ep); $small.Dispose(); $bmp.Dispose()
        $script:ShotCount++
        if ($script:ShotCount % 100 -eq 0) {      # 오래된 것부터 지운다 (900장을 넘기면 300장)
            $all = @(Get-ChildItem $ShotDir -Filter *.jpg | Sort-Object Name)
            if ($all.Count -gt 900) { $all | Select-Object -First 300 | Remove-Item -Force -ErrorAction SilentlyContinue }
        }
        return $name
    } catch { return $null }
}
# 프로그램이 지금 화면에 쓰고 있는 글(예: '측정대기중...', '음주측정기 준비중...', '측정기에 불어주세요.')을 UI Automation 으로 읽는다. 읽기만 한다.
try { Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes } catch { }
$script:UiTreeDone = $false; $script:UiLastAt = [DateTime]::MinValue; $script:UiLastText = ''
function Get-UiTexts {
    try {
        $p = Get-Process -Name 'Wellcom.Alcohol.Kendo.Winform' -ErrorAction Stop | Select-Object -First 1
        $cond = New-Object Windows.Automation.PropertyCondition([Windows.Automation.AutomationElement]::ProcessIdProperty, $p.Id)
        $win = [Windows.Automation.AutomationElement]::RootElement.FindFirst('Children', $cond)
        if (-not $win) { return '(창 없음)' }
        $all = $win.FindAll('Descendants', [Windows.Automation.Condition]::TrueCondition)
        if (-not $script:UiTreeDone) {     # 처음 한 번, 어떤 요소가 읽히는지 전체를 남긴다 (/ui-tree.txt)
            $script:UiTreeDone = $true
            $o = foreach ($e in $all) { $c = $e.Current; "{0}`t{1}`t{2}`t{3}" -f $c.ControlType.ProgrammaticName, $c.AutomationId, $c.ClassName, $c.Name }
            [IO.File]::WriteAllLines((Join-Path $Dir 'ui-tree.txt'), @("창: $($win.Current.Name)  요소 $($all.Count)개") + @($o), (New-Object Text.UTF8Encoding $true))
        }
        $t = foreach ($e in $all) { $n = $e.Current.Name; if ($n -and $n.Length -le 40) { $n } }
        return (@($t | Select-Object -Unique) -join ' | ')
    } catch { return "(읽기 실패: $($_.Exception.Message))" }
}
function Get-Age($r, $nowUtc) {
    try { return ($nowUtc - [DateTime]::ParseExact(([string]$r.createdate).Substring(0, 19), 'yyyy-MM-ddTHH:mm:ss', [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::AssumeUniversal -bor [Globalization.DateTimeStyles]::AdjustToUniversal)).TotalSeconds } catch { return 9999 }
}
function Record-Session($rows, $photos, $nowUtc) {
    $act = @($rows | Where-Object { $Done -notcontains ([string]$_.result).Trim() -and (Get-Age $_ $nowUtc) -le $MaxAge })
    if ($act.Count -gt 0) { $script:ShotUntil = (Get-Date).AddSeconds(6) }
    if ($act.Count -eq 0 -and (Get-Date) -gt $script:ShotUntil) { return }
    $name = Save-Shot
    $ui = $script:UiLastText
    if (((Get-Date) - $script:UiLastAt).TotalSeconds -ge 2) { $script:UiLastAt = Get-Date; $ui = Get-UiTexts; $script:UiLastText = $ui }
    $who = ($rows | Where-Object { (Get-Age $_ $nowUtc) -le $MaxAge } | ForEach-Object { "$($_.empname)#$($_.count)=$(([string]$_.result).Trim())[" + ((@($photos["$($_.empid)|$($_.count)"])) -join ',') + "]" }) -join ' '
    Add-Content -Path (Join-Path $Dir 'session.log') -Encoding UTF8 -Value ("{0} 화면={1} 앞창='{2}' 화면문구=[{3}] {4}" -f (Get-Date -Format 'MM-dd HH:mm:ss.f'), $name, [FgWin]::Title(), $ui, $who)
}

# ── 내보내기: 정해진 PC(B)만, 정해진 파일만, 읽기 전용 ─────────────────────────
$Allow = @('192.168.35.99', '127.0.0.1')
$ExportPort = 8765
if ($env:ALCOHOL_TEST_PORT) { $ExportPort = [int]$env:ALCOHOL_TEST_PORT }
$AppLogDir = if ($env:ALCOHOL_TEST_APPLOG) { $env:ALCOHOL_TEST_APPLOG } else { 'C:\Wellcomsnt\Wellcom.Alcohol.Kendo.Winform\Log' }   # 측정 프로그램 자신의 로그(읽기만)
$script:Srv = $null
try { $script:Srv = New-Object Net.Sockets.TcpListener([Net.IPAddress]::Any, $ExportPort); $script:Srv.Start() }
catch { Log "내보내기 포트 $ExportPort 를 못 엶: $($_.Exception.Message)"; $script:Srv = $null }
if ($script:Srv -and -not $env:ALCOHOL_TEST_PORT) {
    try {   # 방화벽 규칙(관리자일 때만 되고, 아니면 말없이 넘어간다)
        $out = netsh advfirewall firewall add rule name=AlcoholWatch dir=in action=allow protocol=TCP localport=$ExportPort remoteip=192.168.35.99 2>&1 | Out-String
        Log ("방화벽 규칙: " + $out.Trim())
    } catch { }
}
function Send-Http($c, $code, $ctype, [byte[]]$body) {
    $head = [Text.Encoding]::ASCII.GetBytes("HTTP/1.1 $code OK`r`nContent-Type: $ctype`r`nContent-Length: $($body.Length)`r`nConnection: close`r`n`r`n")
    $ns = $c.GetStream(); $ns.Write($head, 0, $head.Length); $ns.Write($body, 0, $body.Length); $ns.Flush()
}
function Read-Shared($path) {
    $fs = [IO.File]::Open($path, 'Open', 'Read', 'ReadWrite'); try { $ms = New-Object IO.MemoryStream; $fs.CopyTo($ms); return $ms.ToArray() } finally { $fs.Dispose() }
}
function Serve-One {
    if (-not $script:Srv -or -not $script:Srv.Pending()) { return }
    $c = $script:Srv.AcceptTcpClient()
    try {
        $ip = $c.Client.RemoteEndPoint.Address.ToString()
        $c.ReceiveTimeout = 2000
        $buf = New-Object byte[] 2048; $n = $c.GetStream().Read($buf, 0, 2048)
        $path = ([Text.Encoding]::ASCII.GetString($buf, 0, $n) -split ' ')[1]
        $txt = 'text/plain; charset=utf-8'
        if ($Allow -notcontains $ip) { Send-Http $c 403 $txt ([Text.Encoding]::UTF8.GetBytes('forbidden')) }
        elseif ($path -eq '/') {
            $list = @('inventory.txt', 'watch.log', 'session.log', 'alerts.log', 'ui-tree.txt') + @(Get-ChildItem $AppLogDir -Filter 'ManagementApp.*.log' -ErrorAction SilentlyContinue | Sort-Object Name | Select-Object -Last 4 | ForEach-Object { 'app/' + $_.Name }) + @(Get-ChildItem $ShotDir -Filter *.jpg -ErrorAction SilentlyContinue | Sort-Object Name | Select-Object -Last 300 | ForEach-Object { 'shots/' + $_.Name })
            Send-Http $c 200 $txt ([Text.Encoding]::UTF8.GetBytes(("v$VERSION`n" + ($list -join "`n"))))
        }
        elseif ($path -in '/inventory.txt', '/watch.log', '/session.log', '/alerts.log', '/ui-tree.txt' -and (Test-Path (Join-Path $Dir $path.TrimStart('/')))) {
            Send-Http $c 200 $txt (Read-Shared (Join-Path $Dir $path.TrimStart('/')))
        }
        elseif ($path -match '^/app/(ManagementApp\.\d{8}\.log)$' -and (Test-Path (Join-Path $AppLogDir $Matches[1]))) {
            Send-Http $c 200 $txt (Read-Shared (Join-Path $AppLogDir $Matches[1]))
        }
        elseif ($path -match '^/shots/([0-9_]+\.jpg)$' -and (Test-Path (Join-Path $ShotDir $Matches[1]))) {
            Send-Http $c 200 'image/jpeg' (Read-Shared (Join-Path $ShotDir $Matches[1]))
        }
        else { Send-Http $c 404 $txt ([Text.Encoding]::UTF8.GetBytes('not found')) }
    } catch { } finally { try { $c.Close() } catch { } }
}

# ── 본 반복 ──────────────────────────────────────────────────────────────────
Log "시작 v$VERSION"
$st = @{ Click = @{}; Told = @{} }
$lastUpd = [DateTime]::MinValue; $lastInv = [DateTime]::MinValue; $lastRep = [DateTime]::MinValue; $lastLog = $true
while ($true) {
    $now = Get-Date
    if (($now - $lastInv).TotalMinutes -ge 360) { $lastInv = $now; Start-Inventory }
    if (($now - $lastRep).TotalMinutes -ge 5) { $lastRep = $now; Send-Report }
    if (($now - $lastUpd).TotalMinutes -ge 5 -and -not $script:Alarm) { $lastUpd = $now; Test-Stop; Test-Demo; Update-Self }
    try {
        $today = $now.ToString('yyyyMMdd')
        $raw = @(Get-Api "/btest/admin/$today/$today")
        if (-not $lastLog) { Log '서버 다시 연결됨'; $lastLog = $true }
        $seen = @{}
        foreach ($r in $raw) { $k = "$($r.empid)|$($r.count)"; if (-not $seen.ContainsKey($k) -or [string]$r.modificationdate -gt [string]$seen[$k].modificationdate) { $seen[$k] = $r } }
        $rows = @($seen.Values)
        $photos = @{}
        $nowUtc = $now.ToUniversalTime()
        foreach ($r in $rows) {
            $res = ([string]$r.result).Trim()
            if ($Done -contains $res) { continue }
            try {
                $list = @(Get-Api ("/btest/getFile/{0}/{1}/{2}/{3}/{4}" -f $script:Cp, $r.date, $r.empid, $r.officecode, $r.count))
                $photos["$($r.empid)|$($r.count)"] = @($list | ForEach-Object { [string]$_.type })
            } catch { }
        }
        Record-Session $rows $photos $nowUtc
        foreach ($a in (Get-Alarms $rows $photos $nowUtc $st)) { if (((Get-Date) - $script:LogAlarmAt).TotalSeconds -gt 60) { Show-Alarm $a } }
        # 경보를 끌 때: 시간이 다 됐거나, 그 사람이 결과를 받았거나 다시 찍었다
        if ($script:Alarm) {
            $x = $script:Alarm
            $mine = @($rows | Where-Object { [string]$_.empid -eq $x.Empid })
            $newer = $mine | Where-Object { [int]$_.count -gt $x.Count }
            $got = $mine | Where-Object { [int]$_.count -eq $x.Count -and $Done -contains ([string]$_.result).Trim() }
            if ((Get-Date) -gt $x.Until -or $newer -or $got) { Close-Alarm }
        }
        # 하루가 바뀌면 상태를 비운다
        if ($st.Day -ne $today) { $st.Day = $today; $st.Click = @{}; $st.Told = @{} }
    } catch {
        if ($lastLog) { Log "서버 조회 실패: $($_.Exception.Message)"; $lastLog = $false }
        Pump 5
    }
    Pump 1
}
