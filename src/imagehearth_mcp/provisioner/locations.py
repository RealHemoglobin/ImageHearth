"""Carpetas de instalación: unidades detectadas, propuesta y comprobaciones previas.

Solo biblioteca estándar. Nada de lo que hay aquí crea carpetas: la comprobación de
permisos usa un archivo de prueba que se borra al instante.
"""

import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from imagehearth_mcp.engine import config
from imagehearth_mcp.provisioner.detect import nearest_existing
from imagehearth_mcp.provisioner.manifest import format_size
from imagehearth_mcp.provisioner.preflight import ERROR, WARNING, Issue, check_disk

FOLDER_NAME = "ImageHearth"
# Archivos más grandes que esto no caben en FAT32.
FAT32_LIMIT = 0xFFFFFFFF
# Ruta más larga (relativa a la carpeta de instalación) que se espera: site-packages de PyTorch.
LONGEST_RELATIVE = 150
WINDOWS_MAX_PATH = 260

VIRTUAL_FILESYSTEMS = frozenset(
    {
        "proc", "sysfs", "tmpfs", "devtmpfs", "devpts", "cgroup", "cgroup2", "overlay",
        "squashfs", "securityfs", "debugfs", "tracefs", "configfs", "fusectl", "pstore",
        "bpf", "mqueue", "hugetlbfs", "autofs", "binfmt_misc", "efivarfs", "ramfs",
        "rpc_pipefs", "nsfs", "selinuxfs", "fuse.gvfsd-fuse", "fuse.portal", "fuse.lxcfs",
        "iso9660", "udf",
    }
)  # fmt: skip
HIDDEN_PREFIXES = ("/proc", "/sys", "/dev", "/snap", "/boot", "/var/lib/docker", "/var/lib/snapd")
NETWORK_FILESYSTEMS = frozenset(
    {
        "nfs", "nfs4", "cifs", "smb", "smb2", "smb3", "smbfs", "afs", "9p", "ncpfs",
        "sshfs", "fuse.sshfs", "davfs", "fuse.davfs", "glusterfs", "ceph", "lustre",
        "fuse.rclone",
    }
)  # fmt: skip
REMOVABLE_PREFIXES = ("/media", "/run/media")
FAT32_FILESYSTEMS = frozenset({"vfat", "fat", "fat32", "msdos", "umsdos"})
EXFAT_FILESYSTEMS = frozenset({"exfat"})

# GetDriveTypeW
DRIVE_REMOVABLE = 2
DRIVE_FIXED = 3
DRIVE_REMOTE = 4
DRIVE_RAMDISK = 6


@dataclass(frozen=True)
class Drive:
    """Un volumen. `system`: el que contiene la carpeta de datos de siempre."""

    path: Path
    fstype: str = ""
    free: int = 0
    network: bool = False
    removable: bool = False
    system: bool = False


class WindowsApi:
    """Lo que hace falta de Windows. Los tests lo sustituyen por uno simulado."""

    def drives(self):
        import ctypes

        mask = ctypes.windll.kernel32.GetLogicalDrives()
        return [f"{chr(65 + bit)}:\\" for bit in range(26) if mask & (1 << bit)]

    def drive_type(self, root):
        import ctypes

        return ctypes.windll.kernel32.GetDriveTypeW(root)

    def filesystem(self, root):
        import ctypes

        name = ctypes.create_unicode_buffer(64)
        ok = ctypes.windll.kernel32.GetVolumeInformationW(
            root, None, 0, None, None, None, name, len(name)
        )
        return name.value if ok else ""

    def long_paths_enabled(self):
        import winreg

        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\FileSystem"
            ) as key:
                return bool(winreg.QueryValueEx(key, "LongPathsEnabled")[0])
        except OSError:
            return False


def _read_proc_mounts():
    try:
        return Path("/proc/mounts").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _unescape(text):
    return re.sub(r"\\([0-7]{3})", lambda match: chr(int(match.group(1), 8)), text)


