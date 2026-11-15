"""`setup` por pasos con teclas: volver con 0, indicador de paso y Ctrl+C (fase 11)."""

import argparse
from unittest import mock

import pytest

from imagehearth_mcp.engine import config
from imagehearth_mcp.provisioner import ProvisionError, detect, maintenance, menu
from imagehearth_mcp.provisioner import setup as setup_command
from imagehearth_mcp.provisioner.install_manifest import InstallManifest
from tests.test_catalog import install, models_dir, tiny  # noqa: F401
from tests.test_provisioner import (  # noqa: F401
    fake_download,
    machine,
    make_comfy,
    press,
    setup_args,
    torch_ok,
)
from tests.test_quality_model import idle  # noqa: F401

# Linux, GPU de 24 GB: perfiles fast (1), quality (2), full (3); modelos flux-dev (1),
# flux-schnell (2), sdxl (3).


def interactive(**kwargs):
    return setup_args(**{"profile": None, "accept_licenses": False, "non_interactive": False, **kwargs})


def test_full_run_only_with_keys(machine, monkeypatch, capsys):
    press(monkeypatch, "231")
    assert setup_command.run(interactive()) == 0
    output = capsys.readouterr().out

    for step in (1, 2, 3):
        assert f"Step {step} of 3" in output

    records = InstallManifest.load(config.INSTALL_MANIFEST)
    assert (records.profile, records.quality_model) == ("quality", "sdxl")


def test_enter_takes_the_recommended_answers(machine, monkeypatch):
    press(monkeypatch, "\r\r\r")
    assert setup_command.run(interactive()) == 0
    records = InstallManifest.load(config.INSTALL_MANIFEST)
    assert records.profile == "full" and records.quality_model == "flux-dev"


def test_zero_goes_back_and_keeps_answers(machine, monkeypatch, capsys):
    # profile quality, model sdxl, back from the review to the model (default sdxl), accept.
    press(monkeypatch, "230\r1")
    assert setup_command.run(interactive()) == 0
    output = capsys.readouterr().out
    assert output.count("Step 2 of 3") == 2
    assert "Choice [3]" in output
    assert InstallManifest.load(config.INSTALL_MANIFEST).quality_model == "sdxl"


def test_profile_without_quality_removes_the_model_step(machine, monkeypatch, capsys):
    # quality, back from the model, fast: two steps left.
    press(monkeypatch, "2" + "0" + "1" + "1")
    assert setup_command.run(interactive()) == 0
    output = capsys.readouterr().out
    assert "Step 1 of 3" in output and "Step 2 of 2" in output
    records = InstallManifest.load(config.INSTALL_MANIFEST)
    assert records.profile == "fast" and records.quality_model is None


def test_zero_from_every_step_goes_back_one_at_a_time(machine, monkeypatch, capsys):
    # profile, model, review; back, back, back leaves with nothing written.
    press(monkeypatch, "23" + "000")
    assert setup_command.run(interactive()) == 0
    assert "Nothing was changed." in capsys.readouterr().out
    assert not config.INSTALL_MANIFEST.exists()
    assert machine.downloads == []


def test_steps_resolved_by_arguments_are_not_shown(machine, monkeypatch, capsys):
    press(monkeypatch, "1")
    assert setup_command.run(interactive(profile="fast")) == 0
    output = capsys.readouterr().out
    assert "Step 1 of 1" in output and "Step 2" not in output
    assert "Profiles:" not in output


def test_quality_model_argument_hides_its_step(machine, monkeypatch, capsys):
    press(monkeypatch, "21")
    assert setup_command.run(interactive(quality_model="sdxl")) == 0
    output = capsys.readouterr().out
    assert "Step 2 of 2" in output and "Quality models" not in output


def existing_comfy(machine):
    comfy = make_comfy(machine.tmp / "theirs")
    machine.detection.comfy_installs = [detect.ComfyInstall(str(comfy), "source", True)]
    return comfy


