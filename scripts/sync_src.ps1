# 从仓库根 src/ 同步到 desktop-electron/src/（排除运行时垃圾与用户数据）
$ErrorActionPreference = "Stop"
$AppRoot = Split-Path -Parent $PSScriptRoot
$RepoRoot = Split-Path -Parent $AppRoot
$RepoSrc = Join-Path $RepoRoot "src"
$Dest = Join-Path $AppRoot "src"

if (-not (Test-Path -LiteralPath $RepoSrc)) {
    throw "Repo src not found: $RepoSrc"
}

Write-Host "==> Syncing $RepoSrc -> $Dest"
# 排除 temp 与运行时产物；output/ 目录内既有 Python 包又有生成文件，单独同步 .py
& robocopy.exe $RepoSrc $Dest /E /XD temp __pycache__ .pytest_cache /XF *.pyc /NFL /NDL /NJH /NJS /nc /ns /np
$rc = $LASTEXITCODE
if ($rc -ge 8) { exit $rc }

$outputSrc = Join-Path $RepoSrc "output"
$outputDest = Join-Path $Dest "output"
if (Test-Path -LiteralPath $outputSrc) {
    New-Item -ItemType Directory -Force -Path $outputDest | Out-Null
    Get-ChildItem -LiteralPath $outputSrc -Filter "*.py" -File | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $outputDest $_.Name) -Force
    }
    Write-Host "==> Synced output package (*.py only)"
}

$workflowFrom = Join-Path (Join-Path $RepoSrc "workspace") "workflows"
if (-not (Test-Path -LiteralPath $workflowFrom)) {
    $workflowFrom = Join-Path (Join-Path $RepoRoot "workspace") "workflows"
}
$workflowTo = Join-Path (Join-Path $AppRoot "workspace") "workflows"
if (Test-Path -LiteralPath $workflowFrom) {
    New-Item -ItemType Directory -Force -Path $workflowTo | Out-Null
    & robocopy.exe $workflowFrom $workflowTo /E /NFL /NDL /NJH /NJS /nc /ns /np
    $rc2 = $LASTEXITCODE
    if ($rc2 -ge 8) { exit $rc2 }
}

Write-Host "Done. desktop-electron is self-contained under: $AppRoot"
exit 0
