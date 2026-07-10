# Install / run BeachOps Windows worker as a Docker Desktop container.
# Container uses restart: unless-stopped - comes up with Docker Desktop / PC boot
# (enable Docker Desktop -> Settings -> General -> Start when you sign in).
#
# Prerequisites:
#   - Docker Desktop (Linux containers)
#   - .env.windows-worker with BEACHOPS_API_URL, BEACHOPS_WORKER_TOKEN, CURSOR_API_KEY
#
# Usage:
#   .\scripts\install-windows-worker.ps1              # build + up -d
#   .\scripts\install-windows-worker.ps1 -RunOnce     # foreground logs (still in Docker)
#   .\scripts\install-windows-worker.ps1 -Unregister  # stop + remove container
#   .\scripts\install-windows-worker.ps1 -Native      # legacy: Scheduled Task (needs admin)

[CmdletBinding()]
param(
    [switch]$RunOnce,
    [switch]$Unregister,
    [switch]$Native,
    [string]$TaskName = "BeachOpsWindowsWorker",
    [string]$PythonExe = "",
    [string]$RepoRoot = ""
)

$ErrorActionPreference = "Stop"

if (-not $RepoRoot) {
    $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

$ComposeFile = Join-Path $RepoRoot "docker-compose.windows-worker.yml"
$EnvFile = Join-Path $RepoRoot ".env.windows-worker"
$Project = "beachops-windows-worker"

function Stop-NativeWindowsWorkers {
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.CommandLine -and (
                $_.CommandLine -like "*beachops.windows_worker*" -or
                $_.CommandLine -like "*run-windows-worker.ps1*"
            )
        } |
        ForEach-Object {
            Write-Host "Stopping native worker PID $($_.ProcessId)"
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
}

function Assert-Docker {
    $null = Get-Command docker -ErrorAction Stop
    docker info 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Desktop is not running. Start it, then re-run this script."
    }
}

function Assert-EnvFile {
    if (-not (Test-Path $EnvFile)) {
        $example = Join-Path $RepoRoot ".env.windows-worker.example"
        throw "Missing $EnvFile - copy from $example and fill BEACHOPS_API_URL / BEACHOPS_WORKER_TOKEN / CURSOR_API_KEY"
    }
    $raw = Get-Content $EnvFile -Raw
    foreach ($key in @("BEACHOPS_API_URL", "BEACHOPS_WORKER_TOKEN", "CURSOR_API_KEY")) {
        if ($raw -notmatch "(?m)^$key=.+") {
            throw "$EnvFile must set $key"
        }
    }
}

function Ensure-DockerAutoStart {
    $settings = Join-Path $env:APPDATA "Docker\settings-store.json"
    if (-not (Test-Path $settings)) { return }
    try {
        $json = Get-Content $settings -Raw | ConvertFrom-Json
        if ($json.PSObject.Properties.Name -contains "AutoStart" -and $json.AutoStart -eq $true) {
            Write-Host "Docker Desktop AutoStart already enabled."
            return
        }
        $json | Add-Member -NotePropertyName AutoStart -NotePropertyValue $true -Force
        $json | ConvertTo-Json -Depth 20 | Set-Content $settings -Encoding UTF8
        Write-Host "Enabled Docker Desktop AutoStart (sign-in)."
    } catch {
        Write-Host "Could not update Docker AutoStart (open Docker Desktop -> Settings -> General)."
    }
}

if ($Native) {
    if ($Unregister) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
        Write-Host "Removed scheduled task '$TaskName' (if it existed)."
        exit 0
    }
    if (-not $PythonExe) {
        $venvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
        if (Test-Path $venvPython) { $PythonExe = $venvPython }
        else { $PythonExe = (Get-Command python -ErrorAction Stop).Source }
    }
    Assert-EnvFile
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^([^#=]+)=(.*)$') {
            Set-Item -Path ("Env:" + $matches[1]) -Value $matches[2]
        }
    }
    if ($RunOnce) {
        Set-Location $RepoRoot
        & $PythonExe -m beachops.windows_worker
        exit $LASTEXITCODE
    }
    $action = New-ScheduledTaskAction `
        -Execute $PythonExe `
        -Argument "-m beachops.windows_worker" `
        -WorkingDirectory $RepoRoot
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $taskSettings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -RestartCount 3 `
        -RestartInterval (New-TimeSpan -Minutes 1) `
        -ExecutionTimeLimit (New-TimeSpan -Days 0)
    $principal = New-ScheduledTaskPrincipal `
        -UserId $env:USERNAME `
        -LogonType Interactive `
        -RunLevel Limited
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $taskSettings `
        -Principal $principal `
        -Force | Out-Null
    Write-Host "Registered scheduled task '$TaskName' (legacy native mode)."
    exit 0
}

# --- Docker path (default) ---
Assert-Docker
Assert-EnvFile
Ensure-DockerAutoStart
Stop-NativeWindowsWorkers

Push-Location $RepoRoot
try {
    if ($Unregister) {
        docker compose -p $Project -f $ComposeFile down --remove-orphans
        if ($LASTEXITCODE -ne 0) { throw "docker compose down failed" }
        Write-Host "Stopped and removed Windows worker container."
        exit 0
    }

    Write-Host "Building and starting Windows worker container..."
    docker compose -p $Project -f $ComposeFile up -d --build
    if ($LASTEXITCODE -ne 0) { throw "docker compose up failed" }

    docker compose -p $Project -f $ComposeFile ps
    Write-Host ""
    Write-Host "Windows worker is up (restart: unless-stopped)."
    Write-Host ("  Logs:  docker compose -p {0} -f `"{1}`" logs -f windows-worker" -f $Project, $ComposeFile)
    Write-Host "  Stop:  .\scripts\install-windows-worker.ps1 -Unregister"
    Write-Host ""
    Write-Host "Ensure Docker Desktop starts at sign-in so the container comes up with the PC."

    if ($RunOnce) {
        docker compose -p $Project -f $ComposeFile logs -f windows-worker
    }
}
finally {
    Pop-Location
}
