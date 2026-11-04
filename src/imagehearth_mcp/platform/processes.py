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


class LaunchUnavailable(RuntimeError):
    """The process can't be safely stopped and started again from here."""


# Variables that systemd sets only for processes it runs as services.
_SERVICE_VARIABLES = ("INVOCATION_ID", "JOURNAL_STREAM")


def _cgroup_unit(pid):
    """Last part of the process's cgroup path on Linux (`x.service`, `x.scope`), else None."""
    try:
        with open(f"/proc/{pid}/cgroup", encoding="utf-8") as file:
            for line in file:
                if line.startswith("0::"):
                    return line.strip().rsplit("/", 1)[-1]
    except OSError:
        pass

    return None


def _runs_as_service(pid, environment):
    """True if systemd started the process as a service, not from a terminal or an app.

    Shells inherit INVOCATION_ID from a terminal that runs as a service, so the
    variables alone would reject every server started from it. On Linux the cgroup
    tells them apart: a service lives in a `.service` unit, a terminal in a scope.
    """
    unit = _cgroup_unit(pid)

    if unit is not None:
        return unit.endswith(".service")

    return any(variable in environment for variable in _SERVICE_VARIABLES)


def listener_pid(port):
    """PID of the process listening on a local TCP port, or None."""
    try:
        connections = psutil.net_connections(kind="tcp")
    except (psutil.AccessDenied, OSError):
        # macOS only lists the connections of the user's own processes one by one.
        connections = []

        for process in psutil.process_iter():
            try:
                connections.extend(process.net_connections(kind="tcp"))
            except (psutil.Error, OSError):
                continue

    for connection in connections:
        if (
            connection.status == psutil.CONN_LISTEN
            and connection.laddr
            and connection.laddr.port == port
            and connection.pid
        ):
            return connection.pid

    return None


def _current_username():
    try:
        return psutil.Process().username()
    except (psutil.Error, OSError):
        return None


def launch_info(pid, executable_name):
    """How to start a process again exactly as it is running now.

    Only for a process of this user whose executable is `executable_name`
    and that isn't a system service. Raises LaunchUnavailable otherwise.
    """
    try:
        process = psutil.Process(pid)
        name = os.path.splitext(os.path.basename(process.exe()))[0]

        if name.lower() != executable_name:
            raise LaunchUnavailable(f"The process on that port is {name}, not {executable_name}.")

        if process.username() != _current_username():
            raise LaunchUnavailable(f"It belongs to another user ({process.username()}).")

        info = {
            "pid": pid,
            "exe": process.exe(),
            "args": process.cmdline()[1:],
            "cwd": process.cwd(),
            "env": None,
            "env_inherited": False,
            "create_time": process.create_time(),
        }
    except LaunchUnavailable:
        raise
    except (psutil.Error, OSError) as error:
        raise LaunchUnavailable(f"Can't read how it was started: {error}.") from error

    try:
        environment = process.environ()
    except (psutil.AccessDenied, OSError):
        info["env_inherited"] = True
    except psutil.Error as error:
        raise LaunchUnavailable(f"Can't read how it was started: {error}.") from error
    else:
        if _runs_as_service(pid, environment):
            raise LaunchUnavailable("It runs as a system service.")

        info["env"] = environment

    return info
