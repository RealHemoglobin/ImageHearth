"""Prueba de contrato periódica contra el último ComfyUI publicado.

Consulta la última versión de ComfyUI en GitHub, la descarga en una carpeta temporal y
ejecuta la misma comprobación que `contract.py` (nodos y entradas de los workflows), con
el entorno de Python del ComfyUI local. No cambia nada de la instalación: sirve de aviso
temprano de que una versión nueva de ComfyUI rompería una plantilla.

Escribe un log con la fecha y la versión probada en la carpeta de logs de ImageHearth y
sale con 0 si pasa o 1 si falla (también si no puede consultar GitHub o descargar).
"""

import hashlib
import sys
import tarfile
import tempfile
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))

import contract

from imagehearth_mcp.engine import config

RELEASE_API = "https://api.github.com/repos/Comfy-Org/ComfyUI/releases/latest"
ARCHIVE_URL = "https://github.com/Comfy-Org/ComfyUI/archive/refs/tags/{tag}.tar.gz"
TIMEOUT = 60
CHUNK = 1024 * 1024


class LatestError(Exception):
    """No se pudo averiguar o descargar la última versión."""


def latest_tag(session=requests):
    """Etiqueta de la última versión publicada (p. ej. `v0.43.0`)."""
    try:
        response = session.get(
            RELEASE_API, headers={"Accept": "application/vnd.github+json"}, timeout=TIMEOUT
        )
        response.raise_for_status()
        tag = response.json()["tag_name"]
    except (requests.RequestException, ValueError, KeyError) as error:
        raise LatestError(f"Can't read the latest ComfyUI release from GitHub: {error}") from error

    if not isinstance(tag, str) or not tag.replace(".", "").lstrip("v").isalnum():
        raise LatestError(f"GitHub returned an unexpected release tag: {tag!r}")

    return tag


def download(tag, folder, session=requests):
    """Descarga y extrae esa versión en `folder`. Devuelve (carpeta del código, SHA-256)."""
    archive = Path(folder) / "comfyui.tar.gz"
    digest = hashlib.sha256()

    try:
        with session.get(ARCHIVE_URL.format(tag=tag), stream=True, timeout=TIMEOUT) as response:
            response.raise_for_status()

            with open(archive, "wb") as file:
                for chunk in response.iter_content(CHUNK):
                    file.write(chunk)
                    digest.update(chunk)

        extracted = Path(folder) / "source"

        with tarfile.open(archive) as tar:
            tar.extractall(extracted, filter="data")

        return next(extracted.iterdir()), digest.hexdigest()
    except (requests.RequestException, OSError, tarfile.TarError, StopIteration) as error:
        raise LatestError(f"Can't download or unpack ComfyUI {tag}: {error}") from error


def run(session=requests, log_dir=None, verify=contract.verify, now=time.time):
    """Ejecuta la prueba y devuelve (código de salida, ruta del log)."""
    log_dir = Path(log_dir or config.LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(now()))
    lines = [f"ImageHearth contract test against the latest ComfyUI, {stamp}"]
    tag = "unknown"
    code = 1

    try:
        tag = latest_tag(session)
        lines.append(f"Latest ComfyUI release: {tag}")
        pinned = _pinned_version()
        lines.append(f"Pinned by ImageHearth: {pinned}")

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            folder = Path(folder)
            source, sha256 = download(tag, folder, session)
            lines.append(f"Archive SHA-256: {sha256}")
            engine_log = log_dir / f"contract-latest-{stamp}-comfyui.log"
            problems = verify(source, folder, log_file=engine_log)

        lines += problems or ["PASS: every node and input the workflows use exists."]
        code = 1 if problems else 0
    except (LatestError, contract.ContractError) as error:
        lines.append(f"FAIL: {error}")

    lines.append(f"Result: {'PASS' if code == 0 else 'FAIL'} (ComfyUI {tag})")
    log = log_dir / f"contract-latest-{stamp}-{tag}.log"
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return code, log


def _pinned_version():
    from imagehearth_mcp.provisioner import manifest

    return manifest.load().comfyui.version


def main():
    code, log = run()
    print(log.read_text(encoding="utf-8"), end="")
    print(f"Log: {log}")
    sys.exit(code)


if __name__ == "__main__":
    main()
