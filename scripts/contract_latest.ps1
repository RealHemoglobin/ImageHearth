# Prueba de contrato contra el último ComfyUI publicado: ver scripts\contract_latest.py.
$ErrorActionPreference = "Stop"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Installing uv with its official installer (https://astral.sh/uv)..."
    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}

Set-Location (Join-Path $PSScriptRoot "..")

uv run python scripts\contract_latest.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
