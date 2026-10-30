import io
import os
import re
import shutil
import time
import uuid

import requests
from PIL import Image

from engine import config
from engine.log import get_logger

log = get_logger("comfyui")


def submit(workflow):
    response = requests.post(
        f"{config.COMFY_API}/prompt",
        json={"prompt": workflow},
        timeout=60,
    )

    if response.status_code == 400:
        raise RuntimeError(f"ComfyUI rechazó el workflow: {_rejection(response)}")

    response.raise_for_status()
    result = response.json()

    if "prompt_id" not in result:
        raise RuntimeError(f"ComfyUI no aceptó el workflow: {result}")

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
                raise RuntimeError(f"Error en ComfyUI: {_execution_error(status)}")

            if status.get("completed"):
                for node in history.get("outputs", {}).values():
                    for image in node.get("images", []):
                        if image.get("type") == "output":
                            return image

                raise RuntimeError("ComfyUI terminó sin producir imágenes.")

        if on_poll:
            on_poll()

        time.sleep(config.POLL_INTERVAL)

    raise TimeoutError(f"ComfyUI no terminó en los {timeout} segundos disponibles.")


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
            f"ComfyUI devolvió una imagen no válida: {error}"
        ) from error

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{uuid.uuid4().hex}.tmp")

    try:
        temporary.write_bytes(response.content)
        os.replace(temporary, destination)
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
        log.warning("Interrumpiendo el trabajo %s", prompt_id)
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


def free_models(timeout=None):
    """Pide liberar la VRAM y espera a que ComfyUI lo confirme."""
    timeout = config.FREE_TIMEOUT if timeout is None else timeout

    response = requests.post(
        f"{config.COMFY_API}/free",
        json={"unload_models": True, "free_memory": True},
        timeout=60,
    )
    response.raise_for_status()

    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        status = requests.get(
            f"{config.COMFY_API}/imageengine/status",
            timeout=10,
        )
        status.raise_for_status()

        data = status.json()
        models = data.get("loaded_models", [])

        if data.get("models_loaded") == 0 and not models:
            return

        log.info("Esperando a que ComfyUI libere modelos: %s", models)
        time.sleep(config.POLL_INTERVAL)

    raise RuntimeError("ComfyUI no ha confirmado la descarga de todos sus modelos.")


def _rejection(response):
    try:
        data = response.json()
    except ValueError:
        return response.text[:500]

    details = [data.get("error", {}).get("message", "Solicitud no válida")]

    for node_id, node in data.get("node_errors", {}).items():
        for error in node.get("errors", []):
            details.append(
                f"nodo {node_id} ({node.get('class_type')}): "
                f"{error.get('message')} {error.get('details', '')}".strip()
            )

    return "; ".join(details)


def _execution_error(status):
    for message in status.get("messages", []):
        if isinstance(message, list) and message[0] == "execution_error":
            detail = message[1]
            return (
                f"nodo {detail.get('node_id')} ({detail.get('node_type')}): "
                f"{detail.get('exception_message', '').strip()}"
            )

    return str(status)
