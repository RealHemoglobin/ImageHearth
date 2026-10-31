import io
import os
import re
import shutil
import time
import uuid

import requests
from PIL import Image

from imagehearth_mcp.engine import config
from imagehearth_mcp.engine.log import get_logger
from imagehearth_mcp.platform import files

log = get_logger("comfyui")


def submit(workflow):
    response = requests.post(
        f"{config.COMFY_API}/prompt",
        json={"prompt": workflow},
        timeout=60,
    )

    if response.status_code == 400:
        raise RuntimeError(f"ComfyUI rejected the workflow: {_rejection(response)}")

    response.raise_for_status()
    result = response.json()

    if "prompt_id" not in result:
        raise RuntimeError(f"ComfyUI did not accept the workflow: {result}")

    return result["prompt_id"]


def wait_for_image(prompt_id, timeout, on_poll=None):
    """Espera al trabajo y devuelve la primera imagen de salida."""
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        response = requests.get(
            f"{config.COMFY_API}/history/{prompt_id}",
            timeout=15,
        )
        response.raise_for_status()

        history = response.json().get(prompt_id)

        if history:
            status = history.get("status", {})

            if status.get("status_str") == "error":
                raise RuntimeError(f"ComfyUI error: {_execution_error(status)}")

            if status.get("completed"):
                for node in history.get("outputs", {}).values():
                    for image in node.get("images", []):
                        if image.get("type") == "output":
                            return image

                raise RuntimeError("ComfyUI finished without producing images.")

        if on_poll:
            on_poll()

        time.sleep(config.POLL_INTERVAL)

    raise TimeoutError(f"ComfyUI did not finish within the {timeout} seconds available.")


def download_image(image, destination):
    """Descarga y verifica la imagen antes de publicarla en su destino."""
    response = requests.get(
        f"{config.COMFY_API}/view",
        params={
            "filename": image["filename"],
            "subfolder": image.get("subfolder", ""),
            "type": "output",
        },
        timeout=120,
    )
    response.raise_for_status()

    try:
        with Image.open(io.BytesIO(response.content)) as picture:
            picture.verify()
    except Exception as error:
        raise RuntimeError(
            f"ComfyUI returned an invalid image: {error}"
        ) from error

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{uuid.uuid4().hex}.tmp")

    try:
        temporary.write_bytes(response.content)
        files.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)

    return destination


def remove_output_copy(image):
    """Borra de ComfyUI/output la copia de una imagen ya guardada."""
    subfolder = image.get("subfolder", "")

    if subfolder != config.COMFY_SUBFOLDER:
        return

    filename = os.path.basename(image["filename"])
    (config.COMFY_DIR / "output" / subfolder / filename).unlink(missing_ok=True)


def run_input_subfolder(run_id):
    return f"{config.COMFY_SUBFOLDER}/{run_id}"


def remove_run_inputs(run_id):
    """Borra únicamente las referencias subidas por esta ejecución."""
    if not re.fullmatch(r"[0-9a-f]+", run_id or ""):
        return

    folder = config.COMFY_DIR / "input" / config.COMFY_SUBFOLDER / run_id

    if folder.exists():
        shutil.rmtree(folder)


def queue_prompt_ids():
    response = requests.get(f"{config.COMFY_API}/queue", timeout=10)
    response.raise_for_status()
    data = response.json()

    return {
        "running": [item[1] for item in data.get("queue_running", [])],
        "pending": [item[1] for item in data.get("queue_pending", [])],
    }


def cancel(prompt_id):
    """Cancela solo el trabajo indicado y espera a que abandone la cola."""
    queue = queue_prompt_ids()

    if prompt_id in queue["pending"]:
        requests.post(
            f"{config.COMFY_API}/queue",
            json={"delete": [prompt_id]},
            timeout=10,
        ).raise_for_status()

    if prompt_id in queue["running"]:
        log.warning("Interrupting job %s", prompt_id)
        requests.post(
            f"{config.COMFY_API}/interrupt",
            json={"prompt_id": prompt_id},
            timeout=10,
        ).raise_for_status()

    deadline = time.monotonic() + config.CANCEL_TIMEOUT

    while time.monotonic() < deadline:
        queue = queue_prompt_ids()

        if prompt_id not in queue["running"] + queue["pending"]:
            return True

        time.sleep(config.POLL_INTERVAL)

    return False


class StatusNodeMissing(RuntimeError):
    """El nodo imagehearth_status no está instalado o es una versión antigua."""


def status_node():
    """Datos del nodo imagehearth_status; StatusNodeMissing si no sirve."""
    response = requests.get(
        f"{config.COMFY_API}{config.STATUS_ROUTE}",
        timeout=10,
    )

    if response.status_code == 404:
        raise StatusNodeMissing(
            f"The {config.STATUS_NODE} node is not installed in ComfyUI."
        )

    response.raise_for_status()
    data = response.json()

    if data.get("version", 0) < config.STATUS_NODE_VERSION:
        raise StatusNodeMissing(
            f"The {config.STATUS_NODE} node in ComfyUI is outdated "
            f"(version {data.get('version')}, expected {config.STATUS_NODE_VERSION})."
        )

    return data


def free_models(timeout=None):
    """Pide liberar la VRAM y espera a que ComfyUI lo confirme.

    Lanza StatusNodeMissing si no hay nodo con el que confirmarlo.
    """
    timeout = config.FREE_TIMEOUT if timeout is None else timeout

    response = requests.post(
        f"{config.COMFY_API}/free",
        json={"unload_models": True, "free_memory": True},
        timeout=60,
    )
    response.raise_for_status()

    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        data = status_node()
        models = data.get("loaded_models", [])

        if data.get("models_loaded") == 0 and not models:
            return

        log.info("Waiting for ComfyUI to release models: %s", models)
        time.sleep(config.POLL_INTERVAL)

    raise RuntimeError("ComfyUI did not confirm that all its models were unloaded.")


def _rejection(response):
    try:
        data = response.json()
    except ValueError:
        return response.text[:500]

    details = [data.get("error", {}).get("message", "Invalid request")]

    for node_id, node in data.get("node_errors", {}).items():
        for error in node.get("errors", []):
            details.append(
                f"node {node_id} ({node.get('class_type')}): "
                f"{error.get('message')} {error.get('details', '')}".strip()
            )

    return "; ".join(details)


def _execution_error(status):
    for message in status.get("messages", []):
        if isinstance(message, list) and message[0] == "execution_error":
            detail = message[1]
            return (
                f"node {detail.get('node_id')} ({detail.get('node_type')}): "
                f"{detail.get('exception_message', '').strip()}"
            )

    return str(status)
