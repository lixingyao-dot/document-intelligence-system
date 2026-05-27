# Electron 开发：Vite 热更新 + 本地 API（改 frontend/src 立即生效）
$ErrorActionPreference = "Stop"
$AppRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "BuildCommon.ps1")

Set-Location $AppRoot
Stop-LocalDesktopProcesses -AppRoot $AppRoot

if (-not (Test-Path "$AppRoot\src")) {
    throw "Missing desktop-electron\src"
}

$frontendDir = Join-Path $AppRoot "frontend"
if (-not (Test-Path "$frontendDir\node_modules")) {
    Write-Host "==> npm install (frontend)..."
    Set-Location $frontendDir
    npm install
    Set-Location $AppRoot
}

$venvPy = Join-Path $AppRoot ".venv-build\Scripts\python.exe"
if (Test-Path $venvPy) {
    $py = $venvPy
} else {
    $py = "python"
    & $py -m pip install -r "$AppRoot\requirements.txt" -q
}

if (-not (Test-Path "node_modules")) {
    Write-Host "==> npm install (electron)..."
    npm install
}

$apiPort = 8766
$viteUrl = "http://127.0.0.1:5175"
$env:DOC_INTEL_DESKTOP = "1"
$env:DOC_INTEL_ELECTRON = "1"
$env:DOC_INTEL_PYTHON = $py
$env:DESKTOP_API_PORT = "$apiPort"
$env:DOC_INTEL_UI_URL = $viteUrl

$viteProc = $null
try {
    Write-Host "==> Starting Vite dev server (frontend/src -> live UI)..."
    $viteProc = Start-Process -FilePath "npm.cmd" -ArgumentList @("run", "dev") `
        -WorkingDirectory $frontendDir -PassThru -WindowStyle Hidden

    $viteReady = $false
    for ($i = 0; $i -lt 60; $i++) {
        try {
            $resp = Invoke-WebRequest -Uri $viteUrl -UseBasicParsing -TimeoutSec 2
            if ($resp.StatusCode -eq 200 -and $resp.Content -match 'electron-glass') {
                $viteReady = $true
                break
            }
        } catch {
            # wait
        }
        Start-Sleep -Seconds 1
    }
    if (-not $viteReady) {
        throw "Vite did not become ready at $viteUrl"
    }

    Write-Host "==> Starting Electron..."
    Write-Host "    UI:  $viteUrl  (edit frontend/src, save to refresh)"
    Write-Host "    API: http://127.0.0.1:$apiPort"
    Write-Host "    Data: %APPDATA%\document-intelligence-desktop-electron\data"
    npm run dev
} finally {
    if ($viteProc -and -not $viteProc.HasExited) {
        Stop-Process -Id $viteProc.Id -Force -ErrorAction SilentlyContinue
    }
    Stop-LocalDesktopProcesses -AppRoot $AppRoot
}
