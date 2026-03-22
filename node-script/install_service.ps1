$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
function Resolve-ServiceDist([string]$baseDir) {
    $candidates = @(
        (Join-Path $baseDir "JHCISSyncService"),
        (Join-Path $baseDir "dist\\JHCISSyncService"),
        (Join-Path (Split-Path -Parent $baseDir) "JHCISSyncService"),
        (Join-Path (Split-Path -Parent $baseDir) "dist\\JHCISSyncService"),
        (Join-Path $baseDir "_internal\\JHCISSyncService")
    )

    foreach ($candidate in $candidates) {
        $exePath = Join-Path $candidate "JHCISSyncService.exe"
        if (Test-Path $exePath) {
            return $candidate
        }
    }

    $checked = ($candidates | ForEach-Object { Join-Path $_ "JHCISSyncService.exe" }) -join [Environment]::NewLine
    throw "Service executable not found. Checked:`n$checked"
}

function Resolve-DesktopConfigPath([string]$baseDir, [string]$fileName) {
    $candidates = @(
        (Join-Path $baseDir $fileName),
        (Join-Path $baseDir "dist\\JHCISSyncDesktop_envonly\\$fileName"),
        (Join-Path (Split-Path -Parent $baseDir) $fileName),
        (Join-Path (Split-Path -Parent $baseDir) "dist\\JHCISSyncDesktop_envonly\\$fileName")
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    return $null
}

$serviceDist = Resolve-ServiceDist $root
$serviceExe = Join-Path $serviceDist "JHCISSyncService.exe"
$envSource = Resolve-DesktopConfigPath $root ".env"
$scheduleSource = Resolve-DesktopConfigPath $root "scheduler_settings.json"

if ($null -ne $envSource -and (Test-Path $envSource)) {
    Copy-Item $envSource (Join-Path $serviceDist ".env") -Force
}

if ($null -ne $scheduleSource -and (Test-Path $scheduleSource)) {
    Copy-Item $scheduleSource (Join-Path $serviceDist "scheduler_settings.json") -Force
}

& $serviceExe --startup auto install
if (-not (Get-Service -Name "JHCISSyncService" -ErrorAction SilentlyContinue)) {
    throw "Service install failed. Run PowerShell as Administrator and try again."
}

& $serviceExe start
Start-Sleep -Seconds 2

$service = Get-Service -Name "JHCISSyncService" -ErrorAction Stop
if ($service.Status -ne "Running") {
    throw "Service was installed but did not start successfully. Current status: $($service.Status)"
}

Write-Host "Installed and started JHCIS Sync Service"
