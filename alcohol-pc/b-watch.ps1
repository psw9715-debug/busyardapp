# B PC(사용자 PC) 전용: 음주측정 PC 지킴이의 alerts.log 를 2초마다 읽어, 끊김이 기록되면 내 화면을 붉게 번쩍이고 짧게 울린다.
# 읽기만 한다(음주 PC 에는 아무것도 쓰지 않는다). UTF-8 BOM 으로 저장.
# 출퇴근 관리(창 제목 '출근 현황 관리 시스템')가 떠 있을 때만 번쩍이고, 없으면 아무것도 하지 않는다.
# -WithAttendance 로 출퇴근 관리가 띄웠다면, 그 창이 1분 넘게 없을 때 스스로 끝낸다.
#   powershell -NoProfile -ExecutionPolicy Bypass -File b-watch.ps1            # 감시 시작
#   powershell -NoProfile -ExecutionPolicy Bypass -File b-watch.ps1 -Test      # 번쩍임만 한 번 보기
param([string]$Url = 'http://192.168.35.23:8765/alerts.log', [switch]$Test, [switch]$DryRun, [string]$OutFile = '',
      [string]$AttendanceTitle = '출근 현황 관리 시스템', [switch]$WithAttendance, [string]$SignalFile = '')

Add-Type -ReferencedAssemblies System.Windows.Forms, System.Drawing -TypeDefinition @"
using System; using System.Windows.Forms;
public class ClickThroughForm : Form {
  protected override bool ShowWithoutActivation { get { return true; } }
  protected override CreateParams CreateParams { get { var p = base.CreateParams; p.ExStyle |= 0x80 | 0x20 | 0x08000000 | 0x80000; return p; } }
}
"@
Add-Type -AssemblyName System.Windows.Forms, System.Drawing

Add-Type -TypeDefinition @"
using System; using System.Collections.Generic; using System.Runtime.InteropServices; using System.Text;
public static class WinTitles {
  delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc p, IntPtr l);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  public static bool Has(string part) { bool found = false; EnumWindows((h, l) => { var s = new StringBuilder(256); GetWindowText(h, s, 256); if (s.Length > 0 && s.ToString().Contains(part)) { found = true; return false; } return true; }, IntPtr.Zero); return found; }
}
"@
function Test-Attendance { return [WinTitles]::Has($AttendanceTitle) }

function Wait-Ui($ms) { $end = (Get-Date).AddMilliseconds($ms); while ((Get-Date) -lt $end) { [Windows.Forms.Application]::DoEvents(); Start-Sleep -Milliseconds 20 } }

# 붉은 번쩍임(클릭이 통과하고 포커스를 뺏지 않는다) + 가운데 글 + 짧은 소리
function Show-Flash($text, $level) {
    $color = if ($level -eq 'red') { [Drawing.Color]::Red } else { [Drawing.Color]::Gold }
    $times = if ($level -eq 'red') { 3 } else { 1 }
    $forms = foreach ($sc in [Windows.Forms.Screen]::AllScreens) {
        $f = New-Object ClickThroughForm
        $f.FormBorderStyle = 'None'; $f.StartPosition = 'Manual'; $f.Bounds = $sc.Bounds; $f.TopMost = $true; $f.ShowInTaskbar = $false
        $f.BackColor = $color; $f.Opacity = 0.55; $f
    }
    $banner = New-Object ClickThroughForm
    $banner.FormBorderStyle = 'None'; $banner.StartPosition = 'Manual'; $banner.TopMost = $true; $banner.ShowInTaskbar = $false
    $b = [Windows.Forms.Screen]::PrimaryScreen.Bounds
    $banner.Size = New-Object Drawing.Size(1100, 260); $banner.Location = New-Object Drawing.Point(($b.Left + ($b.Width - 1100) / 2), ($b.Top + 80))
    $banner.BackColor = [Drawing.Color]::Black; $banner.Opacity = 0.85
    $l = New-Object Windows.Forms.Label; $l.Dock = 'Fill'; $l.TextAlign = 'MiddleCenter'; $l.ForeColor = $color
    $l.Font = New-Object Drawing.Font('맑은 고딕', 36, [Drawing.FontStyle]::Bold); $l.Text = $(if ($level -eq 'red') { $text + "`r`n다시 음주측정을 요청하세요!" } else { $text }); $banner.Controls.Add($l)
    $banner.Show()
    for ($i = 0; $i -lt $times; $i++) {
        foreach ($f in $forms) { $f.Show() }
        if ($level -eq 'red') { [Media.SystemSounds]::Exclamation.Play(); try { [Console]::Beep(1400, 180); [Console]::Beep(1000, 180) } catch { } }
        Wait-Ui 320
        foreach ($f in $forms) { $f.Hide() }
        Wait-Ui 160
    }
    Wait-Ui $(if ($level -eq 'red') { 5000 } else { 3000 })
    $banner.Close(); $banner.Dispose(); foreach ($f in $forms) { $f.Close(); $f.Dispose() }
}

if ($Test) { Show-Flash '시험: 이헌진  음주측정기 에러' 'red'; return }

