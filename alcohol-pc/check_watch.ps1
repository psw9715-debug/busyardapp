# 끊김 판정 시험 — 실패하는지 먼저 보고, 통과해야 배포한다.  powershell -NoProfile -ExecutionPolicy Bypass -File alcohol-pc\check_watch.ps1
. (Join-Path $PSScriptRoot 'watch.ps1') -NoRun
$fail = 0
function Expect($name, $cond) { if ($cond) { "ok   $name" } else { "FAIL $name"; $script:fail++ } }
function Row($emp, $cnt, $res, $ageSec, $now) {
    [pscustomobject]@{ empid = $emp; count = "$cnt"; result = $res; empname = "이름$emp"
        createdate = $now.AddSeconds(-$ageSec).ToString('yyyy-MM-ddTHH:mm:ss') + '.000+0000' }
}
$now = [DateTime]::UtcNow
function NewSt { @{ Click = @{}; Told = @{} } }

# 1) 찰칵 뒤 13초 넘게 완료 없음 → 알림
$st = NewSt; $rows = @(Row 'a' 1 'R' 20 $now); $ph = @{ 'a|1' = @('로그인') }
[void](Get-Alarms $rows $ph $now.AddSeconds(-14) $st)        # 14초 전에 찰칵을 처음 봤다고 친다
Expect '찰칵 13초 지나 완료 없음 → 알림' ((Get-Alarms $rows $ph $now $st).Count -eq 1)
Expect '같은 회차는 두 번 알리지 않음'   ((Get-Alarms $rows $ph $now $st).Count -eq 0)

# 2) 정상: 찰칵 뒤 측정완료 사진이 나옴 → 알리지 않음
$st = NewSt; $ph = @{ 'a|1' = @('로그인', '측정완료') }
[void](Get-Alarms $rows $ph $now.AddSeconds(-14) $st)
Expect '측정완료 사진 있으면 조용' ((Get-Alarms $rows $ph $now $st).Count -eq 0)

# 3) 정상: 결과 Y
$st = NewSt; $ph = @{ 'a|1' = @('로그인') }
[void](Get-Alarms @(Row 'a' 1 'R' 20 $now) $ph $now.AddSeconds(-14) $st)
Expect '결과 Y 면 조용' ((Get-Alarms @(Row 'a' 1 'Y' 20 $now) $ph $now $st).Count -eq 0)

# 4) 아직 13초 안 됨 → 조용 (오래 부는 정상 사람에게 울리면 안 된다)
$st = NewSt; $ph = @{ 'a|1' = @('로그인') }
[void](Get-Alarms $rows $ph $now.AddSeconds(-5) $st)
Expect '찰칵 5초 전이면 조용' ((Get-Alarms $rows $ph $now $st).Count -eq 0)

# 5) 이미 다시 찍음(2회차 있음) → 1회차는 알리지 않음
$st = NewSt; $ph = @{ 'a|1' = @('로그인') }
$rows2 = @((Row 'a' 1 'R' 30 $now), (Row 'a' 2 'R' 3 $now))
[void](Get-Alarms $rows2 $ph $now.AddSeconds(-14) $st)
Expect '다시 찍었으면 1회차는 조용' ((Get-Alarms $rows2 $ph $now $st).Count -eq 0)

# 6) 찰칵이 아예 없이 음악만(에러 A) → 알리지 않음 (카드를 다시 찍으면 됨)
$st = NewSt
Expect '찰칵 없음(에러 A)은 조용' ((Get-Alarms @(Row 'a' 1 'R' 40 $now) @{} $now $st).Count -eq 0)

# 7) 미측정 사진 → 즉시 알림
$st = NewSt
Expect "'미측정' 이면 즉시 알림" ((Get-Alarms @(Row 'a' 1 'R' 10 $now) @{ 'a|1' = @('로그인', '미측정') } $now $st).Count -eq 1)

# 8) 켤 때 몰려온 오래된 회차(90초 넘음) → 조용
$st = NewSt; $ph = @{ 'a|1' = @('로그인') }
[void](Get-Alarms @(Row 'a' 1 'R' 200 $now) $ph $now.AddSeconds(-14) $st)
Expect '90초 지난 옛 회차는 조용' ((Get-Alarms @(Row 'a' 1 'R' 200 $now) $ph $now $st).Count -eq 0)

