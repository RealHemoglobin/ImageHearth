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

# Linux, GPU de 24 GB: perfiles fast (1), quality (2), full (3). Cada capacidad pide sus
# modelos con selección múltiple (Enter acepta lo recomendado) y la precisión de cada uno que
# tenga varias. Recomendado a 24 GB: Z-Image-Turbo bf16, Qwen-Image fp8 y Qwen-Image-Edit fp8.

DOWN = "\x1b[B"
# SDXL 1.0 is the first quality model and the recommended Qwen-Image the fifth: mark one,
# unmark the other.
SDXL = " " + DOWN * 4 + " " + "\r"


def interactive(**kwargs):
    return setup_args(
        **{
            "profile": None,
            "accept_licenses": False,
            "non_interactive": False,
            "fast_models": "sdxl-turbo",
            **kwargs,
        }
    )


def test_full_run_only_with_keys(machine, monkeypatch, capsys):
    # folder, profile quality, recommended fast model and precision, SDXL 1.0, no LoRAs, accept.
    press(monkeypatch, "12" + "\r" + "\r" + SDXL + "\r" + "1")
    assert setup_command.run(interactive(fast_models=None)) == 0
    output = capsys.readouterr().out

    for step in (1, 2, 3, 4, 5, 6, 7):
        assert f"Step {step} of " in output

    assert "Step 7 of 7" in output
    records = InstallManifest.load(config.INSTALL_MANIFEST)
    assert (records.profile, records.quality_model) == ("quality", "sdxl")
    assert records.models["fast"] == [{"model": "z-image-turbo", "precision": "bf16"}]


def test_enter_takes_the_recommended_answers(machine, monkeypatch):
    # folder, profile, then models and precision of fast, quality and editing, and accept.
    press(monkeypatch, "\r" * 9)
    assert setup_command.run(interactive(fast_models=None)) == 0
    records = InstallManifest.load(config.INSTALL_MANIFEST)
    assert records.profile == "full" and records.quality_model == "qwen-image"
    assert records.models == {
        "fast": [{"model": "z-image-turbo", "precision": "bf16"}],
        "high": [{"model": "qwen-image", "precision": "fp8"}],
        "edit": [{"model": "qwen-image-edit", "precision": "fp8"}],
    }


def test_zero_goes_back_and_keeps_answers(machine, monkeypatch, capsys):
    # profile quality, SDXL 1.0, no LoRAs; back from the review to the LoRAs and from there
    # to the models (SDXL 1.0 still marked), on to the LoRAs again and accept.
    press(monkeypatch, "12" + "\r" + "\r" + SDXL + "\r" + "0" + "0" + "\r" + "\r" + "1")
    assert setup_command.run(interactive(fast_models=None)) == 0
    output = capsys.readouterr().out
    assert output.count("Step 5 of 7") == 2 and output.count("Step 6 of 7") == 3
    assert InstallManifest.load(config.INSTALL_MANIFEST).quality_model == "sdxl"


def test_profile_without_quality_removes_the_model_steps(machine, monkeypatch, capsys):
    # quality, back from the fast models, fast, its model and precision, accept.
    press(monkeypatch, "1" + "2" + "0" + "1" + "\r" + "\r" + "1")
    assert setup_command.run(interactive(fast_models=None)) == 0
    output = capsys.readouterr().out
    assert "Step 5 of 5" in output
    records = InstallManifest.load(config.INSTALL_MANIFEST)
    assert records.profile == "fast" and records.quality_model is None


def test_zero_from_every_step_goes_back_one_at_a_time(machine, monkeypatch, capsys):
    # folder, profile, fast models and precision, SDXL 1.0, then back from the LoRAs, the
    # models, the precision, the models, the profile and the folder leaves with nothing written.
    press(monkeypatch, "12" + "\r" + "\r" + SDXL + "000000")
    assert setup_command.run(interactive(fast_models=None)) == 0
    assert "Nothing was changed." in capsys.readouterr().out
    assert not config.INSTALL_MANIFEST.exists()
    assert machine.downloads == []


def test_steps_resolved_by_arguments_are_not_shown(machine, monkeypatch, capsys):
    press(monkeypatch, "11")
    assert setup_command.run(interactive(profile="fast")) == 0
    output = capsys.readouterr().out
    assert "Step 2 of 2" in output and "Step 3" not in output
    assert "Profiles:" not in output and "Fast models" not in output


def test_quality_model_argument_hides_its_step(machine, monkeypatch, capsys):
    press(monkeypatch, "12\r1")
    assert setup_command.run(interactive(quality_model="sdxl")) == 0
    output = capsys.readouterr().out
    assert "Step 4 of 4" in output and "Quality models" not in output


def test_several_models_ask_for_the_default(machine, monkeypatch, capsys):
    # fast profile: mark Klein 4B (third) as well as the recommended Z-Image-Turbo (second),
    # precision of Z-Image-Turbo, then the default (the second in the list).
    press(monkeypatch, "1" + DOWN + DOWN + " " + "\r" + "\r" + "2" + "1")
    assert setup_command.run(interactive(profile="fast", fast_models=None)) == 0
    output = capsys.readouterr().out
    assert "Default fast model" in output
    records = InstallManifest.load(config.INSTALL_MANIFEST)
    assert [item["model"] for item in records.models["fast"]] == ["z-image-turbo", "klein-4b"]
    assert records.defaults["fast"] == "klein-4b"


def existing_comfy(machine):
    comfy = make_comfy(machine.tmp / "theirs")
    machine.detection.comfy_installs = [detect.ComfyInstall(str(comfy), "source", True)]
    return comfy


def test_existing_comfy_adds_the_mode_step(machine, monkeypatch, capsys):
    comfy = existing_comfy(machine)
    press(monkeypatch, "1" + "1" + "1" + "n")
    assert setup_command.run(interactive(profile="fast")) == 0
    output = capsys.readouterr().out
    assert "Step 1 of 3" in output and "Step 2 of 2" in output
    records = InstallManifest.load(config.INSTALL_MANIFEST)
    assert records.mode == "attached" and records.comfy_dir == str(comfy.resolve())


def test_existing_comfy_managed_option_and_back_to_mode(machine, monkeypatch):
    existing_comfy(machine)
    # Attach, review, back to the mode, managed, review.
    press(monkeypatch, "1" + "0" + "2" + "1" + "1")
    assert setup_command.run(interactive(profile="fast")) == 0
    assert InstallManifest.load(config.INSTALL_MANIFEST).mode == "managed"


def test_managed_argument_hides_the_mode_step(machine, monkeypatch, capsys):
    existing_comfy(machine)
    press(monkeypatch, "11")
    assert setup_command.run(interactive(profile="fast", managed=True)) == 0
    assert "Step 2 of 2" in capsys.readouterr().out


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
