# PyInstaller：仅 API（无 pywebview），供 Electron extraResources 捆绑
param(
    [switch]$ForceDeps,
    [switch]$SkipFrontendBuild
)

$ErrorActionPreference = "Stop"
$AppRoot = Split-Path -Parent $PSScriptRoot

function Stop-ApiExe {
    Get-Process -Name "DocumentIntelligenceApi" -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep -Seconds 1
}

function Ensure-BuildVenv {
    $venv = Join-Path $AppRoot ".venv-build"
    $py = Join-Path $venv "Scripts\python.exe"
    $pyi = Join-Path $venv "Scripts\pyinstaller.exe"
    $reqFile = Join-Path $AppRoot "requirements-desktop-build.txt"
    $stamp = Join-Path $venv ".deps-installed.stamp"

    if (-not (Test-Path $py)) {
        Write-Host "==> Creating isolated build venv: .venv-build"
        python -m venv $venv
        $ForceDeps = $true
    }

    $reqHash = ""
    if (Test-Path $reqFile) {
        $reqHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $reqFile).Hash
    }
    $stampOk = (Test-Path $stamp) -and ((Get-Content -LiteralPath $stamp -Raw -ErrorAction SilentlyContinue).Trim() -eq $reqHash)
    $needInstall = $ForceDeps -or (-not (Test-Path $pyi)) -or (-not $stampOk)

    if ($needInstall) {
        Write-Host "==> Installing dependencies (pip timeout 120s)..."
        $pipArgs = @("-m", "pip", "install", "--default-timeout=120")
        if ($ForceDeps) {
            try {
                & $py @pipArgs --upgrade pip wheel setuptools -q 2>$null
            } catch {
                Write-Host "Note: pip self-upgrade skipped (network)."
            }
        }
        & $py @pipArgs -r $reqFile -q
        if ($LASTEXITCODE -ne 0) { throw "pip install failed in .venv-build" }
        if ($reqHash) { Set-Content -LiteralPath $stamp -Value $reqHash -Encoding utf8 }
    } else {
        Write-Host "==> Dependencies OK (skip pip; -ForceDeps to reinstall)"
    }

    if (-not (Test-Path $pyi)) { throw "PyInstaller not found in .venv-build" }

    return @{ Python = $py; PyInstaller = $pyi }
}

$excludeModules = @(
    "torch", "torchvision", "torchaudio", "torchtext", "torchgen",
    "cv2", "opencv_python",
    "matplotlib", "matplotlib.backends",
    "scipy", "sklearn", "scikit_learn", "scikit-image", "skimage",
    "tensorflow", "keras", "tensorboard",
    "nltk", "spacy",
    "pytest", "_pytest",
    "IPython", "jupyter", "jupyter_client", "jupyter_core", "notebook", "nbformat",
    "sympy",
    "transformers", "accelerate", "huggingface_hub", "tokenizers", "safetensors",
    "onnx", "onnxruntime",
    "oss2", "aliyunsdkcore", "aliyunsdkkms",
    "twisted",
    "sqlalchemy", "alembic",
    "numba", "llvmlite", "dask", "distributed",
    "pyarrow",
    "google.cloud.aiplatform", "vertexai",
    "faiss", "chromadb",
    "selenium", "playwright",
    "_tkinter", "tkinter",
    "PyQt5", "PyQt6", "PySide2", "PySide6", "wx",
    "webview", "proxy_tools", "pythonnet", "clr_loader", "bottle"
)

if (-not $SkipFrontendBuild -and -not (Test-Path "$AppRoot\frontend\dist\index.html")) {
    Write-Host "==> Building frontend (required for API bundle)..."
    Set-Location "$AppRoot\frontend"
    if (-not (Test-Path "node_modules")) { npm install }
    npm run build
    Set-Location $AppRoot
}

Stop-ApiExe
$dist = Join-Path $AppRoot "dist-api"
if (Test-Path $dist) {
    try {
        Remove-Item -LiteralPath $dist -Recurse -Force -ErrorAction Stop
    } catch {
        Write-Host "WARN: Could not remove $dist — close DocumentIntelligenceApi.exe if running."
    }
}