# 9) 측정 프로그램 로그 즉시 판정 (2026-11-13 실제 로그 모양)
function Run-Log($lines) { $st = @{ Pending = $false; Fired = $false }; $o = @(); foreach ($l in $lines) { $r = Step-AppLog $l $st; if ($r -and $r -ne 'NEW') { $o += $r } }; return , $o }
$ready = 'bytes6 05 readySoundPlayRunFlag SoundPlay.Ready bytes6 :'
Expect '정상(찰칵→측정완료→닫힘)은 조용'   ((Run-Log @($ready, '로그인캡처 끝', '측정완료캡처 시작', 'Close MainWindow')).Count -eq 0)
Expect '찰칵 뒤 0x81 에러 → 즉시 경보'      ((Run-Log @($ready, '로그인캡처 끝', '0x81 음주측정기 에러 bytes25 :', 'Close MainWindow')).Count -eq 1)
Expect '찰칵 뒤 완료 없이 창 닫힘 → 경보'   ((Run-Log @($ready, '로그인캡처 끝', 'close click', 'Close MainWindow')).Count -eq 1)
Expect '에러 뒤 닫힘은 두 번 울리지 않음'   ((Run-Log @($ready, '로그인캡처 끝', '0x81 음주측정기 에러 bytes25 :', 'Close MainWindow')).Count -eq 1)
Expect '찰칵 전(준비 중) 에러·닫힘은 조용'  ((Run-Log @($ready, '0x81 음주측정기 에러 bytes25 :', 'Close MainWindow')).Count -eq 0)

Expect '미측정캡처는 창이 닫히기 전에 경보'  ((Run-Log @($ready, '로그인캡처 끝', '미측정캡처 시작')).Count -eq 1)
Expect '미측정 뒤 닫힘은 두 번 울리지 않음'  ((Run-Log @($ready, '로그인캡처 끝', '미측정캡처 시작', '미측정캡처 끝', 'Close MainWindow')).Count -eq 1)
# 10) 닿지 않는 NAS 를 확인해도 2.5초 안에 돌아와야 한다 (경보가 같이 멈추면 안 된다 — 11-14 04:16 에 3분 늦은 일)
$sw = [Diagnostics.Stopwatch]::StartNew()
$c = New-Object Net.Sockets.TcpClient; $ar = $c.BeginConnect('192.168.35.250', 445, $null, $null); [void]$ar.AsyncWaitHandle.WaitOne(1500); $c.Close()
Expect '닿지 않는 주소 확인이 2.5초 안에 끝남' ($sw.Elapsed.TotalSeconds -lt 2.5)

# 11) 깨진 이름 복구 (서버가 UTF-8 을 Latin-1 로 읽히게 보낼 때)
$garbled = [Text.Encoding]::GetEncoding(28591).GetString([Text.Encoding]::UTF8.GetBytes('이헌진'))
Expect '깨진 이름을 되돌림'            ((Fix-Name $garbled) -eq '이헌진')
Expect '멀쩡한 이름은 그대로'          ((Fix-Name '이헌진') -eq '이헌진')

# 10) 화면 문구로 판정: '측정대기중...' 이 10초 넘게 그대로면 한 번만
$t0 = Get-Date; $ss = @{ StallSince = $null; StallFired = $false }
Expect '대기중 처음 봄 → 조용'             ($null -eq (Step-Stall '측정대기중...' $t0 $ss))
Expect '대기중 4초 → 조용'                 ($null -eq (Step-Stall '측정대기중...' $t0.AddSeconds(4) $ss))
Expect '대기중 5초 그대로 → 경보'          ($null -ne (Step-Stall '금일측정정보 | 측정대기중...' $t0.AddSeconds(5) $ss))
Expect '같은 멈춤은 두 번 알리지 않음'     ($null -eq (Step-Stall '측정대기중...' $t0.AddSeconds(20) $ss))
$ss = @{ StallSince = $null; StallFired = $false }
[void](Step-Stall '측정대기중...' $t0 $ss)
Expect '8초 뒤 불어주세요로 바뀌면 조용'   ($null -eq (Step-Stall '측정기에 불어주세요.' $t0.AddSeconds(8) $ss))
Expect '바뀐 뒤 다시 대기중이면 처음부터'  ($null -eq (Step-Stall '측정대기중...' $t0.AddSeconds(12) $ss) -and $null -eq (Step-Stall '측정대기중...' $t0.AddSeconds(14) $ss))

