# Prueba de contrato contra el ComfyUI local: ver scripts\contract.py.
$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

uv run python scripts\contract.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
