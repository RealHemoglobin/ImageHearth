"""`setup --install-dir`, el paso de carpeta y la persistencia (fase 12)."""

import argparse
import os
import tomllib
from pathlib import Path

import pytest

from imagehearth_mcp import cli
from imagehearth_mcp.engine import config
from imagehearth_mcp.provisioner import ProvisionError, locations, maintenance
from imagehearth_mcp.provisioner import setup as setup_command
from imagehearth_mcp.provisioner.install_manifest import InstallManifest
from tests.test_provisioner import (  # noqa: F401
    GB,
    machine,
    make_comfy,
    press,
    setup_args,
)


@pytest.fixture
def roomy(monkeypatch):
    """Sin la comprobación de espacio real: los modelos del test pesan unos bytes."""
    monkeypatch.setattr(locations, "check_disk", lambda needs: [])


def interactive(**kwargs):
    return setup_args(**{"accept_licenses": False, "non_interactive": False, **kwargs})


def records():
    return InstallManifest.load(config.INSTALL_MANIFEST)


def typed(path):
    return str(path) + "\r"


# --install-dir sin preguntar


def test_install_dir_places_comfyui_and_models(machine, roomy, tmp_path):
    folder = tmp_path / "disk" / "ImageHearth"
    assert setup_command.run(setup_args(install_dir=str(folder))) == 0

    saved = records()
    assert saved.comfy_dir == str(folder / "comfyui")
    assert saved.models_dir == str(folder / "comfyui" / "models")
    assert saved.install_dir == str(folder)
    assert machine.managed == [folder / "comfyui"]
    assert (folder / "comfyui" / "main.py").exists()
    assert machine.downloads == ["sdxl_turbo"]

    written = tomllib.loads(config.CONFIG_FILE.read_text(encoding="utf-8"))
    assert written["comfy_dir"] == str(folder / "comfyui")
    assert "models_dir" not in written


def test_install_dir_with_models_dir(machine, roomy, tmp_path):
    folder = tmp_path / "disk" / "ImageHearth"
    models = tmp_path / "models-disk"
    assert setup_command.run(setup_args(install_dir=str(folder), models_dir=str(models))) == 0

    saved = records()
    assert saved.comfy_dir == str(folder / "comfyui")
    assert saved.models_dir == str(models.resolve())
    assert (models / "checkpoints").exists()
    written = tomllib.loads(config.CONFIG_FILE.read_text(encoding="utf-8"))
    assert written["comfy_dir"] == str(folder / "comfyui")
    assert written["models_dir"] == str(models.resolve())


def test_without_install_dir_nothing_changes(machine):
    assert setup_command.run(setup_args()) == 0
    saved = records()
    assert saved.comfy_dir == str(machine.data / "comfyui")
    assert saved.install_dir is None
    assert not config.CONFIG_FILE.exists()


def test_install_dir_and_attach_are_rejected_before_anything(machine, tmp_path):
    comfy = make_comfy(tmp_path / "theirs")

    with pytest.raises(ProvisionError, match="can't be combined"):
        setup_command.run(setup_args(install_dir=str(tmp_path / "x"), attach=str(comfy)))

    assert not config.INSTALL_MANIFEST.exists()
    assert not (tmp_path / "x").exists()


def test_other_folder_on_an_existing_installation_points_to_move(machine, roomy, tmp_path):
    assert setup_command.run(setup_args()) == 0
    machine.downloads.clear()

    with pytest.raises(ProvisionError, match="update --move-to"):
        setup_command.run(setup_args(install_dir=str(tmp_path / "elsewhere")))

    assert machine.downloads == []
    assert not (tmp_path / "elsewhere").exists()
    # Con la misma carpeta no hay conflicto.
    assert setup_command.run(setup_args(install_dir=str(machine.data))) == 0


def test_install_dir_on_an_attached_installation_is_rejected(machine, tmp_path):
    comfy = make_comfy(tmp_path / "theirs")
    assert setup_command.run(setup_args(attach=str(comfy), install_node=True)) == 0

    with pytest.raises(ProvisionError, match="existing ComfyUI"):
        setup_command.run(setup_args(install_dir=str(tmp_path / "x")))


def test_not_enough_space_fails_before_downloading(machine, tmp_path, monkeypatch):
    import shutil
    from types import SimpleNamespace

    monkeypatch.setattr(shutil, "disk_usage", lambda path: SimpleNamespace(free=2 * GB))
    folder = tmp_path / "small" / "ImageHearth"

    with pytest.raises(ProvisionError, match="Not enough disk space"):
        setup_command.run(setup_args(install_dir=str(folder)))

    assert machine.downloads == [] and machine.managed == []
    assert not folder.exists() and not config.INSTALL_MANIFEST.exists()


@pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0, reason="needs a normal POSIX user")
def test_no_write_permission_fails_before_downloading(machine, roomy, tmp_path):
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)

    try:
        with pytest.raises(ProvisionError, match="Can't write"):
            setup_command.run(setup_args(install_dir=str(locked / "ImageHearth")))
    finally:
        locked.chmod(0o700)

    assert machine.downloads == [] and not config.INSTALL_MANIFEST.exists()


