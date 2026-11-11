param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 3000
)

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Push-Location $repoRoot

try {
    $minPort = 3000
    $maxPort = 3010

    if ($Port -lt $minPort -or $Port -gt $maxPort) {
        throw "Port must be within $minPort-$maxPort. Received: $Port"
    }

    function Test-PortAvailable {
        param([int]$CheckPort)
        try {
            $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $CheckPort)
            $listener.Start()
            $listener.Stop()
            return $true
        }
        catch {
            return $false
        }
    }

    $selectedPort = $null
    for ($p = $Port; $p -le $maxPort; $p++) {
        if (Test-PortAvailable -CheckPort $p) {
            $selectedPort = $p
            break
        }
    }
    if ($null -eq $selectedPort) {
        for ($p = $minPort; $p -lt $Port; $p++) {
            if (Test-PortAvailable -CheckPort $p) {
                $selectedPort = $p
                break
            }
        }
    }

    if ($null -eq $selectedPort) {
        throw "No free port found in allowed range $minPort-$maxPort. Stop another process in that range and retry."
    }

    $python = Join-Path $repoRoot ".venv\Scripts\python.exe"

    if (-not (Test-Path $python)) {
        Write-Host ".venv not found. Creating and syncing with uv..."
        uv sync
    }

    if ($selectedPort -ne $Port) {
        Write-Host "Requested port $Port is busy. Using first available port in range: $selectedPort"
    }

    Write-Host "Launching LGR Sim Workbench on http://$BindHost`:$selectedPort"
    uv run python src/app/run_local_app.py --host $BindHost --port $selectedPort
}
finally {
    Pop-Location
}
