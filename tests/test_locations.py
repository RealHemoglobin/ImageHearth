"""Unidades, propuesta de carpeta y comprobaciones previas (fase 12)."""

import shutil
import sys
from pathlib import Path, PureWindowsPath
from types import SimpleNamespace

import pytest

from imagehearth_mcp.engine import config
from imagehearth_mcp.provisioner import locations
from imagehearth_mcp.provisioner.preflight import ERROR, WARNING

GB = 1_000_000_000
POSIX_PATHS = pytest.mark.skipif(
    sys.platform == "win32", reason="Rutas de montaje POSIX: en Windows se resuelven a una unidad"
)

MOUNTS = r"""sysfs /sys sysfs rw,nosuid 0 0
proc /proc proc rw 0 0
/dev/nvme0n1p2 / ext4 rw,relatime 0 0
tmpfs /run tmpfs rw 0 0
/dev/nvme0n1p1 /boot/efi vfat rw 0 0
/dev/loop3 /snap/core/1 squashfs ro 0 0
/dev/sda1 /mnt/Big\040Disk ext4 rw 0 0
/dev/sdb1 /media/paco/USB vfat rw 0 0
/dev/sdc1 /mnt/readonly ext4 ro 0 0
server:/share /mnt/nas nfs4 rw 0 0
/dev/nvme0n1p2 /var/lib/docker/overlay ext4 rw 0 0
"""


def linux(text=MOUNTS):
    return locations.System("linux", read_mounts=lambda: text)


