r"""Prueba con un `llama-server` real: se para, se relanza igual y responde.

Uso: uv run python scripts/check_llama_restart.py --server RUTA\llama-server.exe --model modelo.gguf

Arranca su propio llama-server en un puerto libre (8099 por defecto) con una variable
de entorno de prueba, y usa el mismo código que el motor para leer cómo se lanzó,
pararlo y relanzarlo. No toca ningún otro proceso. Al terminar lo para.
Lo que no puede comprobar solo: que en Windows no se abra una ventana de consola
al relanzarlo. Míralo mientras corre.
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

MARK = "IMAGEHEARTH_TEST_MARK"


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", type=Path, required=True, help="Ruta de llama-server.")
    parser.add_argument("--model", type=Path, required=True, help="Un modelo GGUF pequeño.")
    parser.add_argument("--port", type=int, default=8099)
    parser.add_argument("--ctx", type=int, default=512)
    return parser.parse_args()


ARGS = parse_args()

# Antes de importar el motor: lee estos valores al importarse.
os.environ["IMAGEHEARTH_LLAMACPP_URL"] = f"http://127.0.0.1:{ARGS.port}"
os.environ["IMAGEHEARTH_MEMORY_MODE"] = "auto"
os.environ[MARK] = "hola"

import requests

from imagehearth_mcp.engine import memory_servers
from imagehearth_mcp.platform import processes, spawn

failures = []


def check(ok, text):
    print(f"[{'OK' if ok else 'FALLA'}] {text}")

    if not ok:
        failures.append(text)


def wait(condition, seconds=60):
    deadline = time.monotonic() + seconds

    while time.monotonic() < deadline:
        if condition():
            return True

        time.sleep(0.5)

    return False


def responds(base):
    try:
        return requests.get(f"{base}/props", timeout=2).ok
    except requests.RequestException:
        return False


def main():
    base = f"http://127.0.0.1:{ARGS.port}"

    if responds(base):
        sys.exit(f"Ya hay algo escuchando en el puerto {ARGS.port}. Usa --port con otro.")

    if not ARGS.server.is_file() or not ARGS.model.is_file():
        sys.exit("No encuentro --server o --model.")

    workdir = ARGS.server.parent
    command = [
        str(ARGS.server),
        "-m", str(ARGS.model),
        "--port", str(ARGS.port),
        "-c", str(ARGS.ctx),
    ]
    print("Arrancando llama-server:", " ".join(command))
    subprocess.Popen(
        command,
        cwd=workdir,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **spawn.detached_options(),
    )

    try:
        check(wait(lambda: responds(base), 120), "llama-server arranca y responde")
        provider = memory_servers.LlamaCppProvider()
        loaded = provider.loaded()
        check(len(loaded) == 1, f"el motor ve un modelo cargado: {loaded and loaded[0]['name']}")

        if not loaded or "launch" not in loaded[0]:
            reason = loaded[0].get("advice") if loaded else "sin modelos"
            check(False, f"se puede reproducir el arranque ({reason})")
            return

        launch = loaded[0]["launch"]
        old_pid = launch["pid"]
        check(True, f"lee cómo se lanzó (pid {old_pid}, {len(launch['args'])} argumentos)")
        check(
            bool(launch.get("env")) and launch["env"].get(MARK) == "hola",
            "lee el entorno, con la variable de prueba",
        )

        print("\nParando... (mira si se abre o cierra alguna ventana)")
        provider.unload(loaded)
        check(not responds(base), "el servidor ya no responde")
        check(not processes.is_same_process(old_pid, launch.get("create_time")), "el proceso original ha terminado")

        print("\nRelanzando... (mira si se abre alguna ventana de consola)")
        started = time.monotonic()
        provider.restore(loaded)
        check(responds(base), f"vuelve a responder ({time.monotonic() - started:.1f} s)")

        again = provider.loaded()
        new = again[0]["launch"] if again and "launch" in again[0] else {}
        check(new.get("pid") not in (None, old_pid), "es un proceso nuevo")
        check(new.get("args") == launch["args"], "mismos argumentos")
        check(
            os.path.normcase(str(new.get("cwd"))) == os.path.normcase(str(launch["cwd"])),
            "mismo directorio de trabajo",
        )
        check((new.get("env") or {}).get(MARK) == "hola", "misma variable de entorno")

        reply = requests.post(
            f"{base}/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "Say hi"}], "max_tokens": 8},
            timeout=120,
        )
        check(reply.ok, "responde a una petición de chat tras el relanzado")
    finally:
        pid = processes.listener_pid(ARGS.port)

        if pid:
            processes.terminate(pid, 10)
            processes.kill(pid)

    print()
    print("RESULTADO:", "todo bien" if not failures else f"{len(failures)} fallo(s)")
    sys.exit(1 if failures else 0)


main()
