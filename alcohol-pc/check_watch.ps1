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

if ($fail) { "`n실패 $fail 건"; exit 1 } else { "`n모두 통과" }
