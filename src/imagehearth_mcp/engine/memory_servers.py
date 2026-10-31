"""Proveedores de memoria para LM Studio, llama.cpp y vLLM.

Solo se actúa sobre un servidor que se identifica como tal: en sus puertos
habituales puede escuchar cualquier otro programa. Lo que su API no permite
descargar se marca con `unloadable: False` y un `advice` para el usuario.
"""

import os
import time

import requests

from imagehearth_mcp.engine import config
from imagehearth_mcp.engine.log import get_logger
from imagehearth_mcp.engine.memory import MemoryProvider, ProviderUnavailable

log = get_logger("memory")

REQUEST_TIMEOUT = 10


def _get(url, unavailable, **options):
    """JSON de un GET, o None si la ruta no existe. Sin respuesta: ProviderUnavailable."""
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT, **options)

        if response.status_code == 404:
            return None

        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as error:
        raise ProviderUnavailable(f"{unavailable} does not respond: {error}") from error


def _wait_until(condition, timeout):
    deadline = time.monotonic() + timeout

    while not condition():
        if time.monotonic() >= deadline:
            return False

        time.sleep(config.POLL_INTERVAL)

    return True


def _restored(provider, models):
    """Comprobación final, como en Ollama: detecta lo expulsado por otro modelo."""
    try:
        active = {model["name"] for model in provider.loaded()}
    except ProviderUnavailable as error:
        log.error("Could not verify the restoration: %s", error)
        active = set()

    return {
        "restored": [m["name"] for m in models if m["name"] in active],
        "failed": [m["name"] for m in models if m["name"] not in active],
    }


def _unload_each(provider, models, unload_one):
    timeout = config.UNLOAD_TIMEOUT
    names = {model["name"] for model in models}

    for model in models:
        log.info("Unloading model: %s", model["name"])
        unload_one(model)

    def released():
        return not names & {model["name"] for model in provider.loaded()}

    if not _wait_until(released, timeout):
        raise TimeoutError(f"{provider.name} did not release {sorted(names)} within {timeout}s.")


def _restore_each(provider, models, load_one):
    for model in models:
        try:
            log.info("Restoring model: %s", model["name"])
            load_one(model)
        except requests.RequestException as error:
            log.error("Error restoring %s: %s", model["name"], error)

    return _restored(provider, models)


class LMStudioProvider(MemoryProvider):
    """API REST v1: lista instancias, las descarga y las vuelve a cargar."""

    name = "lmstudio"
    NO_UNLOAD = (
        "This LM Studio version has no unload API: update it, or eject the model "
        "yourself with `lms unload --all`."
    )

    def _headers(self):
        token = os.environ.get("LM_API_TOKEN")
        return {"Authorization": f"Bearer {token}"} if token else {}

    def _url(self, path):
        return f"{config.LMSTUDIO_API}{path}"

    def loaded(self):
        data = _get(self._url("/api/v1/models"), "LM Studio", headers=self._headers())

        if data is None:
            return self._loaded_legacy()

        if not isinstance(data, dict) or not isinstance(data.get("models"), list):
            raise ProviderUnavailable("The server on the LM Studio port is not LM Studio.")

        found = []

        for model in data["models"]:
            for instance in model.get("loaded_instances") or []:
                found.append(
                    {
                        "name": f"lmstudio/{instance['id']}",
                        "provider": self.name,
                        "instance_id": instance["id"],
                        "key": model["key"],
                        "size_vram": model.get("size_bytes", 0),
                        "context_length": instance.get("config", {}).get("context_length"),
                    }
                )

        return found

    def _loaded_legacy(self):
        data = _get(self._url("/api/v0/models"), "LM Studio", headers=self._headers())

        if not isinstance(data, dict) or not isinstance(data.get("data"), list):
            raise ProviderUnavailable("The server on the LM Studio port is not LM Studio.")

        return [
            {
                "name": f"lmstudio/{model['id']}",
                "provider": self.name,
                "unloadable": False,
                "advice": self.NO_UNLOAD,
            }
            for model in data["data"]
            if model.get("state") == "loaded"
        ]

    def _post(self, path, payload, timeout):
        response = requests.post(
            self._url(path), json=payload, headers=self._headers(), timeout=timeout
        )
        response.raise_for_status()

    def unload(self, models):
        _unload_each(
            self,
            models,
            lambda model: self._post(
                "/api/v1/models/unload",
                {"instance_id": model["instance_id"]},
                config.UNLOAD_TIMEOUT,
            ),
        )

    def restore(self, models):
        def load(model):
            payload = {"model": model["key"]}

            if model.get("context_length"):
                payload["context_length"] = model["context_length"]

            self._post("/api/v1/models/load", payload, config.RESTORE_TIMEOUT)

        return _restore_each(self, models, load)


