"""Correcciones de la revisión de seguridad de la fase 16 (docs/security-review.md)."""

import io
import os
import stat
import sys
import tarfile
from pathlib import Path
from unittest import mock

import pytest

from imagehearth_mcp.provisioner import (
    ProvisionError,
    comfyui,
    connect,
    manifest,
    models,
)
from imagehearth_mcp.provisioner.install_manifest import InstallManifest
from tests.test_provisioner import (
    TORCH,
    FakeUv,
    comfy_pin,
    fetch_archive,
)

ROOT = Path(__file__).resolve().parent.parent


def archive_with(*members):
    """tar.gz con miembros (nombre, tipo, dato o destino del enlace)."""
    buffer = io.BytesIO()

    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for name, kind, payload in members:
            info = tarfile.TarInfo(name)

            if kind == "file":
                info.size = len(payload)
                tar.addfile(info, io.BytesIO(payload))
            else:
                info.type = tarfile.SYMTYPE if kind == "symlink" else tarfile.LNKTYPE
                info.linkname = payload
                tar.addfile(info)

    return buffer.getvalue()


# El filtro "data" de tarfile quita la raíz de una ruta absoluta: se extrae dentro, no se rechaza.
CONTAINED = {"absolute-path"}
MALICIOUS = {
    "parent-directory": [("ComfyUI-1/main.py", "file", b"x"), ("ComfyUI-1/../../escape.py", "file", b"x")],
    "absolute-path": [("ComfyUI-1/main.py", "file", b"x"), ("/imagehearth-escape-test.py", "file", b"x")],
    "symlink-out": [("ComfyUI-1/main.py", "file", b"x"), ("ComfyUI-1/link", "symlink", "../../../etc")],
    "absolute-symlink": [("ComfyUI-1/main.py", "file", b"x"), ("ComfyUI-1/link", "symlink", "/etc/passwd")],
    "hardlink-out": [("ComfyUI-1/main.py", "file", b"x"), ("ComfyUI-1/hard", "hardlink", "../../outside")],
}


@pytest.fixture
def records(tmp_path):
    return InstallManifest(tmp_path / "data" / "install.json")


@pytest.mark.parametrize("name", MALICIOUS)
def test_comfyui_archive_with_unsafe_members_is_rejected(tmp_path, records, name):
    target = tmp_path / "work" / "comfyui"
    target.parent.mkdir()

    def install():
        comfyui.install_managed(
            comfy_pin("1"),
            TORCH,
            target,
            records,
            run=FakeUv(),
            fetch=fetch_archive(archive_with(*MALICIOUS[name])),
            which=lambda _: "/bin/uv",
        )

    if name in CONTAINED:
        install()
    else:
        with pytest.raises(ProvisionError, match="Can't install ComfyUI"):
            install()

        assert not (target / "main.py").exists()

    assert not Path("/imagehearth-escape-test.py").exists()
    assert not (tmp_path / "escape.py").exists()
    assert not (tmp_path / "work" / "escape.py").exists()
    assert not list(tmp_path.glob("*.partial")) and not list((tmp_path / "work").glob("*.partial"))


@pytest.mark.parametrize("name", MALICIOUS)
def test_custom_node_archive_with_unsafe_members_is_rejected(tmp_path, records, name):
    comfy = tmp_path / "work" / "comfy"
    python = comfy / "venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    (comfy / "custom_nodes").mkdir()
    pin = manifest.load().nodes["comfyui-gguf"]
    members = [(n.replace("ComfyUI-1", "ComfyUI-GGUF-abc"), k, d) for n, k, d in MALICIOUS[name]]

    def install():
        comfyui.install_custom_node(
            pin,
            comfy,
            records,
            run=lambda command, check: None,
            fetch=lambda _pin, path: path.write_bytes(archive_with(*members)),
            which=lambda _: "/bin/uv",
        )

    if name in CONTAINED:
        install()
    else:
        with pytest.raises(ProvisionError, match="Can't install"):
            install()

        assert not (comfy / "custom_nodes" / pin.folder).exists()

    assert not Path("/imagehearth-escape-test.py").exists()
    assert not (tmp_path / "work" / "escape.py").exists()


def test_archive_with_a_wrong_hash_is_rejected_and_deleted(tmp_path):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def raise_for_status(self):
            pass

        def iter_content(self, size):
            yield b"not the archive"

    pin = comfy_pin("1")
    destination = tmp_path / "comfyui.tar.gz"

    with (
        mock.patch.object(comfyui.requests, "get", return_value=Response()),
        pytest.raises(ProvisionError, match="SHA-256"),
    ):
        comfyui._download_archive(pin, destination)

    assert not destination.exists()


@pytest.mark.skipif(sys.platform == "win32", reason="Permisos POSIX")
def test_agent_config_is_never_written_world_readable(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("token = 'secret'\n", encoding="utf-8")
    path.chmod(0o600)
    seen = []
    real_replace = connect.files.replace

    def spy(source, destination, *args):
        seen.append(stat.S_IMODE(os.stat(source).st_mode))
        real_replace(source, destination, *args)

    with mock.patch.object(connect.files, "replace", spy):
        connect._write(path, "token = 'secret'\n[mcp_servers.imagehearth]\n")

    assert seen == [0o600]
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.skipif(sys.platform == "win32", reason="Permisos POSIX")
def test_a_new_agent_config_is_created_private(tmp_path):
    path = tmp_path / "new" / "config.toml"
    connect._write(path, "a = 1\n")
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.skipif(sys.platform == "win32", reason="Enlaces simbólicos POSIX")
def test_agent_config_that_is_a_symlink_keeps_its_link(tmp_path):
    real = tmp_path / "dotfiles" / "config.toml"
    real.parent.mkdir()
    real.write_text("a = 1\n", encoding="utf-8")
    link = tmp_path / "config.toml"
    link.symlink_to(real)
    connect._write(link, "a = 2\n")

    assert link.is_symlink()
    assert real.read_text(encoding="utf-8") == "a = 2\n"


def test_hf_token_never_reaches_a_message(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_secret_value")
    assert "hf_secret_value" not in models.scrub("401 for Bearer hf_secret_value at the hub")
    assert models.scrub("no token here") == "no token here"
    monkeypatch.delenv("HF_TOKEN")
    assert models.scrub("anything") == "anything"


def test_install_sh_never_takes_the_current_directory_for_the_repository():
    script = (ROOT / "install.sh").read_text(encoding="utf-8")
    assert '"$(dirname "$0")" 2>/dev/null && pwd) || repo_dir' not in script
    assert "install.sh | */install.sh)" in script
