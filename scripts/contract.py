"""Prueba de contrato: ComfyUI en CPU expone todos los nodos que usan los workflows.

No descarga modelos ni usa la GPU. Arranca una instancia propia en un puerto
libre, así que no toca la que esté en uso. Los nodos fijados en el manifiesto, como
ComfyUI-GGUF, se instalan en una carpeta temporal: el ComfyUI local no cambia.
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

import requests

from imagehearth_mcp.engine import config
from imagehearth_mcp.platform import paths, processes, spawn
from imagehearth_mcp.provisioner import comfyui, manifest

START_TIMEOUT = 180


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def workflow_nodes():
    nodes = {}

    for file in sorted(config.WORKFLOWS_DIR.glob("*.json")):
        workflow = json.loads(file.read_text(encoding="utf-8"))

        for node in workflow.values():
            if isinstance(node, dict) and "class_type" in node:
                nodes.setdefault(node["class_type"], set()).add(file.name)

    return nodes


def install_nodes(base_dir):
    """Nodos fijados y sus dependencias en `base_dir`. Devuelve la ruta de paquetes."""
    packages = base_dir / "packages"

    for pin in manifest.load().nodes.values():
        archive = base_dir / f"{pin.name}.tar.gz"
        comfyui._download_archive(pin, archive)
        extracted = base_dir / "extracted"

        with tarfile.open(archive) as tar:
            tar.extractall(extracted, filter="data")

        top = next(extracted.iterdir())
        destination = base_dir / "custom_nodes" / pin.folder
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(top), str(destination))
        subprocess.run(
            [
                "uv",
                "pip",
                "install",
                "--quiet",
                "--python",
                str(paths.find_venv_python(config.COMFY_DIR)),
                "--target",
                str(packages),
                *pin.packages,
            ],
            check=True,
        )

    return packages


def main():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
        check_contract(Path(folder))


def check_contract(base_dir):
    python = paths.venv_python(config.COMFY_DIR / "venv")

    if not python.exists() or not (config.COMFY_DIR / "main.py").exists():
        sys.exit(f"ComfyUI not found in {config.COMFY_DIR} (set IMAGEHEARTH_COMFY_DIR).")

    packages = install_nodes(base_dir)
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    process = subprocess.Popen(
        [
            str(python),
            "main.py",
            "--cpu",
            "--listen",
            "127.0.0.1",
            "--port",
            str(port),
            "--base-directory",
            str(base_dir),
        ],
        cwd=config.COMFY_DIR,
        env={**os.environ, "PYTHONPATH": str(packages)},
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **spawn.detached_options(),
    )

    try:
        deadline = time.monotonic() + START_TIMEOUT

        while True:
            if process.poll() is not None:
                sys.exit(f"ComfyUI exited at startup (code {process.returncode}).")

            try:
                available = requests.get(f"{base}/object_info", timeout=10).json()
                break
            except (requests.RequestException, ValueError):
                if time.monotonic() >= deadline:
                    sys.exit(f"ComfyUI did not respond within {START_TIMEOUT} seconds.")

                time.sleep(1)

        missing = {
            name: sorted(files)
            for name, files in workflow_nodes().items()
            if name not in available
        }

        if missing:
            for name, files in missing.items():
                print(f"MISSING {name} (used by {', '.join(files)})")

            sys.exit(1)

        print(f"OK: {len(workflow_nodes())} node types used by the workflows exist.")
    finally:
        if not processes.terminate(process.pid, 30):
            processes.kill(process.pid)


if __name__ == "__main__":
    main()