def fat32(monkeypatch, removable=False):
    drive = locations.Drive(Path("/"), "vfat", removable=removable)
    monkeypatch.setattr(locations, "mount_of", lambda path, system=None: drive)


def test_fat32_with_big_files_fails_before_downloading(machine, roomy, tmp_path, monkeypatch):
    fat32(monkeypatch)
    # Los modelos del test pesan unos bytes: el límite se baja para que no quepan.
    monkeypatch.setattr(locations, "FAT32_LIMIT", 5)

    with pytest.raises(ProvisionError, match=r"FAT32|VFAT"):
        setup_command.run(setup_args(install_dir=str(tmp_path / "usb" / "ImageHearth")))

    assert machine.downloads == []


def test_fat32_without_big_files_warns_in_the_summary(machine, roomy, tmp_path, monkeypatch, capsys):
    fat32(monkeypatch, removable=True)
    assert setup_command.run(setup_args(install_dir=str(tmp_path / "usb" / "ImageHearth"))) == 0
    output = capsys.readouterr().out
    assert "WARNING:" in output and "removable drive" in output
    assert "Install folder:" in output


# Paso interactivo


def drive_at(path, free=500 * GB, **kwargs):
    path.mkdir(parents=True, exist_ok=True)
    return locations.Drive(path, "ext4", free, **kwargs)


def test_step_offers_the_usual_place_drives_and_typing(machine, roomy, tmp_path, monkeypatch, capsys):
    other = drive_at(tmp_path / "disk2")
    monkeypatch.setattr(locations, "list_drives", lambda *a, **k: [other])
    press(monkeypatch, "\x03")

    with pytest.raises(KeyboardInterrupt):
        setup_command.run(interactive(profile="fast"))

    output = capsys.readouterr().out
    assert "Step 1 of 2" in output
    assert "(the usual place)" in output and "(recommended)" in output
    assert f"{other.path / 'ImageHearth'}" in output
    assert "500.0 GB free" in output and "Type a path" in output


def test_step_chooses_a_detected_drive(machine, roomy, tmp_path, monkeypatch):
    other = drive_at(tmp_path / "disk2")
    monkeypatch.setattr(locations, "list_drives", lambda *a, **k: [other])
    press(monkeypatch, "2" + "1")
    assert setup_command.run(interactive(profile="fast")) == 0
    folder = other.path / "ImageHearth"
    assert records().comfy_dir == str(folder / "comfyui")
    assert records().install_dir == str(folder)
    assert (folder / "comfyui" / "main.py").exists()


def test_system_drive_is_not_offered_twice(machine, roomy, tmp_path, monkeypatch, capsys):
    system = locations.Drive(Path("/"), "ext4", 100 * GB, system=True)
    monkeypatch.setattr(locations, "list_drives", lambda *a, **k: [system])
    press(monkeypatch, "\x03")

    with pytest.raises(KeyboardInterrupt):
        setup_command.run(interactive(profile="fast"))

    output = capsys.readouterr().out
    assert "  2. Type a path" in output and "  3." not in output


def test_step_with_a_typed_path(machine, roomy, tmp_path, monkeypatch):
    folder = tmp_path / "typed" / "ImageHearth"
    press(monkeypatch, "2" + typed(folder) + "1")
    assert setup_command.run(interactive(profile="fast")) == 0
    assert records().comfy_dir == str(folder / "comfyui")


