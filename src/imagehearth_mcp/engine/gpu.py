import subprocess
import sys

import requests

from imagehearth_mcp.engine import config

MIB = 1024 * 1024


def _from_comfyui():
    response = requests.get(f"{config.COMFY_API}/system_stats", timeout=3)
    response.raise_for_status()

    for device in response.json().get("devices", []):
        free = device.get("vram_free")

        if device.get("type") != "cpu" and isinstance(free, int):
            return free // MIB

    return None


def _from_nvidia_smi():
    output = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
    ).stdout

    return int(output.splitlines()[0].strip())


def _total_from_comfyui():
    response = requests.get(f"{config.COMFY_API}/system_stats", timeout=3)
    response.raise_for_status()

    for device in response.json().get("devices", []):
        total = device.get("vram_total")

        if device.get("type") != "cpu" and isinstance(total, int):
            return total // MIB

    return None


def _total_from_nvidia_smi():
    output = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
    ).stdout

    return int(output.splitlines()[0].strip())


def total_mib():
    """Total GPU memory: /system_stats, then nvidia-smi, or None."""
    sources = (_total_from_comfyui,)

    if sys.platform != "darwin":
        sources = (_total_from_comfyui, _total_from_nvidia_smi)

    for source in sources:
        try:
            value = source()
        except (requests.RequestException, OSError, subprocess.SubprocessError, ValueError, IndexError):
            continue

        if value is not None:
            return value

    return None


def free_mib():
    """Memoria libre de la GPU: /system_stats, después nvidia-smi, o None."""
    # En macOS no hay nvidia-smi: la memoria unificada solo la da ComfyUI.
    sources = (_from_comfyui,)

    if sys.platform != "darwin":
        sources = (_from_comfyui, _from_nvidia_smi)

    for source in sources:
        try:
            value = source()
        except (requests.RequestException, OSError, subprocess.SubprocessError):
            continue
        except (ValueError, IndexError):
            continue

        if value is not None:
            return value

    return None
