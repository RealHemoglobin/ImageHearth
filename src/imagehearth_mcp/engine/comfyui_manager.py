import json
import socket
import subprocess
import time

import requests

from imagehearth_mcp.engine import config
from imagehearth_mcp.engine.log import get_logger
from imagehearth_mcp.platform import files, paths, processes, spawn

log = get_logger("comfyui")

STOP_TIMEOUT = 30


def is_running():
    try:
        response = requests.get(f"{config.COMFY_API}/system_stats", timeout=3)
        return response.status_code == 200
    except requests.RequestException:
        return False


def port_is_open():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(3)
        return sock.connect_ex((config.COMFY_HOST, config.COMFY_PORT)) == 0


def find_processes():
    """PID de los procesos main.py lanzados desde el directorio de ComfyUI."""
    return processes.find_by_cwd_and_script(config.COMFY_DIR, "main.py")


def is_dead():
    return not find_processes() and not port_is_open()


def _write_registry(pid):
    config.PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = config.PID_FILE.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({"pid": pid, "create_time": processes.create_time(pid)}),
        encoding="utf-8",
    )
    files.replace(temporary, config.PID_FILE)


def managed_pid():
    """PID de la instancia lanzada por ImageHearth, o None.

    Un registro cuyo proceso ya no existe, o cuyo PID fue reutilizado por otro
    proceso, se descarta.
    """
    try:
        entry = json.loads(config.PID_FILE.read_text(encoding="utf-8"))
        pid = entry["pid"]
        created = entry["create_time"]
    except FileNotFoundError:
        return None
    except (OSError, ValueError, KeyError, TypeError):
        config.PID_FILE.unlink(missing_ok=True)
        return None

    if processes.is_same_process(pid, created):
        return pid

    config.PID_FILE.unlink(missing_ok=True)
    return None


def _rotate_log():
    # Solo con ComfyUI parado: el proceso mantiene abierto su log.
    try:
        if config.COMFY_LOG_FILE.stat().st_size > config.COMFY_LOG_MAX_BYTES:
            files.replace(
                config.COMFY_LOG_FILE,
                config.COMFY_LOG_FILE.with_suffix(".log.1"),
            )
    except (FileNotFoundError, PermissionError):
        pass


def start():
    if is_running():
        log.info("ComfyUI is already running.")
        return

    if port_is_open():
        raise RuntimeError(
            f"Port {config.COMFY_PORT} is in use, but it does not respond "
            "like ComfyUI."
        )

    if not (config.COMFY_DIR / "main.py").exists():
        raise FileNotFoundError(
            f"ComfyUI not found in {config.COMFY_DIR}. Install it with "
            "`imagehearth-mcp setup`, or set its folder with "
            f"comfy_dir in {config.CONFIG_FILE} or with IMAGEHEARTH_COMFY_DIR."
        )

    python = paths.find_venv_python(config.COMFY_DIR)

    if not python.exists():
        raise FileNotFoundError(
                f"Python not found: {python}. Repair it with `imagehearth-mcp setup`."
            )

    config.COMFY_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    _rotate_log()

    log.info("Starting ComfyUI...")

    with open(config.COMFY_LOG_FILE, "a", buffering=1, encoding="utf-8") as output:
        process = subprocess.Popen(
            [
                str(python),
                "main.py",
                "--listen",
                config.COMFY_HOST,
                "--port",
                str(config.COMFY_PORT),
            ],
            cwd=config.COMFY_DIR,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            **spawn.detached_options(),
        )

    _write_registry(process.pid)

    for attempt in range(config.COMFY_START_TIMEOUT):
        if is_running():
            log.info("ComfyUI ready at %s", config.COMFY_API)
            return

        if process.poll() is not None:
            config.PID_FILE.unlink(missing_ok=True)
            raise RuntimeError(
                f"ComfyUI exited at startup (code {process.returncode}). "
                f"See the log: {config.COMFY_LOG_FILE}"
            )

        if attempt % 10 == 0:
            log.info("Waiting for ComfyUI... (%ss)", attempt)

        time.sleep(1)

    raise TimeoutError(
        f"ComfyUI did not respond within {config.COMFY_START_TIMEOUT} "
        f"seconds. See the log: {config.COMFY_LOG_FILE}"
    )


def _stop(pid):
    log.warning("Stopping ComfyUI (pid %s)", pid)

    if not processes.terminate(pid, STOP_TIMEOUT):
        log.warning("ComfyUI did not stop; forcing pid %s", pid)
        processes.kill(pid)

    config.PID_FILE.unlink(missing_ok=True)

    deadline = time.monotonic() + STOP_TIMEOUT

    while port_is_open() and time.monotonic() < deadline:
        time.sleep(1)


def restart():
    """Reinicia la instancia gestionada. Nunca toca una ajena."""
    pid = managed_pid()

    if pid is None:
        if is_running() or port_is_open() or find_processes():
            raise RuntimeError(
                f"The ComfyUI on port {config.COMFY_PORT} was not started by "
                "ImageHearth, so it will not be restarted. Restart it manually."
            )
    else:
        _stop(pid)

    start()


