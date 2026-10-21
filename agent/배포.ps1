# 받아쓰기 설치본을 만들어 공유 폴더에 올린다.
# 이 파일은 한글이 들어 있으므로 **UTF-8 BOM** 으로 저장해야 한다
# (PowerShell 5.1 은 BOM 이 없으면 ANSI 로 읽어 경로가 깨진다).
#
#   powershell -ExecutionPolicy Bypass -File agent\배포.ps1
#   powershell -ExecutionPolicy Bypass -File agent\배포.ps1 -만들지않고
#
# 하는 일
#   1) 한 덩어리 exe 와 설치본을 만든다 (agent\build.ps1)
#   2) 공유 폴더의 **옛 설치본을 지운다** — 둘이 나란히 있으면 옛것을 깔게 된다
#   3) 새것을 올리고 해시로 같은 파일인지 확인한다
#
# 공유 폴더는 업무관리\설정.json 에서 읽는다. 새 PC 로 옮겨도 그 파일 하나만 고치면 된다.
param([switch]$만들지않고)

$ErrorActionPreference = 'Stop'
$에이전트 = $PSScriptRoot
$뿌리 = Split-Path $에이전트 -Parent

function 공유뿌리 {
    $설정 = 'D:\업무관리\설정.json'
    if (Test-Path $설정) {
        try {
            $값 = Get-Content $설정 -Raw -Encoding UTF8 | ConvertFrom-Json
            $드라이브 = $값.'공유폴더'.'드라이브'
            if ($드라이브 -and (Test-Path "$드라이브\")) { return "$드라이브\" }
            $UNC = $값.'공유폴더'.'UNC'
            if ($UNC -and (Test-Path $UNC)) { return "$UNC\" }
        } catch { }
    }
    if (Test-Path 'Z:\') { return 'Z:\' }
    return '\\192.168.35.22\sctc17\'
}

$올릴곳 = Join-Path (공유뿌리) '유틸리티\차고지순찰프로그램'

if (-not $만들지않고) {
    # 옛 설치본을 먼저 치운다. build.ps1 은 dist 에 있는 설치본을 전부 설치프로그램으로
    # 옮기므로, 치우지 않으면 판올림할 때마다 옛것이 하나씩 더 쌓인다 (하나에 13.7MB).
    Get-ChildItem (Join-Path $에이전트 'dist') -Filter '*_Setup_*.exe' -ErrorAction SilentlyContinue |
        ForEach-Object { Remove-Item $_.FullName -Force }
    Write-Host '== 설치본 만드는 중 =='
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $에이전트 'build.ps1')
    if ($LASTEXITCODE -ne 0) { throw '설치본을 만들지 못했다' }
}

$새것 = Get-ChildItem (Join-Path $뿌리 '설치프로그램') -Filter '*_Setup_*.exe' |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $새것) { throw '올릴 설치본을 찾지 못했다' }
Write-Host ('새 설치본  : ' + $새것.Name)

# 저장소에도 가장 새것 하나만 남긴다
Get-ChildItem (Join-Path $뿌리 '설치프로그램') -Filter '*_Setup_*.exe' |
    Where-Object { $_.Name -ne $새것.Name } |
    ForEach-Object { Remove-Item $_.FullName -Force; Write-Host ('저장소 정리: ' + $_.Name) }

if (-not (Test-Path $올릴곳)) {
    New-Item -ItemType Directory -Path $올릴곳 -Force | Out-Null
    Write-Host ('폴더 만듦  : ' + $올릴곳)
}

Get-ChildItem $올릴곳 -Filter '*_Setup_*.exe' -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -ne $새것.Name } |
    ForEach-Object { Remove-Item $_.FullName -Force; Write-Host ('옛것 지움  : ' + $_.Name) }

$간곳 = Join-Path $올릴곳 $새것.Name
Copy-Item $새것.FullName $간곳 -Force
$같나 = (Get-FileHash $새것.FullName -Algorithm SHA256).Hash -eq (Get-FileHash $간곳 -Algorithm SHA256).Hash
Write-Host ('올린 곳    : ' + $간곳)
Write-Host ('같은 파일  : ' + $같나)
if (-not $같나) { throw '올린 것이 원본과 다르다' }
Get-ChildItem $올릴곳 | Select-Object Name, Length, LastWriteTime | Format-Table -AutoSize
