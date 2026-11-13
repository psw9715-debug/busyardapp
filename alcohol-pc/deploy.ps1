# NAS 공유 폴더에 올린다 (GitHub 는 git push 로). UTF-8 BOM 으로 저장.
$nas = '\192.168.35.22\sctc17\유틸리티\음주PC에이전트'
New-Item -ItemType Directory -Path $nas -Force | Out-Null
foreach ($n in 'watch.ps1', 'install.ps1', 'install.bat', 'README.txt') { Copy-Item (Join-Path $PSScriptRoot $n) (Join-Path $nas $n) -Force }
Get-ChildItem $nas | Select-Object Name, Length, LastWriteTime | Format-Table -AutoSize
