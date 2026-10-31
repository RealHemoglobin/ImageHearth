import time
import uuid
from contextlib import contextmanager

import requests

from imagehearth_mcp.engine import (
    comfyui_client,
    comfyui_manager,
    config,
    gpu,
    memory,
    state,
)
from imagehearth_mcp.engine.log import get_logger
from imagehearth_mcp.engine.log import run_id as log_run_id
from imagehearth_mcp.platform import locks

log = get_logger("orchestrator")

MIB = 1024 * 1024


class RecoveryRequired(RuntimeError):
    """ComfyUI holds the VRAM and it is not safe to reload the models."""


def _loaded_models():
    """Modelos cargados en el proveedor; sin proveedor activo no hay ninguno."""
    try:
        return memory.get_provider().loaded()
    except memory.ProviderUnavailable as error:
        log.info("No memory provider available: %s", error)
        return []


class Session:
    def __init__(self, run_id, models):
        self.run_id = run_id
        self.models = models
        self.prompt_id = None
        self.warnings = []
        self.generation_started = False
        self._warned_models = set()
        self._next_ollama_check = 0.0

    def warn(self, message):
        log.warning(message)
        self.warnings.append(message)

    def add_models(self, models):
        known = {model["name"] for model in self.models}
        self.models.extend(m for m in models if m["name"] not in known)
        state.write(models=self.models)

    def submit(self, workflow):
        # Otro agente ha podido recargar un modelo desde el inicio de la sesión.
        loaded = _loaded_models()

        if loaded:
            log.warning(
                "Ollama models reloaded: %s",
                [model["name"] for model in loaded],
            )
            self.add_models(loaded)
            memory.get_provider().unload(loaded)

        self.prompt_id = comfyui_client.submit(workflow)
        state.write(phase=state.GENERATING, prompt_id=self.prompt_id)
        return self.prompt_id

    def prompt_finished(self):
        self.prompt_id = None
        state.write(prompt_id=None)

    def check_ollama(self):
        """Avisa si se carga un modelo durante la generación, sin expulsarlo."""
        now = time.monotonic()

        if now < self._next_ollama_check:
            return

        self._next_ollama_check = now + config.OLLAMA_CHECK_INTERVAL

        try:
            loaded = memory.get_provider().loaded()
        except memory.ProviderUnavailable as error:
            log.warning("Could not query Ollama: %s", error)
            return

        new = [m for m in loaded if m["name"] not in self._warned_models]

        if new:
            self._warned_models.update(m["name"] for m in new)
            self.add_models(new)
            self.warn(
                "An Ollama model was loaded during generation: "
                f"{[m['name'] for m in new]}"
            )


@contextmanager
def _engine_lock(timeout):
    try:
        lock = locks.acquire(
            config.LOCK_FILE,
            timeout,
            on_wait=lambda: log.info("Waiting for a generation turn..."),
        )
    except TimeoutError:
        raise TimeoutError(
            "ImageHearth is still busy with another generation "
            f"after {timeout} seconds."
        ) from None

    try:
        yield
    finally:
        lock.release()


def is_busy():
    return locks.is_locked(config.LOCK_FILE)


def _foreign_jobs(own_prompt_id):
    queue = comfyui_client.queue_prompt_ids()
    return [
        prompt_id
        for prompt_id in queue["running"] + queue["pending"]
        if prompt_id != own_prompt_id
    ]


def _required_mib(models):
    return sum(model.get("size_vram", 0) for model in models) // MIB


def _confirm_dead_comfyui(models, warnings):
    """Un proceso muerto no retiene VRAM; la memoria libre lo corrobora."""
    required = _required_mib(models)
    free = gpu.free_mib()

    if free is None:
        warnings.append(
            "Could not query free GPU memory; assuming ComfyUI has no "
            "active processes."
        )
        return

    if free < required:
        raise RecoveryRequired(
            f"ComfyUI is stopped, but only {free} MiB are free "
            f"and the models need {required} MiB."
        )


def _confirm_memory_freed(models, warnings):
    """Sin nodo de estado, la memoria libre confirma que ComfyUI soltó los modelos."""
    required = _required_mib(models)
    deadline = time.monotonic() + config.FREE_TIMEOUT

    while True:
        free = gpu.free_mib()

        if free is None:
            warnings.append(
                "Could not query free GPU memory; ComfyUI's release "
                "could not be verified."
            )
            return

        if free >= required:
            return

        if time.monotonic() >= deadline:
            raise RuntimeError(
                f"Only {free} MiB of GPU memory are free after asking "
                f"ComfyUI to release its models; {required} MiB are needed."
            )

        time.sleep(config.POLL_INTERVAL)


def _free_comfyui(models, warnings):
    """Pide a ComfyUI que libere la VRAM y confirma que lo ha hecho."""
    try:
        comfyui_client.free_models()
    except comfyui_client.StatusNodeMissing as error:
        message = (
            f"{error} Free GPU memory is checked through /system_stats "
            "instead; install the node for a more reliable check."
        )

        if message not in warnings:
            warnings.append(message)

        _confirm_memory_freed(models, warnings)


