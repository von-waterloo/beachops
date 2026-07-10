# Thin launcher: prefer Docker Windows worker.
$ErrorActionPreference = "Stop"
& (Join-Path $PSScriptRoot "install-windows-worker.ps1") @args
