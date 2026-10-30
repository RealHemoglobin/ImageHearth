import fcntl
import time
from contextlib import contextmanager
from pathlib import Path

import requests

from engine.comfyui_manager import start as ensure_comfyui
from engine.ollama_manager import (
    get_loaded_models,
    unload_all,
    restore_models,
)

COMFY_API = "http://127.0.0.1:8188"
LOCK_FILE = Path.home() / "AI" / "ImageEngine" / "engine.lock"


def free_comfyui_models(timeout=120):
    response = requests.post(
        f"{COMFY_API}/free",
        json={"unload_models": True, "free_memory": True},
        timeout=60,
    )
    response.raise_for_status()

    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        status = requests.get(
            f"{COMFY_API}/imageengine/status",
            timeout=10,
        )
        status.raise_for_status()

        data = status.json()
        models = data.get("loaded_models", [])

        if data.get("models_loaded") == 0 and not models:
            return

        print(f"Esperando a que ComfyUI libere modelos: {models}")
        time.sleep(2)

    raise RuntimeError(
        "ComfyUI no ha confirmado la descarga de todos sus modelos."
    )


@contextmanager
def generation_session():
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)

    with LOCK_FILE.open("w") as lock:
        print("Esperando turno de generación...")
        fcntl.flock(lock, fcntl.LOCK_EX)

        original_models = []
        ollama_unloaded = False
        generation_started = False

        try:
            ensure_comfyui()

            original_models = get_loaded_models()
            print("Modelos Ollama:", [m["name"] for m in original_models])

            if original_models:
                original_models = unload_all()
                ollama_unloaded = True

            generation_started = True
            yield

        finally:
            if generation_started:
                print("Liberando modelos de ComfyUI...")

                # Si falla, no se restaura Ollama.
                free_comfyui_models()
                print("Liberación de ComfyUI completada.")

            if ollama_unloaded:
                print("Restaurando modelos Ollama...")
                result = restore_models(original_models)
                print("Resultado de restauración:", result)

                if result["failed"]:
                    raise RuntimeError(
                        f"No se pudieron restaurar: {result['failed']}"
                    )

            fcntl.flock(lock, fcntl.LOCK_UN)


if __name__ == "__main__":
    with generation_session():
        print("Sesión de prueba correcta.")
