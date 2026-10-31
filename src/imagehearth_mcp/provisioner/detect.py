"""Qué hay en esta máquina. Solo lee: nunca arranca, instala ni modifica nada."""

import json
import os
import platform as system_platform
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

import psutil
import requests

COMFY_PORTS = (8188, 8000)
DESKTOP_PORT = 8000
PROBE_TIMEOUT = 1
PCI_VENDORS = {"0x10de": "nvidia", "0x1002": "amd", "0x8086": "intel"}

# Servidores de modelos de lenguaje: (nombre, ejecutable, URL de sondeo).
LOCAL_SERVERS = (
    ("ollama", "ollama", "http://127.0.0.1:11434/api/version"),
    ("lmstudio", "lms", "http://127.0.0.1:1234/v1/models"),
    ("llama.cpp", "llama-server", "http://127.0.0.1:8080/health"),
    ("vllm", "vllm", "http://127.0.0.1:8000/version"),
)


@dataclass
class Gpu:
    vendor: str
    name: str = ""
    driver: str = ""
    vram_mib: int = 0


@dataclass
class TorchPlatform:
    """Fila de la matriz de PyTorch de tech-stack.md."""

    index: str
    tier: int
    supported: bool
    note: str = ""


@dataclass
class ComfyInstall:
    path: str
    kind: str  # source | desktop
    has_venv: bool


@dataclass
class RunningComfy:
    port: int
    version: str


@dataclass
class LocalServer:
    name: str
    running: bool
    binary: str | None


@dataclass
class Detection:
    system: str
    machine: str
    gpus: list[Gpu] = field(default_factory=list)
    driver_missing: bool = False
    ram_mib: int = 0
    disk_free_bytes: int = 0
    comfy_installs: list[ComfyInstall] = field(default_factory=list)
    comfy_running: list[RunningComfy] = field(default_factory=list)
    servers: list[LocalServer] = field(default_factory=list)
    platform: TorchPlatform | None = None

    @property
    def primary_gpu(self):
        return max(self.gpus, key=lambda gpu: gpu.vram_mib, default=None)

    def to_dict(self):
        return asdict(self)


def _run(command, timeout=10):
    """Salida de un comando, o None si no existe o falla."""
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    return result.stdout if result.returncode == 0 else None


def _nvidia_gpus(run):
    output = run(
        [
            "nvidia-smi",
            "--query-gpu=name,driver_version,memory.total",
            "--format=csv,noheader,nounits",
        ]
    )
    gpus = []

    for line in (output or "").splitlines():
        fields = [value.strip() for value in line.split(",")]

        if len(fields) != 3:
            continue

        try:
            vram = int(float(fields[2]))
        except ValueError:
            vram = 0

        gpus.append(Gpu("nvidia", fields[0], fields[1], vram))

    return gpus


def _vendor_from_name(name):
    lowered = name.lower()

    if "nvidia" in lowered:
        return "nvidia"

    if "amd" in lowered or "radeon" in lowered or "advanced micro" in lowered:
        return "amd"

    if "intel" in lowered:
        return "intel"

    return None


def _adapters(system, run, sysfs):
    """Tarjetas gráficas según el sistema, tengan o no controlador."""
    if system == "windows":
        output = run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name",
            ]
        )
        names = (output or "").splitlines()
    elif system == "linux":
        output = run(["lspci"])
        names = [
            line.split(": ", 1)[-1]
            for line in (output or "").splitlines()
            if re.search(r"VGA|3D controller|Display controller", line)
        ]

        if output is None:
            return _sysfs_adapters(sysfs)
    else:
        return []

    return [
        Gpu(vendor, name.strip())
        for name in names
        if (vendor := _vendor_from_name(name))
    ]


def _sysfs_adapters(sysfs):
    # lspci no siempre está instalado.
    adapters = []

    for device in sorted(sysfs.glob("*")):
        try:
            device_class = (device / "class").read_text(encoding="utf-8").strip()
            vendor = (device / "vendor").read_text(encoding="utf-8").strip()
        except OSError:
            continue

        if device_class.startswith("0x03") and vendor in PCI_VENDORS:
            adapters.append(Gpu(PCI_VENDORS[vendor]))

    return adapters


def _is_legacy_nvidia(name):
    """GTX 10xx o anterior, sin contar la serie 16, posterior a la 10."""
    match = re.search(r"\bGT[SX]?\s*(\d{3,4})\b", name, re.IGNORECASE)
    return bool(match) and int(match.group(1)) < 1100


