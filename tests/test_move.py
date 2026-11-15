"""`update --move-to`: mismo disco, otro disco, interrupciones y rechazos (fase 12)."""

import argparse
import json
import os
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest

from imagehearth_mcp import cli
from imagehearth_mcp.engine import config
from imagehearth_mcp.platform import locks, paths
from imagehearth_mcp.provisioner import (
    ProvisionError,
    comfyui,
    locations,
    maintenance,
    models,
    move,
    preflight,
)
from imagehearth_mcp.provisioner import setup as setup_command
from imagehearth_mcp.provisioner.install_manifest import InstallManifest
from tests.test_provisioner import (  # noqa: F401
    machine,
    make_comfy,
    press,
    setup_args,
)

WEIGHTS = "checkpoints/sd_xl_turbo_1.0_fp16.safetensors"


class FakeRun:
    """Sustituye a `uv` y al intérprete del entorno: apunta lo que se le pide."""

    def __init__(self, works=True):
        self.commands = []
        self.works = works

    def __call__(self, command, **kwargs):
        self.commands.append(command)

        if command[1:2] == ["venv"]:
            python = paths.venv_python(Path(command[-1]))
            python.parent.mkdir(parents=True, exist_ok=True)
            python.write_text("", encoding="utf-8")

        return SimpleNamespace(returncode=0 if self.works else 1)

    def venv_commands(self):
        return [c for c in self.commands if c[1:2] == ["venv"]]


@pytest.fixture
def installed(machine, monkeypatch, tmp_path):
    """Una instalación gestionada en la carpeta de siempre, con un entorno simulado."""
    data = machine.data
    monkeypatch.setattr(config, "LOCK_FILE", data / "engine.lock")
    monkeypatch.setattr(config, "STATE_FILE", data / "state" / "session.json")
    monkeypatch.setattr(comfyui, "find_uv", lambda which=None: "/bin/uv")
    monkeypatch.setattr(locations, "check_disk", lambda needs: [])
    assert setup_command.run(setup_args()) == 0
    python = paths.venv_python(data / "comfyui" / "venv")
    python.parent.mkdir(parents=True, exist_ok=True)
    python.write_text("", encoding="utf-8")
    (data / "comfyui" / "output").mkdir(exist_ok=True)
    (data / "comfyui" / "output" / "image.png").write_bytes(b"png")
    machine.run = FakeRun()
    monkeypatch.setattr(move.subprocess, "run", machine.run)
    return machine


def other_disk(monkeypatch):
    """Simula un segundo disco: renombrar no sirve, hay que copiar."""
    monkeypatch.setattr(move, "_same_device", lambda a, b: False)


def args(target, **kwargs):
    values = {
        "move_to": str(target),
        "yes": True,
        "accept_licenses": False,
        "non_interactive": True,
    }
    return argparse.Namespace(**{**values, **kwargs})


def update(target, **kwargs):
    return maintenance.update(args(target, **kwargs))


def records():
    return InstallManifest.load(config.INSTALL_MANIFEST)


def tree(root):
    root = Path(root)
    return {
        item.relative_to(root).as_posix(): item.read_bytes() if item.is_file() else None
        for item in sorted(root.rglob("*"))
    }


def weights(folder):
    return Path(folder) / "models" / WEIGHTS


# Mismo disco


def test_same_disk_renames_and_keeps_generating(installed, tmp_path, capsys):
    source = installed.data / "comfyui"
    before = tree(source)
    target = tmp_path / "disk2" / "ImageHearth"
    assert update(target) == 0

    new = target / "comfyui"
    assert not source.exists()
    assert tree(new) == before
    assert weights(new).read_bytes() == b"sdxl_turbo"
    saved = records()
    assert saved.comfy_dir == str(new)
    assert saved.models_dir == str(new / "models")
    assert saved.install_dir == str(target)
    assert saved.is_owned(new) and saved.is_owned(weights(new))
    assert installed.run.venv_commands() == []
    assert not config.MOVE_STATE.exists()
    assert "Renaming" in capsys.readouterr().out

    written = tomllib.loads(config.CONFIG_FILE.read_text(encoding="utf-8"))
    assert written["comfy_dir"] == str(new)
    assert "models_dir" not in written


def test_same_disk_recreates_a_broken_environment(installed, tmp_path):
    installed.run.works = False
    update(tmp_path / "disk2")
    assert len(installed.run.venv_commands()) == 1