@pytest.fixture
def data(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DATA_DIR", Path("/home/paco/.local/share/imagehearth"))
    return tmp_path


def usage(path):
    return SimpleNamespace(free=500 * GB)


def test_default_is_the_data_dir(data):
    assert locations.default_install_dir() == config.DATA_DIR
    assert locations.default_install_dir() / "comfyui" == config.DATA_DIR / "comfyui"


def test_linux_drives_filter_virtual_and_read_only(data):
    drives = locations.list_drives(linux(), usage=usage, writable=lambda p, m: True)
    mounts = [drive.path.as_posix() for drive in drives]
    assert mounts == ["/", "/mnt/Big Disk", "/media/paco/USB", "/mnt/nas"]
    by_path = {drive.path.as_posix(): drive for drive in drives}
    assert by_path["/"].system and not by_path["/mnt/Big Disk"].system
    assert by_path["/media/paco/USB"].removable and by_path["/media/paco/USB"].fstype == "vfat"
    assert by_path["/mnt/nas"].network
    assert all(drive.free == 500 * GB for drive in drives)


def test_drives_without_write_access_are_not_offered(data):
    allowed = lambda path, mode: str(path) != "/mnt/nas"
    drives = locations.list_drives(linux(), usage=usage, writable=allowed)
    assert "/mnt/nas" not in [str(drive.path) for drive in drives]


def test_unreadable_proc_mounts_gives_no_drives(data):
    assert locations.list_drives(linux(""), usage=usage, writable=lambda p, m: True) == []


def test_proposal_is_the_default_on_the_system_drive(data):
    drives = locations.list_drives(linux(), usage=usage, writable=lambda p, m: True)
    proposals = [locations.propose(drive) for drive in drives]
    assert proposals[0] == config.DATA_DIR
    assert proposals[1] == Path("/mnt/Big Disk/ImageHearth")


def test_separate_home_partition_is_the_system_drive(data):
    text = "/dev/a / ext4 rw 0 0\n/dev/b /home ext4 rw 0 0\n/dev/c /mnt/x ext4 rw 0 0\n"
    drives = locations.list_drives(linux(text), usage=usage, writable=lambda p, m: True)
    assert [d.path.as_posix() for d in drives if d.system] == ["/home"]


class FakeWindows:
    def __init__(self, drives, long_paths=False):
        self.table = drives
        self.long = long_paths

    def drives(self):
        return list(self.table)

    def drive_type(self, root):
        return self.table[root][0]

    def filesystem(self, root):
        return self.table[root][1]

    def long_paths_enabled(self):
        return self.long


def windows(long_paths=False):
    table = {
        "C:\\": (locations.DRIVE_FIXED, "NTFS"),
        "D:\\": (locations.DRIVE_FIXED, "NTFS"),
        "E:\\": (locations.DRIVE_REMOVABLE, "FAT32"),
        "F:\\": (5, ""),
        "Z:\\": (locations.DRIVE_REMOTE, "NTFS"),
    }
    return locations.System("win32", windows=FakeWindows(table, long_paths))


def test_windows_drives(monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", PureWindowsPath("C:/Users/p/AppData/Local/imagehearth"))
    drives = locations.list_drives(windows(), usage=usage, writable=lambda p, m: True)
    letters = [str(drive.path) for drive in drives]
    assert letters == ["C:\\", "D:\\", "E:\\", "Z:\\"]
    by_letter = {str(drive.path): drive for drive in drives}
    assert by_letter["C:\\"].system and not by_letter["D:\\"].system
    assert by_letter["E:\\"].removable and by_letter["E:\\"].fstype == "FAT32"
    assert by_letter["Z:\\"].network


@pytest.mark.skipif(sys.platform == "win32", reason="Enlaces simbólicos POSIX")
def test_macos_volumes(tmp_path, data):
    (tmp_path / "Backup").mkdir()
    (tmp_path / "Macintosh HD").symlink_to("/")
    system = locations.System("darwin", volumes=tmp_path)
    drives = locations.list_drives(system, usage=usage, writable=lambda p, m: True)
    assert [str(drive.path) for drive in drives] == ["/", str(tmp_path / "Backup")]


# Comprobaciones


@pytest.fixture
def roomy(monkeypatch):
    monkeypatch.setattr(locations, "check_disk", lambda needs: [])


def codes(issues, level=None):
    return [issue.code for issue in issues if level in (None, issue.level)]


def check(path, system=None, **kwargs):
    kwargs.setdefault("probe", lambda directory: None)
    return locations.check(path, system=system or linux(), **kwargs)


def test_healthy_folder_has_no_issues(roomy, tmp_path):
    assert check(tmp_path / "ImageHearth", sizes=[7 * GB]) == []


def test_no_write_permission_is_an_error(roomy, tmp_path):
    issues = check(tmp_path / "x", probe=lambda directory: "Permission denied")
    assert codes(issues, ERROR) == ["no_permission"]
    assert "Permission denied" in issues[0].message


def test_real_probe_creates_nothing_and_detects_a_read_only_folder(roomy, tmp_path):
    target = tmp_path / "new" / "folder"
    assert locations.check(target, system=linux()) == []
    assert list(tmp_path.iterdir()) == []

    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    assert codes(locations.check(blocker / "inside", system=linux())) == ["not_a_folder"]


def test_not_enough_space_is_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "disk_usage", lambda path: SimpleNamespace(free=2 * GB))
    issues = check(tmp_path / "x", sizes=[10 * GB])
    assert codes(issues, ERROR) == ["disk_space"]


@POSIX_PATHS
def test_fat32_with_a_big_file_is_an_error(roomy):
    issues = check("/media/paco/USB/ImageHearth", sizes=[6 * GB, 1 * GB])
    assert codes(issues, ERROR) == ["fat32_large_files"]
    assert "NTFS, ext4 or exFAT" in issues[0].message
    assert "removable_drive" in codes(issues, WARNING)


@POSIX_PATHS
def test_fat32_without_big_files_only_warns(roomy):
    issues = check("/media/paco/USB/ImageHearth", sizes=[1 * GB, 3 * GB])
    assert codes(issues, ERROR) == []
    assert "fat32" in codes(issues, WARNING)


@POSIX_PATHS
def test_exfat_only_warns(roomy):
    text = "/dev/sdd1 /mnt/exfat exfat rw 0 0\n"
    issues = check("/mnt/exfat/ImageHearth", system=linux(text), sizes=[7 * GB])
    assert codes(issues) == ["exfat"] and issues[0].level == WARNING


@POSIX_PATHS
def test_network_drive_only_warns(roomy):
    issues = check("/mnt/nas/ImageHearth", sizes=[7 * GB])
    assert codes(issues) == ["network_drive"] and issues[0].level == WARNING


def test_windows_spaces_warn_and_long_paths_fail(roomy, monkeypatch):
    monkeypatch.setattr(locations, "resolve", PureWindowsPath)
    monkeypatch.setattr(locations, "nearest_existing", lambda path: Path.cwd())
    system = windows()

    assert codes(check("D:\\ImageHearth", system=system)) == []
    assert codes(check("D:\\My Models\\ImageHearth", system=system)) == ["path_characters"]
    assert codes(check("D:\\Imágenes", system=system)) == ["path_characters"]

    deep = "D:\\" + "a" * 120
    assert codes(check(deep, system=system), ERROR) == ["path_too_long"]
    assert codes(check(deep, system=windows(long_paths=True)), ERROR) == []


def test_windows_fat32_removable(roomy, monkeypatch):
    monkeypatch.setattr(locations, "resolve", PureWindowsPath)
    monkeypatch.setattr(locations, "nearest_existing", lambda path: Path.cwd())
    issues = check("E:\\ImageHearth", system=windows(), sizes=[7 * GB])
    assert codes(issues, ERROR) == ["fat32_large_files"]


@POSIX_PATHS
def test_split_separates_errors_and_warnings(roomy):
    issues = check("/media/paco/USB/ImageHearth", sizes=[6 * GB])
    errors, warnings = locations.split(issues)
    assert len(errors) == 1 and len(warnings) == 1