class System:
    """Lectura de los volúmenes de la máquina. Todo es inyectable para los tests."""

    def __init__(self, name=None, read_mounts=None, volumes=None, windows=None):
        self.name = name or sys.platform
        self._read_mounts = read_mounts or _read_proc_mounts
        self._volumes = Path(volumes) if volumes else Path("/Volumes")
        self._windows = windows

    @property
    def windows(self):
        if self._windows is None:
            self._windows = WindowsApi()

        return self._windows

    def long_paths_enabled(self):
        return self.name == "win32" and self.windows.long_paths_enabled()

    def mounts(self):
        """Volúmenes con su sistema de archivos, sin espacio libre ni filtros de escritura."""
        if self.name == "win32":
            return self._windows_mounts()

        if self.name == "darwin":
            return self._macos_mounts()

        return self._linux_mounts()

    def _linux_mounts(self):
        found = []
        seen = set()

        for line in self._read_mounts().splitlines():
            parts = line.split()

            if len(parts) < 4:
                continue

            device, mount, fstype, options = parts[0], _unescape(parts[1]), parts[2], parts[3]

            if fstype in VIRTUAL_FILESYSTEMS or device in seen:
                continue

            if mount.startswith(HIDDEN_PREFIXES) or (
                mount.startswith("/run") and not mount.startswith("/run/media")
            ):
                continue

            seen.add(device)
            found.append(
                (
                    Drive(
                        Path(mount),
                        fstype,
                        network=fstype in NETWORK_FILESYSTEMS,
                        removable=mount.startswith(REMOVABLE_PREFIXES),
                    ),
                    "ro" in options.split(","),
                )
            )

        return found

    def _macos_mounts(self):
        found = [(Drive(Path("/")), False)]

        try:
            entries = sorted(self._volumes.iterdir())
        except OSError:
            return found

        for entry in entries:
            if entry.is_dir() and entry.resolve() != Path("/"):
                found.append((Drive(entry, removable=True), False))

        return found

    def _windows_mounts(self):
        found = []

        for root in self.windows.drives():
            kind = self.windows.drive_type(root)

            if kind not in (DRIVE_REMOVABLE, DRIVE_FIXED, DRIVE_REMOTE, DRIVE_RAMDISK):
                continue

            found.append(
                (
                    Drive(
                        Path(root),
                        self.windows.filesystem(root),
                        network=kind == DRIVE_REMOTE,
                        removable=kind == DRIVE_REMOVABLE,
                    ),
                    False,
                )
            )

        return found


def default_install_dir():
    """La carpeta de siempre: `comfyui` y el resto de datos cuelgan de ella."""
    return Path(config.DATA_DIR)


def _norm(path):
    """Texto comparable: separadores `/`, sin mayúsculas en una letra de unidad, sin `/` final."""
    text = str(path).replace("\\", "/")

    if re.match(r"^[A-Za-z]:", text):
        text = text.lower()

    return text.rstrip("/")


def _contains(root, path):
    root, path = _norm(root), _norm(path)
    return path == root or path.startswith(root + "/")


def _containing(path, drives):
    """El volumen más específico que contiene `path`, o None."""
    candidates = [drive for drive in drives if _contains(drive.path, path)]
    return max(candidates, key=lambda drive: len(_norm(drive.path)), default=None)


def mount_of(path, system=None):
    """El volumen de `path` (con su sistema de archivos), o None si no se reconoce."""
    system = system or System()
    return _containing(path, [drive for drive, _ in system.mounts()])


def free_bytes(path):
    return shutil.disk_usage(nearest_existing(path)).free


def list_drives(system=None, usage=shutil.disk_usage, writable=os.access):
    """Unidades en las que se puede escribir, con su espacio libre."""
    system = system or System()
    mounts = system.mounts()
    home = _containing(config.DATA_DIR, [drive for drive, _ in mounts])
    drives = []

    for drive, read_only in mounts:
        if read_only or not writable(drive.path, os.W_OK):
            continue

        try:
            free = usage(drive.path).free
        except OSError:
            continue

        drives.append(
            Drive(
                drive.path, drive.fstype, free, drive.network, drive.removable,
                system=drive == home,
            )
        )

    return drives


def propose(drive):
    """La carpeta que se ofrece en una unidad: la de siempre si es la del sistema."""
    if drive.system:
        return default_install_dir()

    return drive.path / FOLDER_NAME


