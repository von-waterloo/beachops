# Deploy tg-cursor-bot to prod (185.244.49.94) via pscp + plink.
# Requires: PuTTY plink/pscp, key C:\Users\vonwa\.ssh\const.ppk, local .env
#
# Restart strategy: stop + rm old bot container, then force-recreate.
# Ensures no stale long-polling process keeps the Telegram token busy.

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Ppk = "C:\Users\vonwa\.ssh\const.ppk"
$HostAddr = "185.244.49.94"
$RemoteUser = "const"
$RemoteDir = "/home/const/tg-cursor-bot"
$ArchiveName = "tg-cursor-bot-deploy.tgz"

if (-not (Test-Path $Ppk)) {
    throw "SSH key not found: $Ppk"
}
if (-not (Test-Path (Join-Path $RepoRoot ".env"))) {
    throw ".env missing in repo root. Create from .env.example before deploy."
}

Push-Location $RepoRoot
try {
    $archive = Join-Path $env:TEMP $ArchiveName
    if (Test-Path $archive) { Remove-Item $archive -Force }

    Write-Host "Creating archive..."
    tar -czf $archive `
        --exclude=".venv" `
        --exclude="venv" `
        --exclude="__pycache__" `
        --exclude="*.egg-info" `
        --exclude=".git" `
        --exclude="data" `
        --exclude=".pytest_cache" `
        --exclude="htmlcov" `
        -C $RepoRoot `
        pyproject.toml README.md alembic.ini alembic src sql docker-compose.yml docker-compose.bind.yml Dockerfile entrypoint.sh .env.example .env

    Write-Host "Uploading to ${RemoteUser}@${HostAddr}:${RemoteDir}..."
    echo y | plink -ssh -l $RemoteUser -i $Ppk $HostAddr "mkdir -p $RemoteDir"
    pscp -i $Ppk $archive "${RemoteUser}@${HostAddr}:${RemoteDir}/${ArchiveName}"

    Write-Host "Extracting, stopping old bot, rebuilding, starting..."
    # Single line — avoids CRLF breakage in plink heredocs on Windows.
    $remoteCmd = @(
        "set -e"
        "cd $RemoteDir"
        "tar -xzf $ArchiveName"
        "rm -f $ArchiveName"
        "docker compose stop -t 15 bot || true"
        "docker compose rm -f bot || true"
        "docker compose build bot"
        "docker compose up -d --force-recreate --remove-orphans --no-deps bot"
        "sleep 3"
        "docker compose ps"
        "docker compose logs --tail=12 bot"
    ) -join " && "

    echo y | plink -ssh -l $RemoteUser -i $Ppk $HostAddr $remoteCmd

    Write-Host ""
    Write-Host "Deploy finished."
    Write-Host "  - Old bot container stopped and removed before start"
    Write-Host "  - Migrations run automatically on bot container start (entrypoint)"
    Write-Host ""
    Write-Host "IMPORTANT: do not run 'python -m tg_cursor_bot' locally with the prod TG_BOT_TOKEN."
    Write-Host "           Two pollers with one token cause Conflict errors and random behaviour."
}
finally {
    Pop-Location
}
