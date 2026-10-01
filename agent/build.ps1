# Build the agent into one exe, then wrap it in an installer.
# Keep this file ASCII-only: PowerShell 5.1 reads .ps1 as ANSI and mangles non-ASCII.
#   powershell -ExecutionPolicy Bypass -File agent\build.ps1
param([switch]$SkipInstaller)

$ErrorActionPreference = 'Stop'
$agent = $PSScriptRoot
$root = Split-Path $agent -Parent
$py = "$env:LOCALAPPDATA\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\python.exe"
if (-not (Test-Path $py)) { $py = (Get-Command python).Source }

# 1) icon
& $py (Join-Path $agent 'make_icon.py')

# 2) one-file exe (python, pywin32, pystray, PIL all bundled - nothing to install on the target PC)
Push-Location $root
try {
    $args = @(
        '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--windowed',
        '--name', 'BusyardAgent',
        '--icon', (Join-Path $agent 'icon.ico'),
        '--distpath', (Join-Path $agent 'dist'),
        '--workpath', (Join-Path $agent 'build'),
        '--specpath', $agent,
        '--add-data', ((Join-Path $root 'src\yard-data.js') + ';.'),
        '--add-data', ((Join-Path $root 'src\yard-old-data.js') + ';.'),
        '--hidden-import', 'win32timezone',
        (Join-Path $agent 'agent.py')
    )
    & $py @args
}
finally { Pop-Location }

$exe = Join-Path $agent 'dist\BusyardAgent.exe'
if (-not (Test-Path $exe)) { throw "exe not built" }
"exe: {0} ({1:N1} MB)" -f $exe, ((Get-Item $exe).Length / 1MB)

# 3) installer (Inno Setup)
if ($SkipInstaller) { return }
$iscc = @(
    'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',
    'C:\Program Files\Inno Setup 6\ISCC.exe',
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
    Write-Warning "Inno Setup not found - run: winget install -e --id JRSoftware.InnoSetup"
    return
}
& $iscc (Join-Path $agent 'installer.iss')
$setup = Get-ChildItem (Join-Path $agent 'dist') -Filter '*Setup*.exe' | Select-Object -First 1
if ($setup) { "setup: {0} ({1:N1} MB)" -f $setup.FullName, ($setup.Length / 1MB) }

# 4) hand it over: keep the finished installer where the user can grab it
#    (and where GitHub serves it, so computer A can just download it)
$out = Join-Path $root '설치프로그램'
New-Item -ItemType Directory -Force -Path $out | Out-Null
Copy-Item $setup.FullName $out -Force
Copy-Item (Join-Path $agent '읽어보기.txt') $out -Force
"handed over: $out"