def resolve(text):
    """`~` expandido y ruta absoluta, sin exigir que exista."""
    return Path(os.path.abspath(Path(text).expanduser()))


def first_missing(path):
    """La carpeta de más arriba que habría que crear para tener `path`, o None si ya existe."""
    path = resolve(path)
    missing = None

    while not path.exists() and path != path.parent:
        missing = path
        path = path.parent

    return missing


def _probe(directory):
    """Crea y borra un archivo de prueba. Devuelve el error, o None."""
    try:
        with tempfile.NamedTemporaryFile(dir=directory, prefix=".imagehearth-probe-"):
            pass
    except OSError as error:
        return str(error)

    return None


def check(path, sizes=(), install_bytes=0, longest=LONGEST_RELATIVE, system=None, probe=_probe):
    """Errores y avisos de instalar en `path`.

    `sizes`: tamaño de cada archivo que se va a descargar; `install_bytes`: lo que
    ocupa el ComfyUI gestionado; `longest`: ruta relativa más larga que se espera.
    """
    system = system or System()
    path = resolve(path)
    existing = nearest_existing(path)
    issues = []

    if not existing.is_dir():
        return [
            Issue(
                ERROR,
                "not_a_folder",
                f"{existing} is a file, so {path} can't be created. Choose another folder.",
            )
        ]

    problem = probe(existing)

    if problem is not None:
        return [
            Issue(
                ERROR,
                "no_permission",
                f"Can't write in {existing}: {problem}. Choose a folder you can write to.",
            )
        ]

    sizes = list(sizes)
    issues += check_disk({path: sum(sizes) + install_bytes})
    mount = mount_of(path, system)
    fstype = (mount.fstype if mount else "").lower()
    big = [size for size in sizes if size > FAT32_LIMIT]

    if fstype in FAT32_FILESYSTEMS and big:
        issues.append(
            Issue(
                ERROR,
                "fat32_large_files",
                f"{path} is on a {fstype.upper()} disk, which can't hold files over 4 GB, "
                f"and {len(big)} of the files to download are bigger (the largest is "
                f"{format_size(max(big))}). Choose a disk formatted as NTFS, ext4 or exFAT.",
            )
        )
    elif fstype in FAT32_FILESYSTEMS:
        issues.append(
            Issue(
                WARNING,
                "fat32",
                f"{path} is on a {fstype.upper()} disk, which can't hold files over 4 GB: "
                "a later model that big would not fit.",
            )
        )
    elif fstype in EXFAT_FILESYSTEMS:
        issues.append(
            Issue(
                WARNING,
                "exfat",
                f"{path} is on an exFAT disk, which has no journal: unplugging it while "
                "ImageHearth works can corrupt files.",
            )
        )

    if mount is not None and mount.network:
        issues.append(
            Issue(
                WARNING,
                "network_drive",
                f"{path} is on a network drive: generation and model loading will be "
                "slower, and it fails if the connection drops.",
            )
        )

    if mount is not None and mount.removable:
        issues.append(
            Issue(
                WARNING,
                "removable_drive",
                f"{path} is on a removable drive: ImageHearth stops working while it is "
                "unplugged.",
            )
        )

    if system.name == "win32":
        issues += _windows_issues(path, longest, system)

    return issues


def _windows_issues(path, longest, system):
    issues = []
    text = str(path)

    if " " in text or not text.isascii():
        issues.append(
            Issue(
                WARNING,
                "path_characters",
                f"{path} has spaces or non-ASCII characters: some of the tools ComfyUI "
                "uses may fail. A path like D:\\ImageHearth avoids it.",
            )
        )

    if len(text) + 1 + longest > WINDOWS_MAX_PATH and not system.long_paths_enabled():
        issues.append(
            Issue(
                ERROR,
                "path_too_long",
                f"{path} is too long: some files would pass Windows' {WINDOWS_MAX_PATH}-"
                "character limit and long paths are not enabled. Choose a shorter folder, "
                "such as D:\\ImageHearth, or enable LongPathsEnabled in Windows.",
            )
        )

    return issues


def split(issues):
    """(errores, avisos) como textos."""
    return (
        [issue.message for issue in issues if issue.level == ERROR],
        [issue.message for issue in issues if issue.level == WARNING],
    )
