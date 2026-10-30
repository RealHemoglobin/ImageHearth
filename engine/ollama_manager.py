import time
from datetime import UTC, datetime

import requests

from engine import config
from engine.log import get_logger

log = get_logger("ollama")

ONE_YEAR = 365 * 24 * 3600
MIN_KEEP_ALIVE = 60


def get_loaded_models():
    response = requests.get(f"{config.OLLAMA_API}/api/ps", timeout=10)
    response.raise_for_status()
    return response.json().get("models", [])


def _load_request(name, payload, timeout):
    response = requests.post(
        f"{config.OLLAMA_API}/api/generate",
        json={"model": name, "prompt": "", **payload},
        timeout=timeout,
    )

    # Los modelos de embeddings no admiten /api/generate.
    if response.status_code == 400:
        response = requests.post(
            f"{config.OLLAMA_API}/api/embed",
            json={"model": name, "input": "", **payload},
            timeout=timeout,
        )

    response.raise_for_status()


def unload_model(name, timeout=180):
    _load_request(name, {"keep_alive": 0}, timeout)


def unload_all(models, timeout=None):
    """Descarga los modelos indicados con un plazo global."""
    timeout = config.UNLOAD_TIMEOUT if timeout is None else timeout
    deadline = time.monotonic() + timeout

    for model in models:
        log.info("Descargando modelo Ollama: %s", model["name"])
        unload_model(model["name"], timeout=_remaining(deadline))

    while True:
        remaining = get_loaded_models()

        if not remaining:
            log.info("Todos los modelos de Ollama están descargados.")
            return

        if time.monotonic() >= deadline:
            raise TimeoutError(
                "Ollama no liberó todos los modelos en "
                f"{timeout}s. Siguen activos: "
                f"{[model['name'] for model in remaining]}"
            )

        log.info(
            "Esperando descarga de Ollama: %s",
            [model["name"] for model in remaining],
        )
        time.sleep(config.POLL_INTERVAL)


def restore_options(model):
    """Parámetros que devuelven el modelo a su configuración original."""
    payload = {}
    keep_alive = _keep_alive(model.get("expires_at"))

    if keep_alive is not None:
        payload["keep_alive"] = keep_alive

    if model.get("context_length"):
        payload["options"] = {"num_ctx": model["context_length"]}

    return payload


def restore_models(models, timeout=None):
    """Restaura los modelos con un plazo global para todos ellos."""
    timeout = config.RESTORE_TIMEOUT if timeout is None else timeout
    deadline = time.monotonic() + timeout

    for model in models:
        name = model["name"]

        try:
            if name in _active_names():
                continue

            log.info("Restaurando modelo Ollama: %s", name)
            _load_request(name, restore_options(model), _remaining(deadline))

            while name not in _active_names():
                if time.monotonic() >= deadline:
                    log.error("Plazo agotado restaurando %s", name)
                    break
                time.sleep(config.POLL_INTERVAL)

        except (requests.RequestException, TimeoutError) as error:
            log.error("Error restaurando %s: %s", name, error)

    # La comprobación final detecta modelos expulsados por otro posterior.
    try:
        active = _active_names()
    except requests.RequestException as error:
        log.error("No se pudo comprobar la restauración: %s", error)
        active = set()

    restored = [m["name"] for m in models if m["name"] in active]
    failed = [m["name"] for m in models if m["name"] not in active]

    return {"restored": restored, "failed": failed}


def _active_names():
    return {model["name"] for model in get_loaded_models()}


def _remaining(deadline):
    remaining = deadline - time.monotonic()

    if remaining <= 0:
        raise TimeoutError("Plazo global de Ollama agotado.")

    return remaining


def _keep_alive(expires_at):
    if not expires_at:
        return None

    try:
        expires = datetime.fromisoformat(expires_at)
    except ValueError:
        return None

    seconds = int((expires - datetime.now(UTC)).total_seconds())

    if seconds > ONE_YEAR:
        return -1

    if seconds <= 0:
        return None

    return f"{max(seconds, MIN_KEEP_ALIVE)}s"


if __name__ == "__main__":
    print("Modelos activos:", [m["name"] for m in get_loaded_models()])
