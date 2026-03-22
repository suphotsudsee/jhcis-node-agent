$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
function Resolve-ServiceExe([string]$baseDir) {
    $candidates = @(
        (Join-Path $baseDir "JHCISSyncService\\JHCISSyncService.exe"),
        (Join-Path $baseDir "dist\\JHCISSyncService\\JHCISSyncService.exe"),
        (Join-Path (Split-Path -Parent $baseDir) "JHCISSyncService\\JHCISSyncService.exe"),
        (Join-Path (Split-Path -Parent $baseDir) "dist\\JHCISSyncService\\JHCISSyncService.exe"),
        (Join-Path $baseDir "_internal\\JHCISSyncService\\JHCISSyncService.exe")
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    throw "Service executable not found. Checked:`n$($candidates -join [Environment]::NewLine)"
}

$serviceExe = Resolve-ServiceExe $root

try {
    & $serviceExe stop
} catch {
}

& $serviceExe remove
Start-Sleep -Seconds 2

if (Get-Service -Name "JHCISSyncService" -ErrorAction SilentlyContinue) {
    throw "Service removal failed. Run PowerShell as Administrator and try again."
}

Write-Host "Removed JHCIS Sync Service"
