#!/bin/sh
# Prueba de contrato contra el último ComfyUI publicado: ver scripts/contract_latest.py.
# Pensado para programarlo (cron o un temporizador de systemd): docs/releasing.md.
set -eu

cd "$(dirname "$0")/.."

uv run python scripts/contract_latest.py