# 11) '측정기에 불어주세요.' 가 18초 넘게 그대로 (정현철 1차)
$bs = @{ StallSince = $null; StallFired = $false }; $b0 = Get-Date
Expect '불어주세요 처음 봄 → 조용'              ($null -eq (Step-Stall '측정기에 불어주세요.' $b0 $bs '불어주세요' 18 'x'))
Expect '불어주세요 11초(정상 중 가장 긴 것) → 조용' ($null -eq (Step-Stall '측정기에 불어주세요.' $b0.AddSeconds(11) $bs '불어주세요' 18 'x'))
Expect '불어주세요 18초 그대로 → 경보'          ((Step-Stall '측정기에 불어주세요.' $b0.AddSeconds(18) $bs '불어주세요' 18 'x') -eq 'x')
Expect '같은 멈춤은 두 번 알리지 않음'          ($null -eq (Step-Stall '측정기에 불어주세요.' $b0.AddSeconds(30) $bs '불어주세요' 18 'x'))
$bs = @{ StallSince = $null; StallFired = $false }
[void](Step-Stall '측정기에 불어주세요.' $b0 $bs '불어주세요' 18 'x')
Expect '15초 뒤 측정중으로 바뀌면 조용'         ($null -eq (Step-Stall '측정중.' $b0.AddSeconds(15) $bs '불어주세요' 18 'x'))

# 12) 사이렌(삐뽀삐뽀) WAV — 1초, 올바른 WAV 머리
$sw = New-SirenBytes
Expect '사이렌은 RIFF/WAVE 머리를 가진다'      ([Text.Encoding]::ASCII.GetString($sw, 0, 4) -eq 'RIFF' -and [Text.Encoding]::ASCII.GetString($sw, 8, 4) -eq 'WAVE')
Expect '사이렌 길이 약 1초(0.25초×4음, 22050Hz·16비트·모노)' ($sw.Length -eq 44 + 4 * [int](22050 * 0.25) * 2)
Expect '사이렌은 소리가 있다(전부 0이 아님)'     ((($sw[100..400] | Measure-Object -Maximum).Maximum) -gt 0)

# 13) 무한 음악이 안 풀리면 15초마다 다시, 최대 3번 (자리를 비운 사이)
$rs = @{ StallSince = $null; StallFired = $false }; $r0 = Get-Date; $m = "x"
[void](Step-Stall '측정대기중...' $r0 $rs '측정대기중' 5 $m 15 3)
Expect '5초에 첫 안내'                        ((Step-Stall '측정대기중...' $r0.AddSeconds(5) $rs '측정대기중' 5 $m 15 3) -eq $m)
Expect '그 뒤 14초 안엔 다시 안 한다'         ($null -eq (Step-Stall '측정대기중...' $r0.AddSeconds(18) $rs '측정대기중' 5 $m 15 3))
Expect '15초 지나면 한 번 더'                 ((Step-Stall '측정대기중...' $r0.AddSeconds(20) $rs '측정대기중' 5 $m 15 3) -eq $m)
Expect '또 15초 지나면 세 번째'               ((Step-Stall '측정대기중...' $r0.AddSeconds(35) $rs '측정대기중' 5 $m 15 3) -eq $m)
Expect '세 번이 끝이다(네 번째는 없음)'       ($null -eq (Step-Stall '측정대기중...' $r0.AddSeconds(60) $rs '측정대기중' 5 $m 15 3))
[void](Step-Stall '측정기에 불어주세요.' $r0.AddSeconds(61) $rs '측정대기중' 5 $m 15 3)
[void](Step-Stall '측정대기중...' $r0.AddSeconds(62) $rs '측정대기중' 5 $m 15 3)
Expect '풀렸다가 또 멈추면 처음부터 다시 센다' ((Step-Stall '측정대기중...' $r0.AddSeconds(67) $rs '측정대기중' 5 $m 15 3) -eq $m)

