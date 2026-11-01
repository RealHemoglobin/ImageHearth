# Prueba de contrato contra el ComfyUI local: ver scripts\contract.py.
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

uv run python scripts\contract.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
