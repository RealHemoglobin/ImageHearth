import subprocess

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


def free_mib():
    """Memoria libre de la GPU: /system_stats, después nvidia-smi, o None."""
    for source in (_from_comfyui, _from_nvidia_smi):
        try:
            value = source()
        except (requests.RequestException, OSError, subprocess.SubprocessError):
            continue
        except (ValueError, IndexError):
            continue

        if value is not None:
            return value

    return None
