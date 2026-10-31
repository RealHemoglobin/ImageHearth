#!/bin/sh
# Verificación local, sustituye al CI: lint, tests y tests contra el wheel instalado.
set -eu

cd "$(dirname "$0")/.."

uv sync --locked
uv run ruff check .
uv run pytest

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

uv build --wheel --out-dir "$tmp/dist"
uv venv -q "$tmp/env"
uv pip install -q --python "$tmp/env/bin/python" "$tmp"/dist/*.whl pytest

# Fuera del repositorio, para que no se importe src/.
(cd "$tmp" && "$tmp/env/bin/python" -c "
import imagehearth_mcp, sys
print(imagehearth_mcp.__file__)
sys.exit('site-packages' not in imagehearth_mcp.__file__)")

"$tmp/env/bin/python" -m pytest tests
