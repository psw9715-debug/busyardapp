# Run the browser test pages without the browser tool: local server + headless Edge.
# Each page sets document.title to "PASS n" / "FAIL n" when it finishes.
# Keep this file ASCII-only: PowerShell 5.1 reads .ps1 as ANSI and mangles non-ASCII paths.
param(
    [Parameter(Mandatory = $true)][string]$Root,
    [int]$Port = 5187,
    [string[]]$Pages = @('test', 'app.test', 'voice.test', 'guide.test')
)

$ErrorActionPreference = 'Stop'
$edge = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
$py = "$env:LOCALAPPDATA\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\python.exe"

$srv = Start-Process $py -ArgumentList '-m', 'http.server', "$Port", '--directory', $Root -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 2
try {
    foreach ($page in $Pages) {
        $out = Join-Path $env:TEMP "claude\dom_$page.html"
        $argv = @(
            '--headless=new', '--disable-gpu', '--no-first-run',
            "--user-data-dir=$env:TEMP\claude\edgeprof_$page",
            '--virtual-time-budget=20000',
            '--dump-dom', "http://localhost:$Port/tools/$page.html"
        )
        Start-Process $edge -ArgumentList $argv -RedirectStandardOutput $out -NoNewWindow -Wait | Out-Null
        $html = Get-Content $out -Raw -Encoding utf8
        $title = if ($html -match '<title>([^<]*)</title>') { $Matches[1] } else { '(no title)' }
        "{0,-12} {1}" -f $page, $title
        foreach ($m in ([regex]::Matches($html, 'FAIL\s+([^\n<]{0,90})') | Select-Object -First 6)) {
            '               ' + $m.Groups[1].Value.Trim()
        }
    }
}
finally {
    Stop-Process -Id $srv.Id -Force -ErrorAction SilentlyContinue
}
