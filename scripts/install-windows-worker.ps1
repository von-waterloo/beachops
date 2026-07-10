# Install / run BeachOps Windows worker (outbound local Cursor execution plane).
#
# Prerequisites:
#   - Python 3.10+ with beachops installed (pip install -e .)
#   - Cursor IDE / cursor-sdk available on this machine
#   - Env vars (set permanently or in the task):
#       BEACHOPS_API_URL=https://beachops.example.com
#       BEACHOPS_WORKER_TOKEN=<token from POST /api/workers/register>
#       BEACHOPS_WORKER_HOSTNAME=<optional; defaults to computer name>
#       CURSOR_API_KEY=...
#       CURSOR_MODEL=composer-2.5   # optional
#       WORKSPACE_PATH=D:\Work\Cursor Bot\data\workspace  # optional
#       BEACHOPS_LOCAL_CWD=D:\Work\some-repo              # optional discovery cwd
#
# Usage:
#   .\scripts\install-windows-worker.ps1              # register Scheduled Task
#   .\scripts\install-windows-worker.ps1 -RunOnce     # run in foreground now
#   .\scripts\install-windows-worker.ps1 -Unregister  # remove the task

[CmdletBinding()]
param(
    [switch]$RunOnce,
    [switch]$Unregister,
    [string]$TaskName = "BeachOpsWindowsWorker",
    [string]$PythonExe = "",
    [string]$RepoRoot = ""
)

$ErrorActionPreference = "Stop"

if (-not $RepoRoot) {
    $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

if (-not $PythonExe) {
    $venvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        $PythonExe = $venvPython
    } else {
        $PythonExe = (Get-Command python -ErrorAction Stop).Source
    }
}

$moduleArgs = @("-m", "beachops.windows_worker")

if ($Unregister) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Removed scheduled task '$TaskName' (if it existed)."
    exit 0
}

if ($RunOnce) {
    Write-Host "Starting Windows worker in foreground..."
    Write-Host "  python: $PythonExe"
    Write-Host "  cwd:    $RepoRoot"
    Set-Location $RepoRoot
    & $PythonExe @moduleArgs
    exit $LASTEXITCODE
}

$action = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument "-m beachops.windows_worker" `
    -WorkingDirectory $RepoRoot

$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet `
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
    -Settings $settings `
    -Principal $principal `
    -Force | Out-Null

Write-Host "Registered scheduled task '$TaskName'."
Write-Host "It starts at logon and runs: $PythonExe -m beachops.windows_worker"
Write-Host ""
Write-Host "Manual run (no task):"
Write-Host "  cd `"$RepoRoot`""
Write-Host "  `$env:BEACHOPS_API_URL='https://...'"
Write-Host "  `$env:BEACHOPS_WORKER_TOKEN='...'"
Write-Host "  `$env:CURSOR_API_KEY='...'"
Write-Host "  & `"$PythonExe`" -m beachops.windows_worker"
Write-Host ""
Write-Host "Or: .\scripts\install-windows-worker.ps1 -RunOnce"