def classify(system, machine, gpus):
    """Sitúa el sistema en la matriz de PyTorch."""
    if system == "darwin":
        return TorchPlatform(
            "metal", 2, False, "macOS is not supported by setup yet."
        )

    if machine.lower() not in ("x86_64", "amd64"):
        return TorchPlatform(
            "cpu", 3, False, f"The {machine} architecture is not supported yet."
        )

    vendors = {gpu.vendor: gpu for gpu in gpus}

    if "nvidia" in vendors:
        if _is_legacy_nvidia(vendors["nvidia"].name):
            return TorchPlatform(
                "cu126", 3, True, "Experimental: NVIDIA series 10 or older."
            )

        return TorchPlatform("cu130", 1, True)

    if "amd" in vendors:
        if system == "windows":
            return TorchPlatform(
                "cpu",
                3,
                False,
                "AMD on Windows needs AMD's own PyTorch packages, which setup "
                "can't install. Install ComfyUI by hand and use --attach.",
            )

        return TorchPlatform("rocm7.2", 3, True, "Experimental: AMD GPU.")

    if any("arc" in gpu.name.lower().split() for gpu in gpus if gpu.vendor == "intel"):
        return TorchPlatform("xpu", 3, True, "Experimental: Intel Arc GPU.")

    return TorchPlatform(
        "cpu", 3, True, "No supported GPU: CPU only, SDXL Turbo only, and slow."
    )


def is_comfy_dir(path):
    return (path / "main.py").is_file() and (path / "comfy").is_dir()


def _has_venv(path):
    return (path / "venv").is_dir() or (path / ".venv").is_dir()


def _known_paths(home):
    return (
        home / "AI" / "ComfyUI",
        home / "ComfyUI",
        home / "comfy" / "ComfyUI",
        home / "Documents" / "ComfyUI",
    )


def _desktop_dir(environ):
    """Carpeta de datos de ComfyUI Desktop, que es la que guarda modelos y nodos."""
    appdata = environ.get("APPDATA")

    if not appdata:
        return None

    try:
        config = json.loads(
            (Path(appdata) / "ComfyUI" / "config.json").read_text(encoding="utf-8")
        )
        return Path(config["basePath"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _running_dirs():
    """Carpetas desde las que corre un main.py de ComfyUI."""
    found = []

    for process in psutil.process_iter(["cmdline", "cwd"]):
        command = process.info.get("cmdline") or []
        cwd = process.info.get("cwd")

        if cwd and any(Path(part).name == "main.py" for part in command):
            found.append(Path(cwd))

    return found


def find_comfy_installs(home, environ, extra_paths=(), running_dirs=None):
    installs = {}

    for path in (*extra_paths, *_known_paths(home), *(running_dirs or ())):
        path = Path(path)

        if is_comfy_dir(path):
            installs.setdefault(
                str(path.resolve()),
                ComfyInstall(str(path.resolve()), "source", _has_venv(path)),
            )

    desktop = _desktop_dir(environ)

    if desktop is not None and (desktop / "custom_nodes").is_dir():
        installs.setdefault(
            str(desktop), ComfyInstall(str(desktop), "desktop", _has_venv(desktop))
        )

    return list(installs.values())


def _get(url, session):
    try:
        return session.get(url, timeout=PROBE_TIMEOUT)
    except requests.RequestException:
        return None


def find_running_comfy(session=requests):
    running = []

    for port in COMFY_PORTS:
        response = _get(f"http://127.0.0.1:{port}/system_stats", session)

        if response is None or response.status_code != 200:
            continue

        try:
            comfy_version = response.json()["system"]["comfyui_version"]
        except (ValueError, KeyError, TypeError):
            continue

        running.append(RunningComfy(port, str(comfy_version)))

    return running


def find_local_servers(session=requests, which=shutil.which):
    servers = []

    for name, binary, url in LOCAL_SERVERS:
        response = _get(url, session)
        servers.append(
            LocalServer(
                name,
                response is not None and response.status_code == 200,
                which(binary),
            )
        )

    return servers


def nearest_existing(path):
    """El antepasado más cercano que existe: la carpeta aún no se ha creado."""
    path = Path(path).absolute()

    while not path.exists() and path != path.parent:
        path = path.parent

    return path


def detect(
    *,
    disk_path=None,
    extra_paths=(),
    run=_run,
    session=requests,
    which=shutil.which,
    system=None,
    machine=None,
    home=None,
    environ=None,
    sysfs=Path("/sys/bus/pci/devices"),
    running_dirs=None,
):
    system = system or sys.platform.replace("win32", "windows")
    machine = machine or system_platform.machine()
    home = home or Path.home()
    environ = os.environ if environ is None else environ

    gpus = _nvidia_gpus(run)
    adapters = _adapters(system, run, sysfs)
    driver_missing = not gpus and any(gpu.vendor == "nvidia" for gpu in adapters)

    if not gpus:
        gpus = adapters

    return Detection(
        system=system,
        machine=machine,
        gpus=gpus,
        driver_missing=driver_missing,
        ram_mib=psutil.virtual_memory().total // (1024 * 1024),
        disk_free_bytes=shutil.disk_usage(nearest_existing(disk_path or home)).free,
        comfy_installs=find_comfy_installs(
            home,
            environ,
            extra_paths,
            _running_dirs() if running_dirs is None else running_dirs,
        ),
        comfy_running=find_running_comfy(session),
        servers=find_local_servers(session, which),
        platform=classify(system, machine, gpus),
    )