def test_moved_installation_is_found_by_the_engine_paths(installed, tmp_path):
    target = tmp_path / "disk2"
    update(target)
    saved = records()
    assert models.resolve_dir(saved, saved.comfy_dir) == target / "comfyui" / "models"
    assert [item.state for item in models.inspect(
        manifest_profile_models(), saved.models_dir
    )] == [models.PRESENT]


def manifest_profile_models():
    from imagehearth_mcp.provisioner import manifest

    return manifest.load().profiles["fast"].models


# Otro disco


def test_other_disk_copies_verifies_and_deletes_the_source(installed, tmp_path, monkeypatch, capsys):
    other_disk(monkeypatch)
    source = installed.data / "comfyui"
    before = {k: v for k, v in tree(source).items() if not k.startswith("venv")}
    target = tmp_path / "disk2" / "ImageHearth"
    assert update(target) == 0

    new = target / "comfyui"
    assert not source.exists()
    after = {k: v for k, v in tree(new).items() if not k.startswith("venv")}
    assert after == before
    assert paths.venv_python(new / "venv").exists()
    assert installed.run.venv_commands()[0][-1] == str(new / "venv")
    assert records().comfy_dir == str(new)
    assert records().install_dir == str(target)
    assert not config.MOVE_STATE.exists()
    assert not list(new.rglob(f"*{move.TEMP_SUFFIX}"))
    assert "Another disk" in capsys.readouterr().out


def test_entries_and_config_follow_the_move(installed, tmp_path, monkeypatch):
    other_disk(monkeypatch)
    target = tmp_path / "disk2"
    update(target)
    saved = records()
    new = target / "comfyui"
    paths_recorded = {entry["path"] for entry in saved.entries}
    assert str(new) in paths_recorded
    assert str(new / "custom_nodes" / config.STATUS_NODE) in paths_recorded
    assert not any(str(installed.data / "comfyui") in path for path in paths_recorded)
    setting = next(s for s in saved.settings if s["key"] == "comfy_dir")
    assert setting["value"] == str(new)


def test_sha256_mismatch_stops_and_leaves_the_source_intact(installed, tmp_path, monkeypatch):
    other_disk(monkeypatch)
    source = installed.data / "comfyui"
    weights(source).write_bytes(b"corrupted!")  # el mismo tamaño que `sdxl_turbo`
    before = tree(source)
    target = tmp_path / "disk2"

    with pytest.raises(ProvisionError, match="SHA-256"):
        update(target)

    assert tree(source) == before
    assert records().comfy_dir == str(source)
    assert not config.CONFIG_FILE.exists()
    assert not weights(target / "comfyui").exists()
    assert not list((target).rglob(f"*{move.TEMP_SUFFIX}"))


def test_interrupted_move_keeps_working_and_resumes(installed, tmp_path, monkeypatch, capsys):
    other_disk(monkeypatch)
    source = installed.data / "comfyui"
    before = tree(source)
    target = tmp_path / "disk2"
    real = move._copy_file
    calls = []

    def interrupt(src, dst, declared, models_path):
        calls.append(dst.name)

        if len(calls) == 4:
            raise KeyboardInterrupt

        return real(src, dst, declared, models_path)

    monkeypatch.setattr(move, "_copy_file", interrupt)

    with pytest.raises(KeyboardInterrupt):
        update(target)

    # El origen sigue entero y apuntado.
    assert tree(source) == before
    assert records().comfy_dir == str(source)
    assert not config.CONFIG_FILE.exists()
    state = json.loads(config.MOVE_STATE.read_text(encoding="utf-8"))
    assert len(state["verified"]) == 3 and state["destination"] == str(target)

    # Repetir el comando lo termina sin copiar otra vez lo verificado.
    copied = []
    monkeypatch.setattr(move, "_copy_file", lambda *a: (copied.append(a[1].name), real(*a))[1])
    assert update(target) == 0
    total = len([k for k, v in before.items() if v is not None and not k.startswith("venv")])
    assert len(copied) == total - 3
    assert not source.exists() and records().comfy_dir == str(target / "comfyui")
    assert not config.MOVE_STATE.exists()
    assert "continues a move" in capsys.readouterr().out


def test_cancel_returns_to_the_source_and_cleans_the_destination(installed, tmp_path, monkeypatch, capsys):
    other_disk(monkeypatch)
    source = installed.data / "comfyui"
    before = tree(source)
    target = tmp_path / "disk2" / "ImageHearth"
    real = move._copy_file
    count = []

    def interrupt(*a):
        count.append(1)

        if len(count) == 5:
            raise KeyboardInterrupt

        return real(*a)

    monkeypatch.setattr(move, "_copy_file", interrupt)

    with pytest.raises(KeyboardInterrupt):
        update(target)

    monkeypatch.setattr(move, "_copy_file", real)
    # Cancelar es "mover" a donde ya está la instalación.
    assert update(installed.data) == 0
    assert "cancelled" in capsys.readouterr().out
    assert tree(source) == before
    assert not (tmp_path / "disk2").exists()
    assert not config.MOVE_STATE.exists()
    assert records().comfy_dir == str(source)


