import fcntl
import time
import uuid
from contextlib import contextmanager

import requests

from imagehearth_mcp.engine import (
    comfyui_client,
    comfyui_manager,
    config,
    ollama_manager,
    state,
)
from imagehearth_mcp.engine.log import get_logger
from imagehearth_mcp.engine.log import run_id as log_run_id

log = get_logger("orchestrator")

MIB = 1024 * 1024


class RecoveryRequired(RuntimeError):
    """ComfyUI retiene la VRAM y no se puede cargar Ollama con seguridad."""


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
        loaded = ollama_manager.get_loaded_models()

        if loaded:
            log.warning(
                "Modelos Ollama recargados: %s",
                [model["name"] for model in loaded],
            )
            self.add_models(loaded)
            ollama_manager.unload_all(loaded)

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
            loaded = ollama_manager.get_loaded_models()
        except requests.RequestException as error:
            log.warning("No se pudo consultar Ollama: %s", error)
            return

        new = [m for m in loaded if m["name"] not in self._warned_models]

        if new:
            self._warned_models.update(m["name"] for m in new)
            self.add_models(new)
            self.warn(
                "Se cargó un modelo Ollama durante la generación: "
                f"{[m['name'] for m in new]}"
            )


def _acquire_lock(lock, timeout):
    deadline = time.monotonic() + timeout
    announced = False

    while True:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except BlockingIOError:
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    "ImageHearth sigue ocupado con otra generación "
                    f"después de {timeout} segundos."
                ) from None

        if not announced:
            log.info("Esperando turno de generación...")
            announced = True

        time.sleep(0.2)


@contextmanager
def _engine_lock(timeout):
    config.LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Cerrar el fichero libera el flock, incluso tras una excepción.
    with config.LOCK_FILE.open("a") as lock:
        _acquire_lock(lock, timeout)
        yield


def is_busy():
    config.LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)

    with config.LOCK_FILE.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return False
        except BlockingIOError:
            return True


def _foreign_jobs(own_prompt_id):
    queue = comfyui_client.queue_prompt_ids()
    return [
        prompt_id
        for prompt_id in queue["running"] + queue["pending"]
        if prompt_id != own_prompt_id
    ]


def _confirm_dead_comfyui(models, warnings):
    """Un proceso muerto no retiene VRAM; la memoria libre lo corrobora."""
    required = sum(model.get("size_vram", 0) for model in models) // MIB
    free = comfyui_manager.gpu_free_mib()

    if free is None:
        warnings.append(
            "No se pudo consultar la VRAM con nvidia-smi; "
            "se confía en que ComfyUI no tiene procesos activos."
        )
        return

    if free < required:
        raise RecoveryRequired(
            f"ComfyUI está detenido, pero solo hay {free} MiB libres "
            f"y Ollama necesita {required} MiB."
        )


def release_comfyui(models, prompt_id, warnings):
    """Libera ComfyUI o lanza RecoveryRequired si no es seguro continuar."""
    if comfyui_manager.is_dead():
        log.info("ComfyUI está detenido; no retiene VRAM.")
        _confirm_dead_comfyui(models, warnings)
        return

    last_error = None

    try:
        if prompt_id and not comfyui_client.cancel(prompt_id):
            warnings.append(f"ComfyUI no canceló el trabajo {prompt_id}.")
    except requests.RequestException as error:
        last_error = error

    for attempt in range(config.FREE_ATTEMPTS):
        try:
            comfyui_client.free_models()
            log.info("Liberación de ComfyUI completada.")
            return
        except (requests.RequestException, RuntimeError) as error:
            last_error = error
            log.warning("Intento %s de liberar ComfyUI: %s", attempt + 1, error)

    if comfyui_manager.is_dead():
        _confirm_dead_comfyui(models, warnings)
        return

    try:
        foreign = _foreign_jobs(prompt_id)
    except requests.RequestException as error:
        raise RecoveryRequired(
            "ComfyUI no libera la VRAM y no responde para comprobar su cola: "
            f"{error}"
        ) from last_error

    if foreign:
        raise RecoveryRequired(
            "ComfyUI no libera la VRAM y no se reinicia porque tiene "
            f"trabajos en cola: {foreign}"
        ) from last_error

    log.warning("Reiniciando ComfyUI para recuperar la VRAM.")

    try:
        comfyui_manager.restart()
        comfyui_client.free_models()
    except (OSError, requests.RequestException, RuntimeError) as error:
        raise RecoveryRequired(
            f"ComfyUI no libera la VRAM y el reinicio falló: {error}"
        ) from error

    warnings.append("ComfyUI se reinició para recuperar la VRAM.")


def _remove_inputs(run_id, warnings):
    try:
        comfyui_client.remove_run_inputs(run_id)
    except OSError as error:
        warnings.append(f"No se pudieron borrar las referencias temporales: {error}")


def _restore(models, warnings):
    """Restaura Ollama; devuelve los modelos que no han vuelto."""
    if not models:
        return []

    state.write(phase=state.RESTORING)

    try:
        result = ollama_manager.restore_models(models)
    except Exception as error:
        warnings.append(f"Error restaurando Ollama: {error}")
        return models

    log.info("Resultado de restauración: %s", result)
    failed = set(result["failed"])
    return [model for model in models if model["name"] in failed]


def _mark_recovery(session, reason):
    session.warn(f"{reason} Estado: recovery_required.")

    try:
        state.write(phase=state.RECOVERY_REQUIRED, reason=reason)
    except OSError as error:
        session.warn(f"No se pudo guardar el estado de la sesión: {error}")


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
            _mark_recovery(session, f"No se pudieron restaurar: {names}.")
        else:
            state.clear()

    except RecoveryRequired as error:
        _mark_recovery(session, str(error))

    except Exception as error:
        log.exception("Fallo inesperado al cerrar la sesión")
        _mark_recovery(session, f"Fallo al cerrar la sesión: {error}.")


def _reconcile():
    """Recupera una sesión anterior; devuelve los modelos a restaurar."""
    pending = state.read()

    if not pending:
        return []

    log.warning("Recuperando sesión pendiente: %s", pending.get("phase"))
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
            reason = f"No se pudieron restaurar: {names}"
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

                loaded = ollama_manager.get_loaded_models()
                log.info("Modelos Ollama: %s", [m["name"] for m in loaded])

                if loaded:
                    session.add_models(loaded)
                    ollama_manager.unload_all(loaded)

                session.generation_started = True
                yield session

            except Exception as error:
                _finish(session)

                if session.warnings:
                    raise RuntimeError(
                        f"{error} | Además: {'; '.join(session.warnings)}"
                    ) from error

                raise

            except BaseException:
                _finish(session)
                raise

            else:
                _finish(session)

        finally:
            log_run_id.reset(token)

