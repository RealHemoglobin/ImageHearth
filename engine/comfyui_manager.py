#!/usr/bin/env python3

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import requests

BASE_DIR = Path.home() / "AI"
COMFY_DIR = BASE_DIR / "ComfyUI"
ENGINE_DIR = BASE_DIR / "ImageEngine"
PYTHON = COMFY_DIR / "venv" / "bin" / "python"
LOG_FILE = ENGINE_DIR / "logs" / "comfyui.log"

HOST = "127.0.0.1"
PORT = 8188
API = f"http://{HOST}:{PORT}"


def is_running():
    try:
        response = requests.get(f"{API}/system_stats", timeout=3)
        return response.status_code == 200
    except requests.RequestException:
        return False


def port_is_open():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex((HOST, PORT)) == 0


def start():
    if is_running():
        print("ComfyUI ya está funcionando.")
        return

    if port_is_open():
        raise RuntimeError(
            f"El puerto {PORT} está ocupado, pero no responde como ComfyUI."
        )

    if not PYTHON.exists():
        raise FileNotFoundError(f"No encuentro Python: {PYTHON}")

    if not (COMFY_DIR / "main.py").exists():
        raise FileNotFoundError(f"No encuentro ComfyUI en {COMFY_DIR}")

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    log = open(LOG_FILE, "a", buffering=1)

    print("Arrancando ComfyUI...")
    subprocess.Popen(
        [
            str(PYTHON),
            "main.py",
            "--listen",
            HOST,
        ],
        cwd=COMFY_DIR,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        close_fds=True,
    )

    for attempt in range(180):
        if is_running():
            print(f"ComfyUI listo en {API}")
            return

        if attempt % 10 == 0:
            print(f"Esperando a ComfyUI... ({attempt}s)")

        time.sleep(1)

    raise TimeoutError(
        f"ComfyUI no respondió después de 180 segundos. "
        f"Consulta el log: {LOG_FILE}"
    )


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "ensure"

    if action == "status":
        print("ComfyUI funcionando." if is_running() else "ComfyUI detenido.")
    elif action in ("start", "ensure"):
        start()
    else:
        print("Uso: comfyui_manager.py [status|start|ensure]")
        sys.exit(1)


if __name__ == "__main__":
    main()