def test_another_destination_with_a_move_under_way_is_refused(installed, tmp_path, monkeypatch):
    other_disk(monkeypatch)
    real = move._copy_file
    monkeypatch.setattr(move, "_copy_file", lambda *a: (_ for _ in ()).throw(KeyboardInterrupt))

    with pytest.raises(KeyboardInterrupt):
        update(tmp_path / "first")

    monkeypatch.setattr(move, "_copy_file", real)

    with pytest.raises(ProvisionError) as error:
        update(tmp_path / "second")

    message = str(error.value)
    assert str(tmp_path / "first") in message and "cancel" in message
    assert str(installed.data) in message


def test_models_outside_comfyui_move_to_the_models_folder(installed, tmp_path, monkeypatch):
    machine = installed
    shelf = tmp_path / "shelf"
    # Instalación con modelos aparte: otra máquina limpia, otra carpeta.
    for path in (machine.data / "comfyui", machine.data / "install.json", config.CONFIG_FILE):
        if path.is_dir():
            import shutil

            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)

    assert setup_command.run(setup_args(models_dir=str(shelf))) == 0
    (shelf / "checkpoints" / "mine.safetensors").write_bytes(b"user model")
    paths.venv_python(machine.data / "comfyui" / "venv").parent.mkdir(parents=True, exist_ok=True)
    paths.venv_python(machine.data / "comfyui" / "venv").write_text("", encoding="utf-8")
    other_disk(monkeypatch)
    target = tmp_path / "disk2"
    assert update(target) == 0

    saved = records()
    assert saved.models_dir == str(target / "models")
    assert (target / "models" / WEIGHTS).read_bytes() == b"sdxl_turbo"
    assert not (shelf / WEIGHTS).exists()
    # Lo que setup no descargó se queda donde está.
    assert (shelf / "checkpoints" / "mine.safetensors").read_bytes() == b"user model"
    yaml = (target / "comfyui" / comfyui.EXTRA_PATHS_FILE).read_text(encoding="utf-8")
    assert json.dumps(str(target / "models")) in yaml
    written = tomllib.loads(config.CONFIG_FILE.read_text(encoding="utf-8"))
    assert written["models_dir"] == str(target / "models")
    assert shelf.is_dir()


# Rechazos


def test_attached_installation_is_refused(machine, tmp_path):
    comfy = make_comfy(tmp_path / "theirs")
    assert setup_command.run(setup_args(attach=str(comfy), install_node=True)) == 0

    with pytest.raises(ProvisionError, match="doesn't move"):
        update(tmp_path / "disk2")

    assert comfy.is_dir()


def test_without_an_installation(machine, tmp_path):
    with pytest.raises(ProvisionError, match="no installation"):
        update(tmp_path / "disk2")


def test_same_folder_is_refused(installed):
    with pytest.raises(ProvisionError, match="already installed"):
        update(installed.data)


def test_non_interactive_needs_yes(installed, tmp_path):
    with pytest.raises(ProvisionError, match="--yes"):
        update(tmp_path / "disk2", yes=False)

    assert (installed.data / "comfyui" / "main.py").exists()


def test_interactive_confirmation_with_one_key(installed, tmp_path, monkeypatch, capsys):
    target = tmp_path / "disk2"
    press(monkeypatch, "n")
    assert update(target, yes=False, non_interactive=False) == 0
    assert "Nothing was moved." in capsys.readouterr().out
    assert (installed.data / "comfyui" / "main.py").exists()
    press(monkeypatch, "y")
    assert update(target, yes=False, non_interactive=False) == 0
    assert (target / "comfyui" / "main.py").exists()


def test_generation_in_progress_is_refused(installed, tmp_path):
    with locks.held(config.LOCK_FILE, timeout=1), pytest.raises(ProvisionError, match="generated"):
        update(tmp_path / "disk2")

    assert (installed.data / "comfyui" / "main.py").exists()


def test_session_needing_recovery_is_refused(installed, tmp_path):
    config.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.STATE_FILE.write_text('{"phase": "generating"}', encoding="utf-8")

    with pytest.raises(ProvisionError, match=r"generated|recover"):
        update(tmp_path / "disk2")


