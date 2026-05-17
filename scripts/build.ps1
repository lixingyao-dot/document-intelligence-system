# 完整发布：前端 + API exe + Electron 安装包（均在 desktop-electron 目录内）
param(
    [switch]$RebuildApi,
    [switch]$SkipApi
)

$ErrorActionPreference = "Stop"
$AppRoot = Split-Path -Parent $PSScriptRoot

function Test-ApiBundleFresh {
    param([string]$ApiExePath)
    if (-not (Test-Path -LiteralPath $ApiExePath)) { return $false }
    $apiTime = (Get-Item -LiteralPath $ApiExePath).LastWriteTime
    $watch = @(
        (Join-Path $AppRoot "launcher.py"),
        (Join-Path $AppRoot "server_entry.py"),
        (Join-Path $AppRoot "scripts\build_api.ps1"),
        (Join-Path $AppRoot "src\output\result_handler.py")
    )
    foreach ($dir in @("src", "backend")) {
        $p = Join-Path $AppRoot $dir
        if (Test-Path -LiteralPath $p) { $watch += $p }
    }
    $newest = $apiTime
    foreach ($item in $watch) {
        if (-not (Test-Path -LiteralPath $item)) { continue }
        if ((Get-Item -LiteralPath $item).PSIsContainer) {
            $f = Get-ChildItem -LiteralPath $item -Recurse -File -Include *.py,*.json -ErrorAction SilentlyContinue |
                Sort-Object LastWriteTime -Descending | Select-Object -First 1
            if ($f -and $f.LastWriteTime -gt $newest) { return $false }
        } elseif ((Get-Item -LiteralPath $item).LastWriteTime -gt $newest) {
            return $false
        }
    }
    return $true
}

function Stop-PackagedAppProcesses {
    $names = @(
        "electron",
        "DocumentIntelligenceApi",
        "DocumentIntelligenceDesktop",
        "文档智能系统"
    )
    foreach ($name in $names) {
        Get-Process -Name $name -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    }
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.ExecutablePath -and (
                $_.ExecutablePath -like "*\desktop-electron\dist-electron\*" -or
                $_.ExecutablePath -like "*\DocumentIntelligenceApi.exe"
            )
        } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 2
}

function Clear-ElectronDistOutput {
    $distRoot = Join-Path $AppRoot "dist-electron"
    if (-not (Test-Path $distRoot)) { return }

    Stop-PackagedAppProcesses

    for ($attempt = 1; $attempt -le 5; $attempt++) {
        try {
            Remove-Item -LiteralPath $distRoot -Recurse -Force -ErrorAction Stop
            return
        } catch {
            Write-Host "Retry clearing dist-electron ($attempt/5)..."
            Stop-PackagedAppProcesses
            Start-Sleep -Seconds 2
        }
    }

    $bak = Join-Path $AppRoot ("dist-electron.old." + [DateTime]::Now.ToString("yyyyMMddHHmmss"))
    try {
        Rename-Item -LiteralPath $distRoot -NewName (Split-Path -Leaf $bak) -Force -ErrorAction Stop
        Write-Host "WARN: dist-electron locked; renamed to $(Split-Path -Leaf $bak)"
    } catch {
        throw @"
Cannot clear dist-electron (app.asar may be locked).
Close any running 文档智能系统 window, then rerun build.ps1.
"@
    }
}

Set-Location $AppRoot

Write-Host "==> Step 1/3: Build frontend"
Set-Location "$AppRoot\frontend"
if (-not (Test-Path "node_modules")) { npm install }
npm run build
if (-not (Test-Path "dist\index.html")) {
    throw "Frontend build failed"
}

$apiDir = Join-Path $AppRoot "dist-api\DocumentIntelligenceApi"
$apiExe = Join-Path $apiDir "DocumentIntelligenceApi.exe"

Write-Host "==> Step 2/3: Build API (PyInstaller)"
Set-Location $AppRoot
if ($SkipApi -and (Test-Path -LiteralPath $apiExe)) {
    Write-Host "    Skipped (-SkipApi). Using existing: $apiExe"
} elseif (-not $RebuildApi -and (Test-ApiBundleFresh -ApiExePath $apiExe)) {
    Write-Host "    Skipped (dist-api is newer than src; use -RebuildApi to force)."
} else {
    & "$PSScriptRoot\build_api.ps1" -SkipFrontendBuild
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

if (-not (Test-Path -LiteralPath $apiExe)) {
    throw "Missing API exe: $apiExe — run .\scripts\build_api.ps1 first"
}
if (Test-Path (Join-Path $apiDir "_internal\webview")) {
    throw "dist-api contains pywebview — use build_api.ps1 only, not pywebview desktop build."
}

Write-Host "==> Step 3/3: electron-builder"
Set-Location $AppRoot

Write-Host "    Regenerate app-icon.ico (NSIS requires >= 256x256)"
$py = "python"
if (Test-Path (Join-Path $AppRoot ".venv-build\Scripts\python.exe")) {
    $py = Join-Path $AppRoot ".venv-build\Scripts\python.exe"
}
& $py "$PSScriptRoot\generate_app_icon.py"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Clear-ElectronDistOutput
if (-not (Test-Path "node_modules")) { npm install }
npm run build
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Done. Installer / unpacked app:"
Write-Host "  $AppRoot\dist-electron"
