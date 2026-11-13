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

if ($fail) { "`n실패 $fail 건"; exit 1 } else { "`n모두 통과" }
