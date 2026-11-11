$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Push-Location $repoRoot

try {
    $venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        & $venvPython tools/app/build_runtime_bundle.py --zip @args
    }
    else {
        uv run python tools/app/build_runtime_bundle.py --zip @args
    }
}
finally {
    Pop-Location
}
