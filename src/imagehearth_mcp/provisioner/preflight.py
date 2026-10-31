"""Comprobaciones previas: se ejecutan antes de descargar nada."""

import shutil
import socket
from dataclasses import dataclass

import requests

from imagehearth_mcp.engine import config
from imagehearth_mcp.provisioner.detect import nearest_existing
from imagehearth_mcp.provisioner.manifest import format_size

ERROR = "error"
WARNING = "warning"
# Margen para archivos temporales y para que el disco no quede lleno del todo.
DISK_MARGIN = 1_000_000_000
MANAGED = "managed"


@dataclass(frozen=True)
class Issue:
    level: str
    code: str
    message: str


def check_disk(needs):
    """`needs`: bytes por carpeta. Dos carpetas en el mismo disco se suman."""
    devices = {}

    for path, size in needs.items():
        existing = nearest_existing(path)
        device = devices.setdefault(existing.stat().st_dev, {"path": existing, "size": 0})
        device["size"] += size

    issues = []

    for device in devices.values():
        required = device["size"] + DISK_MARGIN
        free = shutil.disk_usage(device["path"]).free

        if device["size"] and free < required:
            issues.append(
                Issue(
                    ERROR,
                    "disk_space",
                    f"Not enough disk space in {device['path']}: this needs "
                    f"{format_size(required)} and only {format_size(free)} are free. "
                    "Free some space, choose a smaller profile with --profile, or "
                    "keep the models on another disk with --models-dir.",
                )
            )

    return issues


def port_is_open(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        return sock.connect_ex((config.COMFY_HOST, port)) == 0


def _responds_like_comfy(port):
    try:
        url = f"http://{config.COMFY_HOST}:{port}/system_stats"
        return requests.get(url, timeout=3).status_code == 200
    except requests.RequestException:
        return False


def check_port(port, mode, own_instance=False):
    if not port_is_open(port) or own_instance:
        return []

    if mode == MANAGED:
        return [
            Issue(
                ERROR,
                "port_busy",
                f"Port {port} is already in use. Close whatever is using it or "
                "choose another with --port. If it is a ComfyUI you want to use, "
                "run setup with --attach PATH instead.",
            )
        ]

    if not _responds_like_comfy(port):
        return [
            Issue(
                ERROR,
                "port_busy",
                f"Port {port} is in use, but it does not respond like ComfyUI. "
                "Close whatever is using it, or set the port of your ComfyUI with "
                "--port.",
            )
        ]

    return []


def check_gpu(detection, profile, torch, mode):
    issues = []
    platform = detection.platform
    gpu = detection.primary_gpu

    if detection.driver_missing:
        issues.append(
            Issue(
                ERROR if mode == MANAGED else WARNING,
                "driver_missing",
                "An NVIDIA GPU is present but nvidia-smi does not work, so the driver "
                "is missing or broken. Install the current driver from "
                "https://www.nvidia.com/drivers, reboot and run setup again.",
            )
        )

    if mode == MANAGED and not platform.supported:
        issues.append(
            Issue(
                ERROR,
                "gpu_unsupported",
                f"{platform.note} Install ComfyUI by hand and use --attach PATH.",
            )
        )
    elif platform.tier > 1 and platform.note:
        issues.append(Issue(WARNING, "gpu_experimental", platform.note))

    if platform.supported and platform.index == "cpu" and profile.name != "fast":
        issues.append(
            Issue(
                ERROR,
                "gpu_unsupported",
                f"The {profile.name} profile needs a GPU. Without one, only "
                "--profile fast works.",
            )
        )

    if gpu is not None and gpu.vram_mib:
        if gpu.vram_mib < profile.min_vram_mib:
            issues.append(
                Issue(
                    WARNING,
                    "low_vram",
                    f"{gpu.name} has {gpu.vram_mib} MiB of memory and the "
                    f"{profile.name} profile suggests {profile.min_vram_mib} MiB. "
                    "Generation may be slow or fail.",
                )
            )

        driver = gpu.driver.partition(".")[0]

        if (
            mode == MANAGED
            and torch is not None
            and torch.min_driver
            and driver.isdigit()
            and int(driver) < torch.min_driver
        ):
            issues.append(
                Issue(
                    WARNING,
                    "old_driver",
                    f"NVIDIA driver {gpu.driver} may be too old for this PyTorch "
                    f"(it expects {torch.min_driver} or newer). Update it from "
                    "https://www.nvidia.com/drivers if ComfyUI can't use the GPU.",
                )
            )

    return issues


def check_uv(which=shutil.which):
    if which("uv"):
        return []

    return [
        Issue(
            ERROR,
            "uv_missing",
            "uv was not found in PATH. Install it from "
            "https://docs.astral.sh/uv/getting-started/installation/ and run setup "
            "again.",
        )
    ]
