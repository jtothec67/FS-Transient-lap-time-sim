param(
    [string]$AppName = "LGRSimWorkbench"
)

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$distRoot = Join-Path $repoRoot "dist"
$bundleDir = Join-Path $distRoot $AppName
$zipPath = Join-Path $distRoot "$AppName.zip"
$env:UV_CACHE_DIR = Join-Path $repoRoot ".uv-cache"

$vehicleRuntimeFiles = @(
    "datasets/vehicle/PU_data/Honda_CBR_600RR_RPM_vs_Peak_Power.csv",
    "datasets/vehicle/tyre_data/round_6_12_psi_longit_load_tyredata_parsed.csv",
    "datasets/vehicle/tyre_data/round_8_12_psi_lateral_load_tyredata_parsed.csv"
)

$optionalChatConfigFiles = @(
    "config\deepseek_key",
    "config\deepseek_key.enc"
)

$pyInstallerExcludes = @(
    "--exclude-module", "matplotlib",
    "--exclude-module", "seaborn",
    "--exclude-module", "PIL",
    "--exclude-module", "tkinter",
    "--exclude-module", "_tkinter",
    "--exclude-module", "botocore",
    "--exclude-module", "boto3",
    "--exclude-module", "s3transfer",
    "--exclude-module", "lxml",
    "--exclude-module", "pytest",
    "--exclude-module", "py"
)

function Copy-RuntimePath {
    param(
        [string]$RelativePath
    )

    $source = Join-Path $repoRoot $RelativePath
    $destination = Join-Path $bundleDir $RelativePath

    if (-not (Test-Path -LiteralPath $source)) {
        throw "Required runtime path not found: $source"
    }

    $destinationParent = Split-Path -Parent $destination
    if (-not (Test-Path -LiteralPath $destinationParent)) {
        New-Item -ItemType Directory -Path $destinationParent -Force | Out-Null
    }

    if (Test-Path -LiteralPath $source -PathType Container) {
        Copy-Item -LiteralPath $source -Destination $destination -Recurse -Force
    }
    else {
        Copy-Item -LiteralPath $source -Destination $destination -Force
    }
}

function Copy-OptionalRuntimePath {
    param(
        [string]$RelativePath
    )

    $source = Join-Path $repoRoot $RelativePath
    if (-not (Test-Path -LiteralPath $source)) {
        return $false
    }

    Copy-RuntimePath -RelativePath $RelativePath
    return $true
}

function Invoke-CheckedExternalCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Description,
        [Parameter(Mandatory = $true)]
        [scriptblock]$ScriptBlock
    )

    & $ScriptBlock
    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed with exit code $LASTEXITCODE."
    }
}

function Test-SystemPythonBuildReadiness {
    python -c "import PyInstaller, uvicorn, fastapi, httpx, matplotlib, numpy, pandas, scipy, seaborn" *> $null
    return $LASTEXITCODE -eq 0
}

Push-Location $repoRoot

