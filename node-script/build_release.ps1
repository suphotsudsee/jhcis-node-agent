$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$distRoot = Join-Path $projectRoot "dist"
$buildRoot = Join-Path $projectRoot "build"
$releaseRoot = Join-Path $projectRoot "release"
$packageName = "JHCISSyncDesktop_envonly"
$stageDir = Join-Path $releaseRoot $packageName
$zipPath = Join-Path $releaseRoot ("{0}_{1}.zip" -f $packageName, (Get-Date -Format "yyyyMMdd_HHmmss"))

function Invoke-ExternalCommand([scriptblock]$Command, [string]$ErrorMessage) {
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw $ErrorMessage
    }
}

Write-Host "Project root: $projectRoot"

python -c "import PyInstaller, mysql, mysql.connector, requests, win32serviceutil" | Out-Null

if (Test-Path $stageDir) {
    Remove-Item $stageDir -Recurse -Force
}

New-Item -ItemType Directory -Path $releaseRoot -Force | Out-Null

Write-Host "Building Windows service package..."
Invoke-ExternalCommand { pyinstaller --noconfirm --clean "$projectRoot\JHCISSyncService.spec" } "Service build failed."

Write-Host "Building desktop package..."
Invoke-ExternalCommand { pyinstaller --noconfirm --clean "$projectRoot\JHCISSyncDesktop_envonly.spec" } "Desktop build failed."

$desktopDist = Join-Path $distRoot $packageName
$serviceDist = Join-Path $distRoot "JHCISSyncService"

if (-not (Test-Path (Join-Path $desktopDist "$packageName.exe"))) {
    throw "Desktop executable not found: $(Join-Path $desktopDist "$packageName.exe")"
}

if (-not (Test-Path (Join-Path $serviceDist "JHCISSyncService.exe"))) {
    throw "Service executable not found: $(Join-Path $serviceDist "JHCISSyncService.exe")"
}

Copy-Item $desktopDist $stageDir -Recurse -Force

if (-not (Test-Path (Join-Path $stageDir "JHCISSyncService"))) {
    Copy-Item $serviceDist (Join-Path $stageDir "JHCISSyncService") -Recurse -Force
}

if (Test-Path (Join-Path $projectRoot ".env")) {
    Copy-Item (Join-Path $projectRoot ".env") (Join-Path $stageDir ".env") -Force
}

if (-not (Test-Path (Join-Path $stageDir "scheduler_settings.json"))) {
    @'
{
  "enabled": false,
  "time": "08:00",
  "use_today_date": true
}
'@ | Set-Content -Path (Join-Path $stageDir "scheduler_settings.json") -Encoding UTF8
}

Copy-Item (Join-Path $projectRoot "install_service.ps1") (Join-Path $stageDir "install_service.ps1") -Force
Copy-Item (Join-Path $projectRoot "uninstall_service.ps1") (Join-Path $stageDir "uninstall_service.ps1") -Force
Copy-Item (Join-Path $projectRoot ".env.example") (Join-Path $stageDir ".env.example") -Force
Copy-Item (Join-Path $projectRoot "INSTALL_TH.txt") (Join-Path $stageDir "INSTALL_TH.txt") -Force

if (Test-Path $zipPath) {
    Remove-Item $zipPath -Force
}

Compress-Archive -Path (Join-Path $stageDir "*") -DestinationPath $zipPath -Force

Write-Host ""
Write-Host "Release package created successfully."
Write-Host "Folder: $stageDir"
Write-Host "Zip:    $zipPath"