$venvTools = Ensure-BuildVenv
$iconIco = Join-Path $AppRoot "assets\app-icon.ico"
if (-not (Test-Path $iconIco)) {
    & $venvTools.Python -m pip install pillow -q
    & $venvTools.Python "$AppRoot\scripts\generate_app_icon.py"
}

$srcRoot = Join-Path $AppRoot "src"
if (-not (Test-Path $srcRoot)) {
    throw "Missing $srcRoot — desktop-electron must include src/"
}

$workspaceSrc = Join-Path $srcRoot "workspace"
if (-not (Test-Path $workspaceSrc)) {
    $workspaceSrc = Join-Path $AppRoot "workspace"
}

Write-Host "==> Pre-build import check"
& $venvTools.Python "$PSScriptRoot\check_desktop_imports.py"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$collectSubmodules = @(
    "backend",
    "api",
    "api.routers",
    "core",
    "core.agents",
    "core.agents.agent_a",
    "core.orchestrator",
    "core.llm",
    "core.llm.providers",
    "core.storage",
    "output",
    "service",
    "db",
    "db.repository",
    "utils",
    "uvicorn",
    "langchain_openai",
    "langchain_deepseek",
    "langextract"
)

$hiddenImports = @(
    "launcher",
    "output",
    "output.result_handler",
    "starter_workflows",
    "workflow_storage",
    "backend.main",
    "backend.bootstrap",
    "backend.paths",
    "backend.local_library",
    "backend.routers.library_local",
    "backend.routers.settings",
    "backend.settings_store",
    "api.main",
    "service.agent_service",
    "core.orchestrator.coordinator",
    "core.orchestrator.executor",
    "core.agents.agent_a",
    "core.agents.agent_a.agent_a",
    "core.agents.agent_b",
    "core.agents.agent_c",
    "core.agents.agent_d",
    "core.agents.conversation_agent",
    "core.agents.document_understand_agent",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on"
)

$pyiArgs = @(
    "--noconfirm",
    "--clean",
    "--noconsole",
    "--name", "DocumentIntelligenceApi",
    "--paths", $srcRoot,
    "--paths", $AppRoot,
    "--add-data", "$AppRoot\frontend\dist;frontend\dist",
    "--add-data", "$AppRoot\data\settings.json.example;data"
)
foreach ($sub in $collectSubmodules) {
    $pyiArgs += @("--collect-submodules", $sub)
}
foreach ($hi in $hiddenImports) {
    $pyiArgs += @("--hidden-import", $hi)
}

foreach ($mod in $excludeModules) {
    $pyiArgs += @("--exclude-module", $mod)
}

if (Test-Path $iconIco) {
    $pyiArgs += @("--icon", $iconIco)
}

if (Test-Path $workspaceSrc) {
    Write-Host "==> Bundling workspace templates from: $workspaceSrc"
    $pyiArgs += @("--add-data", "${workspaceSrc};workspace")
}

$pyiArgs += @("--distpath", $dist, "$AppRoot\server_entry.py")

Write-Host "==> Running PyInstaller (API only, no webview)..."
Set-Location $AppRoot
& $venvTools.PyInstaller @pyiArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$outDir = Join-Path $dist "DocumentIntelligenceApi"
$exe = Join-Path $outDir "DocumentIntelligenceApi.exe"
if (-not (Test-Path $exe)) {
    throw "PyInstaller did not produce: $exe"
}
if (-not (Test-Path (Join-Path $AppRoot "launcher.py"))) {
    throw "Missing launcher.py in desktop-electron (required by server_entry.py)"
}
$outputPy = Join-Path $srcRoot "output\result_handler.py"
if (-not (Test-Path $outputPy)) {
    throw "Missing $outputPy — run scripts\sync_src.ps1 or copy output package from repo src/"
}
if (Test-Path (Join-Path $outDir "_internal\webview")) {
    throw "API bundle incorrectly includes pywebview. Delete dist-api and rerun build_api.ps1"
}
Write-Host ""
Write-Host "API bundle ready:"
Write-Host "  $exe"