def test_agent_installation_in_progress_is_refused(installed, tmp_path):
    with locks.held(config.SETUP_JOB_LOCK, timeout=1), pytest.raises(ProvisionError, match="agent"):
        update(tmp_path / "disk2")


def test_non_empty_destination_is_refused(installed, tmp_path):
    (tmp_path / "disk2" / "comfyui").mkdir(parents=True)
    (tmp_path / "disk2" / "comfyui" / "theirs.txt").write_text("x", encoding="utf-8")

    with pytest.raises(ProvisionError, match="not empty"):
        update(tmp_path / "disk2")

    assert (tmp_path / "disk2" / "comfyui" / "theirs.txt").exists()


def test_destination_inside_the_installation_is_refused(installed):
    with pytest.raises(ProvisionError, match="overlaps"):
        update(installed.data / "comfyui" / "inner")


def test_not_enough_space_changes_nothing(installed, tmp_path, monkeypatch):
    import shutil

    other_disk(monkeypatch)
    # La comprobación real de espacio, que `installed` apaga.
    monkeypatch.setattr(locations, "check_disk", preflight.check_disk)
    monkeypatch.setattr(shutil, "disk_usage", lambda p: SimpleNamespace(free=1_000_000))
    monkeypatch.setattr(move, "_install_bytes", lambda: 7_000_000_000)

    with pytest.raises(ProvisionError, match="Not enough disk space"):
        update(tmp_path / "disk2")

    assert (installed.data / "comfyui" / "main.py").exists()
    assert not (tmp_path / "disk2").exists()


@pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0, reason="needs a normal POSIX user")
def test_no_permission_changes_nothing(installed, tmp_path):
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)

    try:
        with pytest.raises(ProvisionError, match="Can't write"):
            update(locked / "ImageHearth")
    finally:
        locked.chmod(0o700)

    assert (installed.data / "comfyui" / "main.py").exists()


def test_fat32_with_big_files_is_refused(installed, tmp_path, monkeypatch):
    drive = locations.Drive(Path("/"), "vfat")
    monkeypatch.setattr(locations, "mount_of", lambda path, system=None: drive)
    monkeypatch.setattr(locations, "FAT32_LIMIT", 5)

    with pytest.raises(ProvisionError, match=r"FAT32|VFAT"):
        update(tmp_path / "usb")

    assert (installed.data / "comfyui" / "main.py").exists()


# uninstall tras un traslado


def uninstall(**kwargs):
    values = {"yes": True, "remove_models": True, "keep_models": False, **kwargs}
    return maintenance.uninstall(argparse.Namespace(**values))


@pytest.mark.parametrize("copy", [False, True])
def test_uninstall_after_a_move_leaves_nothing_behind(installed, tmp_path, monkeypatch, copy):
    if copy:
        other_disk(monkeypatch)

    target = tmp_path / "disk2" / "ImageHearth"
    update(target)
    assert uninstall() == 0
    assert not (tmp_path / "disk2").exists()
    assert not (installed.data / "comfyui").exists()
    assert not config.INSTALL_MANIFEST.exists()


def test_moving_back_to_the_usual_folder(installed, tmp_path, monkeypatch):
    target = tmp_path / "disk2" / "ImageHearth"
    update(target)
    other_disk(monkeypatch)
    update(installed.data)
    assert (installed.data / "comfyui" / "main.py").exists()
    assert not (tmp_path / "disk2").exists()
    saved = records()
    assert saved.comfy_dir == str(installed.data / "comfyui")
    written = tomllib.loads(config.CONFIG_FILE.read_text(encoding="utf-8"))
    assert written["comfy_dir"] == str(installed.data / "comfyui")


def test_uninstall_is_refused_with_a_move_under_way(installed, tmp_path, monkeypatch):
    other_disk(monkeypatch)
    monkeypatch.setattr(move, "_copy_file", lambda *a: (_ for _ in ()).throw(KeyboardInterrupt))

    with pytest.raises(KeyboardInterrupt):
        update(tmp_path / "disk2")

    with pytest.raises(ProvisionError, match="interrupted"):
        uninstall()

    assert (installed.data / "comfyui" / "main.py").exists()


def test_cli_parses_move_to():
    parsed = cli._build_parser().parse_args(["update", "--move-to", "/mnt/d/ImageHearth", "--yes"])
    assert parsed.move_to == "/mnt/d/ImageHearth" and parsed.yes
    assert cli._build_parser().parse_args(["update"]).move_to is None