def test_typed_path_expands_the_home_folder(machine, roomy, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    press(monkeypatch, "2" + typed("~/Hearth") + "1")
    assert setup_command.run(interactive(profile="fast")) == 0
    assert records().install_dir == str(tmp_path / "home" / "Hearth")


def test_invalid_typed_path_explains_and_asks_again(machine, roomy, tmp_path, monkeypatch, capsys):
    blocker = tmp_path / "a-file"
    blocker.write_text("x", encoding="utf-8")
    folder = tmp_path / "good"
    press(monkeypatch, "2" + typed(blocker / "inside") + "2" + typed(folder) + "1")
    assert setup_command.run(interactive(profile="fast")) == 0
    output = capsys.readouterr().out
    assert "is a file" in output
    assert records().install_dir == str(folder)


def test_empty_typed_path_returns_to_the_list(machine, roomy, monkeypatch, capsys):
    press(monkeypatch, "2" + "\r" + "1" + "1")
    assert setup_command.run(interactive(profile="fast")) == 0
    assert records().install_dir is None
    assert capsys.readouterr().out.count("Install folder (ComfyUI") == 2


def test_zero_exits_from_the_folder_step_and_back_from_the_review(
    machine, roomy, tmp_path, monkeypatch, capsys
):
    press(monkeypatch, "0")
    assert setup_command.run(interactive(profile="fast")) == 0
    assert "Nothing was changed." in capsys.readouterr().out
    assert not config.INSTALL_MANIFEST.exists()

    folder = tmp_path / "later"
    # Typed folder, back from the review to the folder step, the usual place, accept.
    press(monkeypatch, "2" + typed(folder) + "0" + "1" + "1")
    assert setup_command.run(interactive(profile="fast")) == 0
    assert records().install_dir is None and not folder.exists()


def test_nothing_is_created_before_the_final_confirmation(machine, roomy, tmp_path, monkeypatch):
    folder = tmp_path / "deep" / "er" / "ImageHearth"
    press(monkeypatch, "2" + typed(folder) + "0" + "0")
    assert setup_command.run(interactive(profile="fast")) == 0
    assert not (tmp_path / "deep").exists()
    assert not config.INSTALL_MANIFEST.exists() and not config.CONFIG_FILE.exists()
    assert machine.downloads == []


def test_the_step_is_skipped_with_the_argument_or_an_installation(machine, roomy, tmp_path, monkeypatch, capsys):
    press(monkeypatch, "1")
    assert setup_command.run(interactive(profile="fast", install_dir=str(tmp_path / "a"))) == 0
    assert "Step 1 of 1" in capsys.readouterr().out

    press(monkeypatch, "1")
    assert setup_command.run(interactive(profile="fast")) == 0
    assert "Install folder (ComfyUI" not in capsys.readouterr().out


def test_the_step_is_skipped_when_attaching(machine, tmp_path, monkeypatch, capsys):
    comfy = make_comfy(tmp_path / "theirs")
    press(monkeypatch, "1" + "n")
    assert setup_command.run(interactive(profile="fast", attach=str(comfy))) == 0
    assert "Install folder (ComfyUI" not in capsys.readouterr().out


# uninstall


def uninstall(**kwargs):
    values = {"yes": True, "remove_models": False, "keep_models": False, **kwargs}
    return maintenance.uninstall(argparse.Namespace(**values))


def test_uninstall_removes_the_folder_setup_created(machine, roomy, tmp_path):
    folder = tmp_path / "disk" / "ImageHearth"
    setup_command.run(setup_args(install_dir=str(folder)))
    assert uninstall(remove_models=True) == 0
    assert not (tmp_path / "disk").exists()
    assert not config.INSTALL_MANIFEST.exists()


def test_uninstall_keeps_a_folder_that_already_existed(machine, roomy, tmp_path):
    folder = tmp_path / "disk" / "ImageHearth"
    folder.mkdir(parents=True)
    setup_command.run(setup_args(install_dir=str(folder)))
    assert uninstall(remove_models=True) == 0
    assert folder.is_dir() and not any(folder.iterdir())


def test_uninstall_keeps_the_folder_if_it_has_other_files(machine, roomy, tmp_path):
    folder = tmp_path / "disk" / "ImageHearth"
    setup_command.run(setup_args(install_dir=str(folder)))
    (folder / "mine.txt").write_text("keep", encoding="utf-8")
    assert uninstall(remove_models=True) == 0
    assert (folder / "mine.txt").exists()
    assert not (folder / "comfyui").exists()


def test_uninstall_keeping_models_leaves_the_folder(machine, roomy, tmp_path):
    folder = tmp_path / "disk" / "ImageHearth"
    setup_command.run(setup_args(install_dir=str(folder)))
    assert uninstall(keep_models=True) == 0
    assert (folder / "comfyui" / "models" / "checkpoints").exists()


def test_cli_parses_install_dir():
    args = cli._build_parser().parse_args(["setup", "--install-dir", "/mnt/d/ImageHearth"])
    assert args.install_dir == "/mnt/d/ImageHearth"
    assert cli._build_parser().parse_args(["setup"]).install_dir is None


def test_config_written_is_valid_toml_with_both_keys(machine, roomy, tmp_path):
    setup_command.run(
        setup_args(install_dir=str(tmp_path / "d"), models_dir=str(tmp_path / "m"))
    )
    tomllib.loads(config.CONFIG_FILE.read_text(encoding="utf-8"))


def test_uninstall_removes_the_configs_comfyui_ships(machine, roomy, tmp_path):
    folder = tmp_path / "disk" / "ImageHearth"
    setup_command.run(setup_args(install_dir=str(folder)))
    configs = folder / "comfyui" / "models" / "configs"
    configs.mkdir()
    (configs / "v1-inference.yaml").write_text("x", encoding="utf-8")
    assert uninstall(remove_models=True) == 0
    assert not (tmp_path / "disk").exists()


def test_uninstall_keeps_other_files_in_configs(machine, roomy, tmp_path):
    folder = tmp_path / "disk" / "ImageHearth"
    setup_command.run(setup_args(install_dir=str(folder)))
    configs = folder / "comfyui" / "models" / "configs"
    configs.mkdir()
    (configs / "mine.txt").write_text("keep", encoding="utf-8")
    assert uninstall(remove_models=True) == 0
    assert (configs / "mine.txt").exists()