# 14) 창 닫기 도구 — 진짜 창으로 (닫을 창·두고 볼 창)
Add-Type -AssemblyName System.Windows.Forms
$me = (Get-Process -Id $PID).ProcessName
$fa = New-Object Windows.Forms.Form; $fa.Text = 'main'; $fa.ShowInTaskbar = $false; $fa.Opacity = 0; $fa.Show()
$fb = New-Object Windows.Forms.Form; $fb.Text = '음주측정시스템'; $fb.ShowInTaskbar = $false; $fb.Opacity = 0; $fb.Show()
[Windows.Forms.Application]::DoEvents()
Expect '다른 프로세스 이름이면 아무것도 닫지 않는다' ([WinClose]::CloseByTitle('없는프로세스', 'main') -eq 0)
Expect "제목이 'main' 인 창 하나를 닫는다"           ([WinClose]::CloseByTitle($me, 'main') -eq 1)
for ($k = 0; $k -lt 20; $k++) { [Windows.Forms.Application]::DoEvents(); Start-Sleep -Milliseconds 25 }
Expect "닫힌 창은 사라졌다 (사람이 X 를 누른 것처럼)" ($fa.IsDisposed)
Expect "제목이 다른 창('음주측정시스템')은 그대로"   (-not $fb.IsDisposed -and $fb.Visible)
Expect '이미 닫혔으면 더 닫을 것이 없다'             ([WinClose]::CloseByTitle($me, 'main') -eq 0)
$fb.Close(); $fb.Dispose()

# 15) 무한 음악 = 찰칵 뒤 준비 신호(06)를 못 받음 (2026-11-26 김수열)
function Wait-Of($lines) { $st = @{ Pending = $false; Fired = $false; Waiting = $false }; foreach ($l in $lines) { [void](Step-AppLog $l $st) }; return $st.Waiting }
$ready = 'bytes6 05 readySoundPlayRunFlag SoundPlay.Ready bytes6 :'
Expect '찰칵 뒤 06 이 없으면 기다리는 중'        (Wait-Of @($ready, '로그인캡처 끝'))
Expect '★ 김수열: 다시 찍으며 06 이 오면 끝'      (-not (Wait-Of @($ready, '로그인캡처 끝', '.ctor MainWindow INSTANCE', 'bytes6 06 SoundPlay.Ready')))
Expect '바로 측정완료면 기다리는 중 아님'          (-not (Wait-Of @($ready, '로그인캡처 끝', '측정완료캡처 시작')))
Expect '창이 닫히면 기다리는 중 아님'              (-not (Wait-Of @($ready, '로그인캡처 끝', 'Close MainWindow')))
Expect '새 창(05)이 열리면 다시 처음부터'          (-not (Wait-Of @($ready, '로그인캡처 끝', $ready)))
Expect '찰칵 전에는 기다리는 중 아님'              (-not (Wait-Of @($ready)))

# 16) 로그만으로 '대기중' 이라 판정해도 화면이 대기중일 때만 알린다 (2026-11-26 고성민: 정상 측정인데 로그가 늦게 적혀 오탐)
Expect '화면이 측정대기중이면 알린다'            (Confirm-Stall '체온측정 | X | 측정대기중...')
Expect '★ 이미 불어주세요 화면이면 알리지 않는다' (-not (Confirm-Stall '측정기에 불어주세요.'))
Expect '측정중이면 알리지 않는다'                (-not (Confirm-Stall '측정중.'))
Expect '안전운행 화면이면 알리지 않는다'          (-not (Confirm-Stall '안전운행하세요.'))
Expect '화면을 못 읽으면 알리지 않는다'          (-not (Confirm-Stall '(창 없음)'))

if ($fail) { "`n실패 $fail 건"; exit 1 } else { "`n모두 통과" }
