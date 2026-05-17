# Electron 开发：本目录自包含（frontend + backend + src）
$ErrorActionPreference = "Stop"
$AppRoot = Split-Path -Parent $PSScriptRoot

Set-Location $AppRoot

if (-not (Test-Path "$AppRoot\src")) {
    throw "Missing desktop-electron\src — run scripts\sync_src.ps1 or copy from repo."
}

if (-not (Test-Path "$AppRoot\frontend\dist\index.html")) {
    Write-Host "==> Building frontend..."
    Set-Location "$AppRoot\frontend"
    if (-not (Test-Path "node_modules")) { npm install }
    npm run build
    Set-Location $AppRoot
}

$venvPy = Join-Path $AppRoot ".venv-build\Scripts\python.exe"
if (Test-Path $venvPy) {
    $py = $venvPy
    Write-Host "==> Using .venv-build for API backend."
} else {
    $py = "python"
    Write-Host "==> Installing Python deps from desktop-electron\requirements.txt..."
    & $py -m pip install -r "$AppRoot\requirements.txt" -q
}

$env:DOC_INTEL_DESKTOP = "1"
$env:DOC_INTEL_ELECTRON = "1"
$env:DOC_INTEL_PYTHON = $py

if (-not (Test-Path "node_modules")) {
    Write-Host "==> npm install (electron)..."
    npm install
}

Write-Host "==> Starting Electron..."
Write-Host "    Data: %APPDATA%\document-intelligence-desktop-electron\data"
npm run dev
