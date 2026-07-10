$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
if (-not $root) { $root = "D:\Work\Cursor Bot" }
Get-Content (Join-Path $root ".env.windows-worker") | ForEach-Object {
  if ($_ -match "^([^#=]+)=(.*)$") { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
Set-Location $root
& (Join-Path $root ".venv\Scripts\python.exe") -m beachops.windows_worker