def release_comfyui(models, prompt_id, warnings):
    """Libera ComfyUI o lanza RecoveryRequired si no es seguro continuar."""
    if comfyui_manager.is_dead():
        log.info("ComfyUI is stopped; it holds no VRAM.")
        _confirm_dead_comfyui(models, warnings)
        return

    last_error = None

    try:
        if prompt_id and not comfyui_client.cancel(prompt_id):
            warnings.append(f"ComfyUI did not cancel job {prompt_id}.")
    except requests.RequestException as error:
        last_error = error

    for attempt in range(config.FREE_ATTEMPTS):
        try:
            _free_comfyui(models, warnings)
            log.info("ComfyUI release completed.")
            return
        except (requests.RequestException, RuntimeError) as error:
            last_error = error
            log.warning("Attempt %s to release ComfyUI: %s", attempt + 1, error)

    if comfyui_manager.is_dead():
        _confirm_dead_comfyui(models, warnings)
        return

    try:
        foreign = _foreign_jobs(prompt_id)
    except requests.RequestException as error:
        raise RecoveryRequired(
            "ComfyUI does not release the VRAM and does not respond to "
            f"check its queue: {error}"
        ) from last_error

    if foreign:
        raise RecoveryRequired(
            "ComfyUI does not release the VRAM and will not be restarted "
            f"because it has queued jobs: {foreign}"
        ) from last_error

    log.warning("Restarting ComfyUI to recover the VRAM.")

    try:
        comfyui_manager.restart()
        _free_comfyui(models, warnings)
    except (OSError, requests.RequestException, RuntimeError) as error:
        raise RecoveryRequired(
            f"ComfyUI does not release the VRAM and the restart failed: {error}"
        ) from error

    warnings.append("ComfyUI was restarted to recover the VRAM.")


def _remove_inputs(run_id, warnings):
    try:
        comfyui_client.remove_run_inputs(run_id)
    except OSError as error:
        warnings.append(f"Could not delete the temporary references: {error}")


def _restore(models, warnings):
    """Restaura los modelos; devuelve los que no han vuelto."""
    if not models:
        return []

    state.write(phase=state.RESTORING)

    try:
        result = memory.get_provider().restore(models)
    except Exception as error:
        warnings.append(f"Error restoring Ollama: {error}")
        return models

    log.info("Restoration result: %s", result)
    failed = set(result["failed"])
    return [model for model in models if model["name"] in failed]


def _mark_recovery(session, reason):
    session.warn(f"{reason} State: recovery_required.")

    try:
        state.write(phase=state.RECOVERY_REQUIRED, reason=reason)
    except OSError as error:
        session.warn(f"Could not save the session state: {error}")


def _finish(session):
    """Limpia la sesión. Nunca lanza: los fallos quedan como advertencias."""
    try:
        if session.generation_started:
            state.write(phase=state.RELEASING)
            release_comfyui(session.models, session.prompt_id, session.warnings)

        _remove_inputs(session.run_id, session.warnings)
        failed = _restore(session.models, session.warnings)

        if failed:
            state.write(models=failed)
            names = [model["name"] for model in failed]
            _mark_recovery(session, f"Could not restore: {names}.")
        else:
            state.clear()

    except RecoveryRequired as error:
        _mark_recovery(session, str(error))

    except Exception as error:
        log.exception("Unexpected failure while closing the session")
        _mark_recovery(session, f"Failed to close the session: {error}.")


def _reconcile():
    """Recupera una sesión anterior; devuelve los modelos a restaurar."""
    pending = state.read()

    if not pending:
        return []

    log.warning("Recovering pending session: %s", pending.get("phase"))
    models = pending.get("models", [])
    warnings = []

    try:
        release_comfyui(models, pending.get("prompt_id"), warnings)
    except RecoveryRequired as error:
        state.write(phase=state.RECOVERY_REQUIRED, reason=str(error))
        raise

    for message in warnings:
        log.warning(message)

    _remove_inputs(pending.get("run_id"), warnings)
    return models


def recover():
    """Resuelve una sesión pendiente sin iniciar una generación."""
    with _engine_lock(timeout=5):
        if not state.read():
            return {"status": "ready", "restored": []}

        models = _reconcile()
        warnings = []
        failed = _restore(models, warnings)

        if failed:
            names = [model["name"] for model in failed]
            reason = f"Could not restore: {names}"
            state.write(phase=state.RECOVERY_REQUIRED, models=failed, reason=reason)
            raise RecoveryRequired(reason)

        state.clear()
        return {
            "status": "ready",
            "restored": [model["name"] for model in models],
            "warnings": warnings,
        }


def ensure_comfyui():
    """Arranca ComfyUI salvo que una sesión activa ya lo esté gestionando."""
    with _engine_lock(timeout=5):
        comfyui_manager.start()


@contextmanager
def generation_session():
    with _engine_lock(config.LOCK_TIMEOUT):
        run_id = uuid.uuid4().hex[:12]
        token = log_run_id.set(run_id)

        try:
            # Antes de escribir el nuevo estado: si falla, el anterior se conserva.
            adopted = _reconcile()
            session = Session(run_id, adopted)
            state.write(
                phase=state.UNLOADING,
                run_id=run_id,
                models=session.models,
                prompt_id=None,
                reason=None,
            )

            try:
                comfyui_manager.start()

                loaded = _loaded_models()
                log.info("Ollama models: %s", [m["name"] for m in loaded])

                if loaded:
                    session.add_models(loaded)
                    memory.get_provider().unload(loaded)

                session.generation_started = True
                yield session

            except Exception as error:
                _finish(session)

                if session.warnings:
                    raise RuntimeError(
                        f"{error} | Also: {'; '.join(session.warnings)}"
                    ) from error

                raise

            except BaseException:
                _finish(session)
                raise

            else:
                _finish(session)

        finally:
            log_run_id.reset(token)

