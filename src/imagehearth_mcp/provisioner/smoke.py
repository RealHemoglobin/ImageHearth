"""Prueba de humo: una imagen pequeña a través del motor real.

Corre en un proceso aparte porque `config` se calcula al importarse y setup
acaba de escribir `config.toml`.
"""

import subprocess
import sys
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from imagehearth_mcp.provisioner import ProvisionError

SIZE = 512
TIMEOUT = 1800
PROMPT = "a red bicycle on a beach"

# Primera coincidencia: indicio en el error -> capa afectada.
LAYERS = (
    ("not found in", "ComfyUI"),
    ("Python not found", "ComfyUI environment"),
    ("exited at startup", "ComfyUI environment"),
    ("did not respond", "ComfyUI"),
    ("Port ", "port"),
    ("safetensors", "models"),
    ("out of memory", "GPU"),
    ("CUDA", "GPU"),
)


def affected_layer(message):
    for hint, layer in LAYERS:
        if hint in message:
            return layer

    return "engine"


def run_smoke(run=subprocess.run):
    """Genera la imagen y devuelve su ruta tras comprobar que es válida."""
    print("Generating a test image...")

    try:
        result = run(
            [sys.executable, "-m", "imagehearth_mcp.provisioner.smoke"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ProvisionError(
            f"The test image failed in the engine layer: {error}. "
            "Run `imagehearth-mcp doctor` for details."
        ) from error

    if result.returncode != 0:
        lines = (result.stderr or "").strip().splitlines()
        message = lines[-1] if lines else f"exit code {result.returncode}"
        raise ProvisionError(
            f"The test image failed in the {affected_layer(message)} layer: {message} "
            "Run `imagehearth-mcp doctor` for details."
        )

    lines = result.stdout.strip().splitlines()
    path = Path(lines[0]) if lines else None

    try:
        with Image.open(path) as image:
            image.verify()
    except (OSError, TypeError, AttributeError, UnidentifiedImageError) as error:
        raise ProvisionError(
            f"The test image at {path} is not valid: {error}. "
            "Run `imagehearth-mcp doctor` for details."
        ) from error

    return path


def main():
    from imagehearth_mcp.engine.image_router import create_image

    try:
        print(create_image(PROMPT, mode="generate", width=SIZE, height=SIZE))
    except Exception as error:
        print(str(error).replace("\n", " "), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