def test_existing_comfy_adds_the_mode_step(machine, monkeypatch, capsys):
    comfy = existing_comfy(machine)
    press(monkeypatch, "1" + "1" + "1" + "n")
    assert setup_command.run(interactive(profile="fast")) == 0
    output = capsys.readouterr().out
    assert "Step 1 of 2" in output and "Step 2 of 2" in output
    records = InstallManifest.load(config.INSTALL_MANIFEST)
    assert records.mode == "attached" and records.comfy_dir == str(comfy.resolve())


def test_existing_comfy_managed_option_and_back_to_mode(machine, monkeypatch):
    existing_comfy(machine)
    # Attach, review, back to the mode, managed, review.
    press(monkeypatch, "1" + "0" + "2" + "1")
    assert setup_command.run(interactive(profile="fast")) == 0
    assert InstallManifest.load(config.INSTALL_MANIFEST).mode == "managed"


def test_managed_argument_hides_the_mode_step(machine, monkeypatch, capsys):
    existing_comfy(machine)
    press(monkeypatch, "1")
    assert setup_command.run(interactive(profile="fast", managed=True)) == 0
    assert "Step 1 of 1" in capsys.readouterr().out


@pytest.mark.parametrize("keys", ["\x03", "2\x03", "23\x03"])
def test_ctrl_c_writes_nothing(machine, monkeypatch, keys):
    press(monkeypatch, keys)

    with pytest.raises(KeyboardInterrupt):
        setup_command.run(interactive())

    assert not config.INSTALL_MANIFEST.exists()
    assert not config.CONFIG_FILE.exists()
    assert machine.downloads == []


def test_non_interactive_is_unchanged(machine):
    with pytest.raises(ProvisionError, match="--profile"):
        setup_args_run(profile=None)

    assert machine.downloads == []


def setup_args_run(**kwargs):
    return setup_command.run(setup_args(**kwargs))


# Preguntas de sí o no con una tecla: update y uninstall.


def keys_for(monkeypatch, text):
    chars = iter(text)
    monkeypatch.setattr(menu, "DEFAULT_READER", lambda: next(chars))


def test_update_asks_for_licenses_with_one_key(machine, monkeypatch):
    setup_command.run(setup_args())
    weights = machine.data / "comfyui" / "models" / "checkpoints" / "sd_xl_turbo_1.0_fp16.safetensors"
    weights.unlink()
    machine.downloads.clear()
    monkeypatch.setattr(maintenance, "is_interactive", lambda args: True)
    keys_for(monkeypatch, "n")
    args = argparse.Namespace(accept_licenses=False, non_interactive=False)

    with pytest.raises(ProvisionError, match="Nothing was changed"):
        maintenance.update(args)

    assert machine.downloads == []
    keys_for(monkeypatch, "y")
    assert maintenance.update(args) == 0
    assert machine.downloads == ["sdxl_turbo"]


def test_uninstall_asks_with_one_key(machine, monkeypatch, capsys):
    setup_command.run(setup_args())
    monkeypatch.setattr(maintenance.sys, "stdin", mock.Mock(isatty=lambda: True))
    args = argparse.Namespace(yes=False, remove_models=False, keep_models=False)
    keys_for(monkeypatch, "n")
    assert maintenance.uninstall(args) == 0
    assert "Nothing was removed." in capsys.readouterr().out
    assert (machine.data / "comfyui" / "main.py").exists()

    keys_for(monkeypatch, "0")
    assert maintenance.uninstall(args) == 0
    assert (machine.data / "comfyui" / "main.py").exists()

    # Continue yes, keep the models.
    keys_for(monkeypatch, "yn")
    assert maintenance.uninstall(args) == 0
    assert not (machine.data / "comfyui" / "main.py").exists()
    weights = machine.data / "comfyui" / "models" / "checkpoints" / "sd_xl_turbo_1.0_fp16.safetensors"
    assert weights.exists()
