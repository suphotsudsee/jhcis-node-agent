$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$distDir = Join-Path $projectRoot "dist"
$buildDir = Join-Path $projectRoot "build"
$docsDir = Join-Path (Split-Path -Parent $projectRoot) "docs"
$queriesPath = Join-Path $docsDir "queries.sql"

python -c "import mysql, mysql.connector, requests" | Out-Null

$arguments = @(
  "--noconfirm",
  "--clean",
  "--windowed",
  "--name", "JHCISSyncDesktop",
  "--hidden-import", "mysql",
  "--hidden-import", "mysql.connector",
  "--collect-submodules", "mysql.connector",
  "--add-data", "$projectRoot\.env.example;."
)

if (Test-Path $queriesPath) {
    $arguments += @("--add-data", "$queriesPath;docs")
}

$arguments += "$projectRoot\desktop_app.py"

pyinstaller @arguments

Write-Host ""
Write-Host "Build complete:"
Write-Host "EXE: $distDir\\JHCISSyncDesktop\\JHCISSyncDesktop.exe"
Write-Host "Folder: $distDir\\JHCISSyncDesktop"
