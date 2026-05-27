# 完整发布（自包含）：毛玻璃前端 → API exe（内嵌 dist）→ Electron 安装包
# 所有产物与依赖路径均在 desktop-electron/ 内，不引用 desktop-local / extended-frontend
param(
    [switch]$SkipApi,
    [switch]$SkipElectron
)

$ErrorActionPreference = "Stop"
$AppRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "BuildCommon.ps1")

function Clear-ElectronDistOutput {
    param([string]$Root)

    $distRoot = Join-Path $Root "dist-electron"
    if (-not (Test-Path $distRoot)) { return }

    Stop-LocalDesktopProcesses -AppRoot $Root

    for ($attempt = 1; $attempt -le 5; $attempt++) {
        try {
            Remove-Item -LiteralPath $distRoot -Recurse -Force -ErrorAction Stop
            return
        } catch {
            Write-Host "Retry clearing dist-electron ($attempt/5)..."
            Stop-LocalDesktopProcesses -AppRoot $Root
            Start-Sleep -Seconds 2
        }
    }

    $bak = Join-Path $Root ("dist-electron.old." + [DateTime]::Now.ToString("yyyyMMddHHmmss"))
    try {
        Rename-Item -LiteralPath $distRoot -NewName (Split-Path -Leaf $bak) -Force -ErrorAction Stop
        Write-Host "WARN: dist-electron locked; renamed to $(Split-Path -Leaf $bak)"
    } catch {
        throw @"
Cannot clear dist-electron (files may be locked).
Close any running 文档智能系统 window under this folder, then rerun build.ps1.
"@
    }
}

Set-Location $AppRoot
Stop-LocalDesktopProcesses -AppRoot $AppRoot

Write-Host "==> Step 1/3: Build glass frontend (frontend/)"
Set-Location "$AppRoot\frontend"
if (-not (Test-Path "node_modules")) { npm install }
npm run build
if (-not (Test-Path "dist\index.html")) {
    throw "Frontend build failed: missing frontend/dist/index.html"
}
Assert-GlassFrontendDist -DistDir "$AppRoot\frontend\dist"

$apiDir = Join-Path $AppRoot "dist-api\DocumentIntelligenceApi"
$apiExe = Join-Path $apiDir "DocumentIntelligenceApi.exe"

Write-Host "==> Step 2/3: Build API bundle (embeds frontend/dist)"
Set-Location $AppRoot
if ($SkipApi -and (Test-Path -LiteralPath $apiExe)) {
    if (-not (Test-ApiBundleIncludesFreshFrontend -AppRoot $AppRoot -ApiExePath $apiExe)) {
        throw @"
-SkipApi refused: dist-api frontend is stale or not glass UI.
Run full build: .\scripts\build.ps1
"@
    }
    Write-Host "    Skipped (-SkipApi). Using: $apiExe"
} else {
    & "$PSScriptRoot\build_api.ps1" -SkipFrontendBuild
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    if (-not (Test-ApiBundleIncludesFreshFrontend -AppRoot $AppRoot -ApiExePath $apiExe)) {
        throw "API bundle verification failed after build_api.ps1"
    }
}

if (Test-Path (Join-Path $apiDir "_internal\webview")) {
    throw "dist-api contains pywebview — use build_api.ps1 only (Electron path, not desktop-local)."
}

if ($SkipElectron) {
    Write-Host ""
    Write-Host "Done (API only, -SkipElectron). API:"
    Write-Host "  $apiExe"
    exit 0
}

Write-Host "==> Step 3/3: electron-builder"
Set-Location $AppRoot

Write-Host "    Regenerate app-icon.ico"
$py = "python"
if (Test-Path (Join-Path $AppRoot ".venv-build\Scripts\python.exe")) {
    $py = Join-Path $AppRoot ".venv-build\Scripts\python.exe"
}
& $py "$PSScriptRoot\generate_app_icon.py"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Clear-ElectronDistOutput -Root $AppRoot
if (-not (Test-Path "node_modules")) { npm install }
npm run build:electron
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$unpackedHtml = Join-Path $AppRoot "dist-electron\win-unpacked\resources\backend\DocumentIntelligenceApi\_internal\frontend\dist"
if (Test-Path $unpackedHtml) {
    Assert-GlassFrontendDist -DistDir $unpackedHtml -Label "packaged frontend"
}

Write-Host ""
Write-Host "Done. Self-contained installer / unpacked app:"
Write-Host "  $AppRoot\dist-electron"
Write-Host "  Run: dist-electron\win-unpacked\文档智能系统.exe"