try {
    if (Test-Path -LiteralPath $bundleDir) {
        Remove-Item -LiteralPath $bundleDir -Recurse -Force
    }
    if (Test-Path -LiteralPath $zipPath) {
        Remove-Item -LiteralPath $zipPath -Force
    }

    if (Test-SystemPythonBuildReadiness) {
        Write-Host "Using current Python environment for PyInstaller build."
        Invoke-CheckedExternalCommand -Description "PyInstaller build" -ScriptBlock {
            python -m PyInstaller --noconfirm --clean --name $AppName --onedir `
                --add-data "src/app/static;app/static" `
                --add-data "config.json;." `
                --add-data "parameters.json;." `
                --add-data "datasets/tracks;datasets/tracks" `
                --add-data "datasets/vehicle/PU_data/Honda_CBR_600RR_RPM_vs_Peak_Power.csv;datasets/vehicle/PU_data" `
                --add-data "datasets/vehicle/tyre_data/round_6_12_psi_longit_load_tyredata_parsed.csv;datasets/vehicle/tyre_data" `
                --add-data "datasets/vehicle/tyre_data/round_8_12_psi_lateral_load_tyredata_parsed.csv;datasets/vehicle/tyre_data" `
                --add-data "docs/lessons;docs/lessons" `
                $pyInstallerExcludes `
                src/app/run_local_app.py
        }
    }
    else {
        Write-Host "System Python is not build-ready. Falling back to uv-managed PyInstaller."
        Invoke-CheckedExternalCommand -Description "PyInstaller build" -ScriptBlock {
            uv run --with pyinstaller pyinstaller --noconfirm --clean --name $AppName --onedir `
                --add-data "src/app/static;app/static" `
                --add-data "config.json;." `
                --add-data "parameters.json;." `
                --add-data "datasets/tracks;datasets/tracks" `
                --add-data "datasets/vehicle/PU_data/Honda_CBR_600RR_RPM_vs_Peak_Power.csv;datasets/vehicle/PU_data" `
                --add-data "datasets/vehicle/tyre_data/round_6_12_psi_longit_load_tyredata_parsed.csv;datasets/vehicle/tyre_data" `
                --add-data "datasets/vehicle/tyre_data/round_8_12_psi_lateral_load_tyredata_parsed.csv;datasets/vehicle/tyre_data" `
                --add-data "docs/lessons;docs/lessons" `
                $pyInstallerExcludes `
                src/app/run_local_app.py
        }
    }

    $exePath = Join-Path $bundleDir "$AppName.exe"
    if (-not (Test-Path -LiteralPath $exePath)) {
        throw "PyInstaller did not produce the expected executable: $exePath"
    }

    $runtimePaths = @(
        "config.json",
        "parameters.json",
        "datasets\tracks",
        "docs\lessons",
        "src\app",
        "src\simulator",
        "src\track",
        "src\vehicle",
        "src\main.py"
    )

    $runtimePaths += $vehicleRuntimeFiles

    foreach ($relativePath in $runtimePaths) {
        Copy-RuntimePath -RelativePath $relativePath
    }

    $launcherPath = Join-Path $bundleDir "Start LGR Sim Workbench.bat"
    $launcherContent = @"
@echo off
setlocal
cd /d "%~dp0"
start "" "%~dp0$AppName.exe"
"@
    $launcherContent | Set-Content -LiteralPath $launcherPath -Encoding ASCII

    $readmePath = Join-Path $bundleDir "README-WINDOWS.txt"
    $readmeContent = @'
LGR Sim Workbench (Windows)
===========================

How to run:
1. Unzip the folder.
2. Double-click Start LGR Sim Workbench.bat.
3. Wait for your browser to open automatically.

Notes:
- Do not move files out of this folder. Keep the folder contents together.
- If Windows SmartScreen appears, click More info then Run anyway.
- The local app will choose the first free port in the range 3000-3010.
- Chat is optional. To enable it, create config\deepseek_key from config\deepseek_key.example and paste in your API key.

Default files shipped in this bundle:
- config.json
- parameters.json
- datasets\tracks
- datasets\vehicle\PU_data\Honda_CBR_600RR_RPM_vs_Peak_Power.csv
- datasets\vehicle\tyre_data\round_6_12_psi_longit_load_tyredata_parsed.csv
- datasets\vehicle\tyre_data\round_8_12_psi_lateral_load_tyredata_parsed.csv
- docs\lessons
'@
    $readmeContent | Set-Content -LiteralPath $readmePath -Encoding ASCII

    $chatConfigDir = Join-Path $bundleDir "config"
    New-Item -ItemType Directory -Path $chatConfigDir -Force | Out-Null

    $hasBundledChatKey = $false
    foreach ($relativePath in $optionalChatConfigFiles) {
        $copied = Copy-OptionalRuntimePath -RelativePath $relativePath
        if ($relativePath -eq "config\deepseek_key" -and $copied) {
            $hasBundledChatKey = $true
        }
    }

    $keyExamplePath = Join-Path $chatConfigDir "deepseek_key.example"
    $keyExampleContent = @'
Paste your DeepSeek API key into a file named:

deepseek_key

Keep this file in the same folder as this example:

config\deepseek_key

The file should contain only the raw API key text, with no quotes or extra lines.
'@
    $keyExampleContent | Set-Content -LiteralPath $keyExamplePath -Encoding ASCII

    if ($hasBundledChatKey) {
        Add-Content -LiteralPath $readmePath -Encoding ASCII -Value "`r`nChat has been preconfigured in this bundle.`r`n"
    }

    Compress-Archive -LiteralPath $bundleDir -DestinationPath $zipPath -Force

    Write-Host "Build complete. Folder output: $bundleDir"
    Write-Host "Zip output: $zipPath"
    Write-Host "End users should run: Start LGR Sim Workbench.bat"
}
finally {
    Pop-Location
}