class LlamaCppProvider(MemoryProvider):
    """El modo router carga y descarga por HTTP; un servidor de un solo modelo no puede."""

    name = "llamacpp"
    NO_UNLOAD = (
        "llama-server can't unload its model over HTTP: stop it while generating, "
        "start it with --sleep-idle-seconds, or use its router mode."
    )

    def _url(self, path):
        return f"{config.LLAMACPP_API}{path}"

    def _router_models(self):
        data = _get(self._url("/models"), "llama-server")
        entries = data.get("data") if isinstance(data, dict) else None

        if isinstance(entries, list) and all(isinstance(e.get("status"), dict) for e in entries):
            return entries or None

        return None

    def loaded(self):
        router = self._router_models()

        if router is not None:
            return [
                {
                    "name": f"llamacpp/{entry['id']}",
                    "provider": self.name,
                    "model_id": entry["id"],
                }
                for entry in router
                if entry["status"].get("value") == "loaded"
            ]

        props = _get(self._url("/props"), "llama-server")

        # El puerto 8080 es muy común: solo llama.cpp publica estos campos.
        if not isinstance(props, dict) or "default_generation_settings" not in props:
            raise ProviderUnavailable("The server on the llama.cpp port is not llama-server.")

        if props.get("is_sleeping"):
            return []

        path = props.get("model_path") or "model"
        return [
            {
                "name": f"llamacpp/{path.replace(chr(92), '/').rsplit('/', 1)[-1]}",
                "provider": self.name,
                "unloadable": False,
                "advice": self.NO_UNLOAD,
            }
        ]

    def _post(self, path, model, timeout):
        response = requests.post(
            self._url(path), json={"model": model["model_id"]}, timeout=timeout
        )
        response.raise_for_status()

    def unload(self, models):
        _unload_each(
            self,
            models,
            lambda model: self._post("/models/unload", model, config.UNLOAD_TIMEOUT),
        )

    def restore(self, models):
        def load(model):
            self._post("/models/load", model, config.RESTORE_TIMEOUT)
            _wait_until(
                lambda: model["name"] in {m["name"] for m in self.loaded()},
                config.RESTORE_TIMEOUT,
            )

        return _restore_each(self, models, load)


class VllmProvider(MemoryProvider):
    """El modo de reposo libera la GPU, pero exige arrancar vLLM con él activado."""

    name = "vllm"
    NO_UNLOAD = (
        "This vLLM server can't release its GPU memory: restart it with "
        "VLLM_SERVER_DEV_MODE=1 and --enable-sleep-mode, or stop it while generating."
    )

    def _url(self, path):
        return f"{config.VLLM_API}{path}"

    def _model_names(self):
        data = _get(self._url("/v1/models"), "vLLM")
        entries = data.get("data") if isinstance(data, dict) else None

        if not isinstance(entries, list) or not all(
            entry.get("owned_by") == "vllm" for entry in entries
        ):
            raise ProviderUnavailable("The server on the vLLM port is not vLLM.")

        return [entry["id"] for entry in entries]

    def loaded(self):
        names = self._model_names()
        sleeping = _get(self._url("/is_sleeping"), "vLLM")

        if sleeping is None:
            return [
                {
                    "name": f"vllm/{name}",
                    "provider": self.name,
                    "unloadable": False,
                    "advice": self.NO_UNLOAD,
                }
                for name in names
            ]

        if sleeping.get("is_sleeping"):
            return []

        return [{"name": f"vllm/{name}", "provider": self.name} for name in names]

    def unload(self, models):
        response = requests.post(
            self._url("/sleep"), params={"level": 1}, timeout=config.UNLOAD_TIMEOUT
        )
        response.raise_for_status()

        if not _wait_until(lambda: not self.loaded(), config.UNLOAD_TIMEOUT):
            raise TimeoutError(
                f"vLLM did not go to sleep within {config.UNLOAD_TIMEOUT}s."
            )

    def restore(self, models):
        try:
            requests.post(
                self._url("/wake_up"), timeout=config.RESTORE_TIMEOUT
            ).raise_for_status()
        except requests.RequestException as error:
            log.error("Error waking up vLLM: %s", error)

        return _restored(self, models)
