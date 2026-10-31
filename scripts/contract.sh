#!/bin/sh
# Prueba de contrato contra el ComfyUI local: ver scripts/contract.py.
set -eu

cd "$(dirname "$0")/.."

uv run python scripts/contract.py
