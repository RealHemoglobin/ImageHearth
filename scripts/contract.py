"""Prueba de contrato: ComfyUI en CPU expone todos los nodos que usan los workflows.

No descarga modelos ni usa la GPU. Arranca una instancia propia en un puerto
libre, así que no toca la que esté en uso. Los nodos fijados en el manifiesto, como
ComfyUI-GGUF, se instalan en una carpeta temporal: el ComfyUI local no cambia.
"""

import contextlib
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


LORA_WORKFLOW = "sdxl_base.json with 3 chained LoRAs"


def lora_workflow():
    """`sdxl_base` as the engine builds it with the most LoRAs a request can have."""
    from imagehearth_mcp.engine import loras, workflow_runner

    catalog = manifest.load().loras
    chosen = [loras.Selected(lora, lora.weight) for lora in list(catalog.values())[: loras.MAX_LORAS]]
    template = json.loads((config.WORKFLOWS_DIR / "sdxl_base.json").read_text(encoding="utf-8"))
    return workflow_runner.apply_loras(template, chosen)


def workflows():
    found = {
        file.name: json.loads(file.read_text(encoding="utf-8"))
        for file in sorted(config.WORKFLOWS_DIR.glob("*.json"))
    }
    found[LORA_WORKFLOW] = lora_workflow()
    return found


def workflow_nodes():
    nodes = {}

    for name, workflow in workflows().items():
        for node in workflow.values():
            if isinstance(node, dict) and "class_type" in node:
                nodes.setdefault(node["class_type"], set()).add(name)

    return nodes


def unknown_inputs(available):
    """Inputs of every workflow (and of the LoRA one) that ComfyUI's node doesn't declare.

    Returns (workflow, "Node id: input") pairs. Connections and literals are checked alike:
    a renamed input is the way a ComfyUI update breaks a template.
    """
    wrong = []

    for name, workflow in workflows().items():
        for key, node in workflow.items():
            if not isinstance(node, dict) or "class_type" not in node:
                continue

            declared = available[node["class_type"]]["input"]
            names = {*declared.get("required", {}), *declared.get("optional", {})}
            wrong += [
                (name, f"{node['class_type']} {key}: {item}")
                for item in node.get("inputs", {})
                if item not in names
            ]

    return wrong


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


class ContractError(Exception):
    """ComfyUI no llegó a responder: no se pudo comprobar nada."""


def verify(source_dir, base_dir, python=None, log_file=None):
    """Arranca el ComfyUI de `source_dir` en CPU y lo compara con los workflows.

    `python` es el intérprete con el que arrancarlo (por defecto, el entorno del ComfyUI
    local). Devuelve la lista de problemas, vacía si todo cuadra, y lanza `ContractError`
    si ComfyUI no arranca. La salida de ComfyUI va a `log_file` si se da.
    """
    source_dir = Path(source_dir)
    python = python or paths.venv_python(config.COMFY_DIR / "venv")

    if not Path(python).exists() or not (source_dir / "main.py").exists():
        raise ContractError(
            f"ComfyUI not found in {source_dir} or its Python environment is missing "
            f"({python}); set IMAGEHEARTH_COMFY_DIR."
        )

    packages = install_nodes(base_dir)
    port = free_port()

    with open(log_file, "ab") if log_file else contextlib.nullcontext() as log:
        return _run(source_dir, base_dir, python, packages, port, log)


def _run(source_dir, base_dir, python, packages, port, log):
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
        cwd=source_dir,
        env={**os.environ, "PYTHONPATH": str(packages)},
        stdin=subprocess.DEVNULL,
        stdout=log or subprocess.DEVNULL,
        stderr=subprocess.STDOUT if log else subprocess.DEVNULL,
        **spawn.detached_options(),
    )

    try:
        deadline = time.monotonic() + START_TIMEOUT

        while True:
            if process.poll() is not None:
                raise ContractError(f"ComfyUI exited at startup (code {process.returncode}).")

            try:
                available = requests.get(f"{base}/object_info", timeout=10).json()
                break
            except (requests.RequestException, ValueError):
                if time.monotonic() >= deadline:
                    raise ContractError(
                        f"ComfyUI did not respond within {START_TIMEOUT} seconds."
                    ) from None

                time.sleep(1)

        return compare(available)
    finally:
        if not processes.terminate(process.pid, 30):
            processes.kill(process.pid)


def compare(available):
    """Problemas entre los workflows y los nodos que ComfyUI declara (`/object_info`)."""
    problems = [
        f"MISSING {name} (used by {', '.join(sorted(files))})"
        for name, files in workflow_nodes().items()
        if name not in available
    ]

    if problems:
        return problems

    return [f"UNKNOWN INPUT {item} ({name})" for name, item in unknown_inputs(available)]


def report(problems):
    """Imprime el resultado y devuelve el código de salida."""
    for problem in problems:
        print(problem)

    if problems:
        return 1

    print(f"OK: {len(workflow_nodes())} node types used by the workflows exist.")
    print(f"OK: the inputs of the {len(workflows())} workflows exist.")
    return 0


def main():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
        try:
            problems = verify(config.COMFY_DIR, Path(folder))
        except ContractError as error:
            sys.exit(str(error))

    sys.exit(report(problems))


if __name__ == "__main__":
    main()
