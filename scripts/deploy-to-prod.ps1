# Deploy BeachOps to prod (185.244.49.94) via pscp + plink.
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
$ArchiveName = "beachops-deploy.tgz"

if (-not (Test-Path $Ppk)) {
    throw "SSH key not found: $Ppk"
}
Push-Location $RepoRoot
try {
    $archive = Join-Path $env:TEMP $ArchiveName
    $bootstrapUpload = Join-Path $env:TEMP "beachops-prod-deploy.sh"
    if (Test-Path $archive) { Remove-Item $archive -Force }
    if (Test-Path $bootstrapUpload) { Remove-Item $bootstrapUpload -Force }
    $bootstrapSource = Join-Path $RepoRoot "scripts\prod-deploy.sh"
    $bootstrapText = [IO.File]::ReadAllText($bootstrapSource).Replace("`r`n", "`n")
    [IO.File]::WriteAllText(
        $bootstrapUpload,
        $bootstrapText,
        [Text.UTF8Encoding]::new($false)
    )

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
        --exclude="node_modules" `
        --exclude="dist" `
        -C $RepoRoot `
        pyproject.toml README.md alembic.ini alembic src sql webapp scripts docker-compose.yml docker-compose.bind.yml Dockerfile entrypoint.sh .env.example
    if ($LASTEXITCODE -ne 0) { throw "Failed to create deployment archive" }

    Write-Host "Uploading to ${RemoteUser}@${HostAddr}:${RemoteDir}..."
    echo y | plink -ssh -l $RemoteUser -i $Ppk $HostAddr "mkdir -p $RemoteDir"
    if ($LASTEXITCODE -ne 0) { throw "Failed to prepare remote directory" }
    pscp -i $Ppk $archive "${RemoteUser}@${HostAddr}:${RemoteDir}/${ArchiveName}"
    if ($LASTEXITCODE -ne 0) { throw "Failed to upload deployment archive" }
    pscp -i $Ppk $bootstrapUpload "${RemoteUser}@${HostAddr}:${RemoteDir}/prod-deploy.sh"
    if ($LASTEXITCODE -ne 0) { throw "Failed to upload deployment bootstrap" }

    Write-Host "Backing up database, extracting, rebuilding and starting BeachOps..."
    $remoteCmd = "cd $RemoteDir && chmod +x prod-deploy.sh && ./prod-deploy.sh"
    echo y | plink -ssh -l $RemoteUser -i $Ppk $HostAddr $remoteCmd
    if ($LASTEXITCODE -ne 0) { throw "Production deploy failed" }

    Write-Host ""
    Write-Host "Deploy finished."
    Write-Host "  - Pre-deploy PostgreSQL backup created on server"
    Write-Host "  - Alembic migrations run through the one-shot migrate service"
    Write-Host "  - Bot, worker, API, Redis and Mini App recreated"
    Write-Host ""
    Write-Host "IMPORTANT: do not run 'python -m beachops' locally with the prod TG_BOT_TOKEN."
    Write-Host "           Two pollers with one token cause Conflict errors and random behaviour."
}
finally {
    if ($archive -and (Test-Path $archive)) { Remove-Item $archive -Force }
    if ($bootstrapUpload -and (Test-Path $bootstrapUpload)) {
        Remove-Item $bootstrapUpload -Force
    }
    Pop-Location
}
