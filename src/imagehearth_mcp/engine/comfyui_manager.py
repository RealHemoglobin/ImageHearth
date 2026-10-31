import os
import signal
import socket
import subprocess
import time
from pathlib import Path

import requests

from imagehearth_mcp.engine import config
from imagehearth_mcp.engine.log import get_logger

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
    pids = []

    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue

        try:
            arguments = (entry / "cmdline").read_bytes().split(b"\0")
            cwd = os.readlink(entry / "cwd")
        except OSError:
            continue

        if b"main.py" in arguments and Path(cwd) == config.COMFY_DIR:
            pids.append(int(entry.name))

    return pids


def is_dead():
    return not find_processes() and not port_is_open()


def gpu_free_mib():
    """Memoria libre de la GPU, o None si no se puede consultar."""
    try:
        output = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.free",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        ).stdout
        return int(output.splitlines()[0].strip())
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None


def _rotate_log():
    # Solo con ComfyUI parado: el proceso mantiene abierto su log.
    try:
        if config.COMFY_LOG_FILE.stat().st_size > config.COMFY_LOG_MAX_BYTES:
            config.COMFY_LOG_FILE.replace(
                config.COMFY_LOG_FILE.with_suffix(".log.1")
            )
    except FileNotFoundError:
        pass


def start():
    if is_running():
        log.info("ComfyUI ya está funcionando.")
        return

    if port_is_open():
        raise RuntimeError(
            f"El puerto {config.COMFY_PORT} está ocupado, "
            "pero no responde como ComfyUI."
        )

    if not (config.COMFY_DIR / "main.py").exists():
        raise FileNotFoundError(
            f"No encuentro ComfyUI en {config.COMFY_DIR}. Indica su carpeta con "
            f"comfy_dir en {config.CONFIG_FILE} o con IMAGEHEARTH_COMFY_DIR."
        )

    python = config.COMFY_DIR / "venv" / "bin" / "python"

    if not python.exists():
        raise FileNotFoundError(f"No encuentro Python: {python}")

    config.COMFY_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    _rotate_log()

    log.info("Arrancando ComfyUI...")

    with open(config.COMFY_LOG_FILE, "a", buffering=1) as output:
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
            start_new_session=True,
            close_fds=True,
        )

    for attempt in range(config.COMFY_START_TIMEOUT):
        if is_running():
            log.info("ComfyUI listo en %s", config.COMFY_API)
            return

        if process.poll() is not None:
            raise RuntimeError(
                f"ComfyUI terminó al arrancar (código {process.returncode}). "
                f"Consulta el log: {config.COMFY_LOG_FILE}"
            )

        if attempt % 10 == 0:
            log.info("Esperando a ComfyUI... (%ss)", attempt)

        time.sleep(1)

    raise TimeoutError(
        f"ComfyUI no respondió después de {config.COMFY_START_TIMEOUT} "
        f"segundos. Consulta el log: {config.COMFY_LOG_FILE}"
    )


def restart():
    for pid in find_processes():
        log.warning("Deteniendo ComfyUI (pid %s)", pid)
        os.kill(pid, signal.SIGTERM)

    deadline = time.monotonic() + STOP_TIMEOUT

    while find_processes() and time.monotonic() < deadline:
        time.sleep(1)

    for pid in find_processes():
        log.warning("ComfyUI no se detuvo; forzando pid %s", pid)
        os.kill(pid, signal.SIGKILL)

    deadline = time.monotonic() + STOP_TIMEOUT

    while port_is_open() and time.monotonic() < deadline:
        time.sleep(1)

    start()