$mutex = New-Object Threading.Mutex($false, 'Local\AlcoholBWatch')
if (-not $mutex.WaitOne(0)) { return }
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch { }

# 2026-11-26 한거성: 에러가 04:32:22 에 적혔는데 이 PC 는 04:33:21 에야 번쩍였다. 왜 늦었는지 알 수 있게 이 감시의 일을 남긴다
# (읽기 실패·느린 읽기·새 경보·출퇴근 창 있음/없음). 남기는 곳: 신호 파일이 있는 log 폴더.
$LogDir = if ($SignalFile) { Split-Path -Parent $SignalFile } else { $env:TEMP }
function Note($m) { try { Add-Content -Path (Join-Path $LogDir ("b-watch_{0}.txt" -f (Get-Date -Format 'yyyyMMdd'))) -Value ("{0} {1}" -f (Get-Date -Format 'HH:mm:ss.f'), $m) -Encoding UTF8 } catch { } }

function Get-Lines {
    # Invoke-WebRequest 는 윈도우 프록시 자동 찾기를 거쳐 가끔 느려질 수 있어, 프록시 없이 곧장 묻는다.
    $t0 = Get-Date
    try {
        $req = [Net.HttpWebRequest]::Create($Url); $req.Proxy = $null; $req.KeepAlive = $false; $req.Timeout = 5000; $req.ReadWriteTimeout = 5000
        $res = $req.GetResponse()
        $sr = New-Object IO.StreamReader($res.GetResponseStream(), [Text.Encoding]::UTF8)
        $c = $sr.ReadToEnd(); $sr.Close(); $res.Close()
        $ms = ((Get-Date) - $t0).TotalMilliseconds
        if ($ms -gt 2000) { Note ("느린 읽기 {0:n0}ms" -f $ms) }
    }
    catch {
        $e = $_.Exception.InnerException; if (-not $e) { $e = $_.Exception }
        if ($e.Response -and [int]$e.Response.StatusCode -eq 404) { return @() }   # 404 = 아직 기록 없음
        Note ("읽기 실패 {0:n0}ms {1}" -f ((Get-Date) - $t0).TotalMilliseconds, $e.Message); return $null
    }
    return @(([string]$c).TrimStart([char]0xFEFF).Split("`n") | ForEach-Object { $_.TrimEnd("`r") } | Where-Object { $_.Trim() })
}

$seen = -1   # 시작할 때 이미 있는 줄은 울리지 않는다
$absentSince = $null
while ($true) {
    $있다 = Test-Attendance
    if ($script:앞창 -ne $있다) { $script:앞창 = $있다; Note $(if ($있다) { '출퇴근 관리 창 있음 — 감시' } else { '출퇴근 관리 창 없음 — 쉼' }) }
    if (-not $있다) {
        $seen = -1      # 출퇴근 관리가 꺼진 동안의 기록은 울리지 않는다(다시 켜질 때 지금 줄 수에서 다시 시작)
        if (-not $absentSince) { $absentSince = Get-Date }
        if ($WithAttendance -and ((Get-Date) - $absentSince).TotalSeconds -gt 60) { return }
        if ($DryRun) { Start-Sleep -Milliseconds 1000 } else { Wait-Ui 2000 }
        continue
    }
    $absentSince = $null
    $lines = Get-Lines
    if ($null -ne $lines) {
        if ($seen -lt 0 -or $lines.Count -lt $seen) { $seen = $lines.Count }
        elseif ($lines.Count -gt $seen) {
            foreach ($ln in $lines[$seen..($lines.Count - 1)]) {
                $m = [regex]::Match($ln, '^(\d\d-\d\d \d\d:\d\d:\d\d)\s+(.*?)\s*측정 프로그램 로그:\s*(.+)$')
                if (-not $m.Success) { continue }
                $name = $m.Groups[2].Value.Trim(); $why = $m.Groups[3].Value.Trim()
                $level = if ($why -match '에러|닫혔|멈췄') { 'red' } elseif ($why -match '미측정') { 'yellow' } else { $null }
                if (-not $level) { continue }
                Note ("새 경보: $ln")
                $prefix = if ($name) { "$name  " } else { '' }
                $kind = if ($why -match '에러') { '음주측정기 에러' } elseif ($why -match '불어주세요') { '불어주세요 화면에서 멈춤(불었는데 안 넘어감)' } elseif ($why -match '멈췄') { '측정대기중에서 멈춤(불어주세요 안 나옴)' } elseif ($why -match '닫혔') { '측정이 끝나지 못하고 닫힘' } else { '미측정' }
                $text = $prefix + $kind
                if ($level -eq 'red' -and $SignalFile -and -not $DryRun) { try { Set-Content -Path $SignalFile -Value (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') -Encoding UTF8 } catch { } }
                if ($DryRun) { Add-Content -Path $OutFile -Value ("{0:HH:mm:ss.fff} [{1}] {2}" -f (Get-Date), $level, $text) -Encoding UTF8 } else { Show-Flash $text $level }
            }
            $seen = $lines.Count
        }
    }
    if ($DryRun) { Start-Sleep -Milliseconds 500 } else { Wait-Ui 1000 }
}
