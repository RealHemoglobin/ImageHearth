import os
from pathlib import Path

import psutil

# Tolerancia al comparar create_time guardado y actual (segundos).
CREATE_TIME_TOLERANCE = 1.0


def _same_path(first, second):
    try:
        return os.path.samefile(first, second)
    except OSError:
        return Path(first) == Path(second)


def find_by_cwd_and_script(directory, script):
    """PID de los procesos que ejecutan `script` con `directory` como cwd."""
    pids = []

    for process in psutil.process_iter(["pid", "cmdline", "cwd"]):
        try:
            arguments = process.info["cmdline"] or []
            cwd = process.info["cwd"]
        except (psutil.Error, OSError):
            continue

        if not cwd or script not in [os.path.basename(a) for a in arguments]:
            continue

        if _same_path(cwd, directory):
            pids.append(process.info["pid"])

    return pids


def create_time(pid):
    """Instante de creación del proceso, o None si no existe."""
    try:
        return psutil.Process(pid).create_time()
    except (psutil.Error, OSError):
        return None


def is_same_process(pid, expected_create_time):
    """Comprueba que el PID sigue siendo el proceso original, no uno reutilizado."""
    current = create_time(pid)

    if current is None or expected_create_time is None:
        return False

    return abs(current - expected_create_time) <= CREATE_TIME_TOLERANCE


def terminate(pid, timeout):
    """Pide la parada de un proceso. Devuelve True si terminó."""
    try:
        process = psutil.Process(pid)
        process.terminate()
        process.wait(timeout)
        return True
    except psutil.NoSuchProcess:
        return True
    except psutil.TimeoutExpired:
        return False


def kill(pid, timeout=10):
    """Fuerza la parada de un proceso (SIGKILL o TerminateProcess)."""
    try:
        process = psutil.Process(pid)
        process.kill()
        process.wait(timeout)
    except psutil.NoSuchProcess:
        pass
    except psutil.TimeoutExpired:
        return False

    return True
