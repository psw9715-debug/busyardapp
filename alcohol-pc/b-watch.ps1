# B PC(사용자 PC) 전용: 음주측정 PC 지킴이의 alerts.log 를 2초마다 읽어, 끊김이 기록되면 내 화면을 붉게 번쩍이고 짧게 울린다.
# 읽기만 한다(음주 PC 에는 아무것도 쓰지 않는다). UTF-8 BOM 으로 저장.
#   powershell -NoProfile -ExecutionPolicy Bypass -File b-watch.ps1            # 감시 시작
#   powershell -NoProfile -ExecutionPolicy Bypass -File b-watch.ps1 -Test      # 번쩍임만 한 번 보기
param([string]$Url = 'http://192.168.35.23:8765/alerts.log', [switch]$Test, [switch]$DryRun, [string]$OutFile = '')

Add-Type -ReferencedAssemblies System.Windows.Forms, System.Drawing -TypeDefinition @"
using System; using System.Windows.Forms;
public class ClickThroughForm : Form {
  protected override bool ShowWithoutActivation { get { return true; } }
  protected override CreateParams CreateParams { get { var p = base.CreateParams; p.ExStyle |= 0x80 | 0x20 | 0x08000000 | 0x80000; return p; } }
}
"@
Add-Type -AssemblyName System.Windows.Forms, System.Drawing

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
    $banner.Size = New-Object Drawing.Size(900, 160); $banner.Location = New-Object Drawing.Point(($b.Left + ($b.Width - 900) / 2), ($b.Top + 80))
    $banner.BackColor = [Drawing.Color]::Black; $banner.Opacity = 0.85
    $l = New-Object Windows.Forms.Label; $l.Dock = 'Fill'; $l.TextAlign = 'MiddleCenter'; $l.ForeColor = $color
    $l.Font = New-Object Drawing.Font('맑은 고딕', 28, [Drawing.FontStyle]::Bold); $l.Text = $text; $banner.Controls.Add($l)
    $banner.Show()
    for ($i = 0; $i -lt $times; $i++) {
        foreach ($f in $forms) { $f.Show() }
        if ($level -eq 'red') { [Media.SystemSounds]::Exclamation.Play() }
        Wait-Ui 260
        foreach ($f in $forms) { $f.Hide() }
        Wait-Ui 160
    }
    Wait-Ui 3500
    $banner.Close(); $banner.Dispose(); foreach ($f in $forms) { $f.Close(); $f.Dispose() }
}

if ($Test) { Show-Flash '시험: 이헌진  음주측정기 에러' 'red'; return }

$mutex = New-Object Threading.Mutex($false, 'Local\AlcoholBWatch')
if (-not $mutex.WaitOne(0)) { return }
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch { }

function Get-Lines {
    try { $c = (Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3).Content }
    catch { if ($_.Exception.Response -and [int]$_.Exception.Response.StatusCode -eq 404) { return @() } ; return $null }   # 404 = 아직 기록 없음, 그 밖의 실패 = 못 읽음
    return @(([string]$c).TrimStart([char]0xFEFF).Split("`n") | ForEach-Object { $_.TrimEnd("`r") } | Where-Object { $_.Trim() })
}

$seen = -1   # 시작할 때 이미 있는 줄은 울리지 않는다
while ($true) {
    $lines = Get-Lines
    if ($null -ne $lines) {
        if ($seen -lt 0 -or $lines.Count -lt $seen) { $seen = $lines.Count }
        elseif ($lines.Count -gt $seen) {
            foreach ($ln in $lines[$seen..($lines.Count - 1)]) {
                $m = [regex]::Match($ln, '^(\d\d-\d\d \d\d:\d\d:\d\d)\s+(.*?)\s*측정 프로그램 로그:\s*(.+)$')
                if (-not $m.Success) { continue }
                $name = $m.Groups[2].Value.Trim(); $why = $m.Groups[3].Value.Trim()
                $level = if ($why -match '에러|닫혔') { 'red' } elseif ($why -match '미측정') { 'yellow' } else { $null }
                if (-not $level) { continue }
                $prefix = if ($name) { "$name  " } else { '' }
                $kind = if ($why -match '에러') { '음주측정기 에러' } elseif ($why -match '닫혔') { '측정이 끝나지 못하고 닫힘' } else { '미측정' }
                $text = $prefix + $kind
                if ($DryRun) { Add-Content -Path $OutFile -Value ("{0:HH:mm:ss.fff} [{1}] {2}" -f (Get-Date), $level, $text) -Encoding UTF8 } else { Show-Flash $text $level }
            }
            $seen = $lines.Count
        }
    }
    if ($DryRun) { Start-Sleep -Milliseconds 1000 } else { Wait-Ui 2000 }
}
