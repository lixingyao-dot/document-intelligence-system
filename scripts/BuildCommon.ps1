# 本目录专用构建辅助（仅 desktop-electron 内路径，不依赖仓库其它目录）

function Get-AppRootFromScript {
    param([string]$ScriptRoot)
    return (Resolve-Path (Join-Path $ScriptRoot "..")).Path
}

function Stop-LocalDesktopProcesses {
    param([string]$AppRoot)

    $AppRoot = (Resolve-Path -LiteralPath $AppRoot).Path
    $markers = @(
        (Join-Path $AppRoot "dist-api"),
        (Join-Path $AppRoot "dist-electron"),
        $AppRoot
    ) | ForEach-Object { $_.ToLowerInvariant() }

    $names = @("electron", "DocumentIntelligenceApi", "文档智能系统")
    foreach ($name in $names) {
        Get-Process -Name $name -ErrorAction SilentlyContinue | ForEach-Object {
            try {
                $exe = $_.Path
                if (-not $exe) { return }
                $norm = $exe.ToLowerInvariant()
                if ($markers | Where-Object { $norm.StartsWith($_) }) {
                    Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
                }
            } catch {
                /* ignore */
            }
        }
    }

    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -in @("DocumentIntelligenceApi.exe", "electron.exe", "文档智能系统.exe") -and
            $_.ExecutablePath -and (
                ($_.ExecutablePath.ToLowerInvariant().StartsWith((Join-Path $AppRoot "dist-api").ToLowerInvariant())) -or
                ($_.ExecutablePath.ToLowerInvariant().StartsWith((Join-Path $AppRoot "dist-electron").ToLowerInvariant()))
            )
        } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

    Start-Sleep -Seconds 1
}

function Get-NewestFileTime {
    param([string]$Root, [string[]]$Include = @("*"))
    if (-not (Test-Path -LiteralPath $Root)) { return $null }
    $f = Get-ChildItem -LiteralPath $Root -Recurse -File -Include $Include -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($f) { return $f.LastWriteTime }
    return $null
}

function Test-GlassFrontendDist {
    param([string]$DistDir)

    $index = Join-Path $DistDir "index.html"
    if (-not (Test-Path -LiteralPath $index)) { return $false }

    $html = Get-Content -LiteralPath $index -Raw -ErrorAction SilentlyContinue
    if ($html -notmatch 'electron-glass') { return $false }

    $cssDir = Join-Path $DistDir "assets"
    if (-not (Test-Path -LiteralPath $cssDir)) { return $false }

    $cssFile = Get-ChildItem -LiteralPath $cssDir -Filter "*.css" -File -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $cssFile) { return $false }

    $css = Get-Content -LiteralPath $cssFile.FullName -Raw -ErrorAction SilentlyContinue
    return ($css -match 'glass-deep') -and ($css -notmatch 'pixel-paper')
}

function Assert-BundledFrontendMatchesSource {
    param([string]$AppRoot)

    $srcDir = Join-Path $AppRoot "frontend\dist"
    $bundledDir = Join-Path $AppRoot "dist-api\DocumentIntelligenceApi\_internal\frontend\dist"
    if (-not (Test-Path -LiteralPath $bundledDir)) {
        throw "Missing bundled frontend: $bundledDir"
    }

    $srcFiles = Get-ChildItem -LiteralPath $srcDir -Recurse -File -ErrorAction Stop
    if (-not $srcFiles.Count) {
        throw "frontend/dist is empty — run: cd frontend && npm run build"
    }

    foreach ($sf in $srcFiles) {
        $rel = $sf.FullName.Substring($srcDir.Length).TrimStart('\', '/')
        $bf = Join-Path $bundledDir $rel
        if (-not (Test-Path -LiteralPath $bf)) {
            throw "API bundle missing frontend file: $rel"
        }
        $sh = (Get-FileHash -LiteralPath $sf.FullName -Algorithm SHA256).Hash
        $bh = (Get-FileHash -LiteralPath $bf -Algorithm SHA256).Hash
        if ($sh -ne $bh) {
            throw @"
API bundle frontend mismatch: $rel
Source and _internal/frontend/dist differ — delete dist-api and rerun build.ps1
"@
        }
    }
}

function Test-ApiBundleIncludesFreshFrontend {
    param(
        [string]$AppRoot,
        [string]$ApiExePath
    )

    if (-not (Test-Path -LiteralPath $ApiExePath)) { return $false }

    $frontendDist = Join-Path $AppRoot "frontend\dist"
    if (-not (Test-GlassFrontendDist -DistDir $frontendDist)) { return $false }

    $bundled = Join-Path (Split-Path -Parent $ApiExePath) "_internal\frontend\dist"
    if (-not (Test-GlassFrontendDist -DistDir $bundled)) { return $false }

    $apiTime = (Get-Item -LiteralPath $ApiExePath).LastWriteTime
    $feTime = Get-NewestFileTime -Root $frontendDist -Include "*.html", "*.css", "*.js"
    if ($feTime -and $feTime -gt $apiTime) { return $false }

    return $true
}

function Assert-GlassFrontendDist {
    param([string]$DistDir, [string]$Label = "frontend/dist")

    if (-not (Test-GlassFrontendDist -DistDir $DistDir)) {
        throw @"
$Label is not the Electron glass UI (need electron-glass + glass-deep, no pixel-paper).
Run: cd frontend && npm run build
"@
    }
}
