"""Fase 15: instalar varios modelos por capacidad con `setup`, y cambiarlos."""

import argparse
import json

import pytest

from imagehearth_mcp.engine import config
from imagehearth_mcp.provisioner import (
    ProvisionError,
    detect,
    doctor,
    maintenance,
    manifest,
    models,
    preflight,
    quality,
)
from imagehearth_mcp.provisioner import setup as setup_command
from imagehearth_mcp.provisioner.install_manifest import InstallManifest
from imagehearth_mcp.provisioner.manifest import Pick
from tests.test_provisioner import machine, make_comfy, setup_args, torch_ok  # noqa: F401
from tests.test_quality_model import idle, on_disk, present  # noqa: F401


@pytest.fixture(autouse=True)
def gguf_node(monkeypatch):
    """The GGUF node is a download from GitHub: not part of these tests."""
    monkeypatch.setattr(setup_command.comfyui, "install_custom_node", lambda *a, **k: True)


def run(box, profile="full", **kwargs):
    kwargs.setdefault("legacy_models", False)
    return setup_command.run(setup_args(profile=profile, **kwargs))


def records():
    return InstallManifest.load(config.INSTALL_MANIFEST)


def stored(capability):
    return [(item["model"], item["precision"]) for item in records().models[capability]]


def lora_files(box):
    folder = box.data / "comfyui" / "models"
    return {name for name, lora in manifest.load().loras.items() if (folder / lora.dest).exists()}


def gpu(box, vram):
    box.detection.gpus = [detect.Gpu("nvidia", "RTX", "580.1", vram)]


# Instalación nueva


def test_several_models_in_each_capability_with_shared_weights_once(machine):
    run(
        machine,
        fast_models="klein-4b,sdxl-turbo",
        quality_models="chroma-hd:fp8",
        edit_models="klein-4b",
    )
    assert machine.downloads.count("klein_4b") == 1
    assert sorted(set(machine.downloads)) == sorted(machine.downloads)
    assert present(machine) == {
        "sdxl_turbo", "klein_4b", "qwen3_4b", "flux2_vae", "chroma_hd_fp8", "t5xxl", "flux_vae",
    }
    assert stored("fast") == [("klein-4b", "bf16"), ("sdxl-turbo", "fp16")]
    assert stored("high") == [("chroma-hd", "fp8")] and stored("edit") == [("klein-4b", "bf16")]
    assert records().defaults == {"fast": "klein-4b", "high": "chroma-hd", "edit": "klein-4b"}
    assert records().profile == "full"


def test_the_first_model_of_a_list_is_the_default(machine):
    run(machine, "fast", fast_models="sdxl-turbo,klein-4b")
    assert records().defaults == {"fast": "sdxl-turbo"}
    assert stored("fast") == [("sdxl-turbo", "fp16"), ("klein-4b", "bf16")]


def test_a_precision_is_chosen_with_name_and_colon(machine):
    run(machine, "quality", fast_models="z-image-turbo:int8", quality_models="qwen-image:Q4_K_M")
    assert stored("fast") == [("z-image-turbo", "int8")]
    assert stored("high") == [("qwen-image", "q4_k_m")]
    assert {"z_image_turbo_int8", "qwen3_4b_fp8", "qwen_image_q4_k_m"} <= present(machine)
    assert "z_image_turbo_bf16" not in present(machine) and "qwen3_4b" not in present(machine)


def test_without_a_precision_the_recommended_for_the_gpu(machine):
    gpu(machine, 16384)
    run(machine, "quality", fast_models="z-image-turbo", quality_models="qwen-image")
    assert stored("fast") == [("z-image-turbo", "bf16")] and stored("high") == [("qwen-image", "q4_k_m")]


def test_variant_gives_the_precision_to_models_that_do_not_name_one(machine):
    run(machine, "quality", fast_models="sdxl-turbo", quality_models="flux-dev", variant="gguf")
    assert stored("high") == [("flux-dev", "gguf")]


def test_nothing_asked_installs_the_recommended_for_each_capability(machine, capsys):
    gpu(machine, 8192)
    run(machine, "full")
    assert stored("fast") == [("klein-4b", "bf16")]
    assert stored("high") == [("chroma-hd", "fp8")]
    assert stored("edit") == [("klein-4b", "bf16")]
    output = capsys.readouterr().out
    assert output.count("recommended for 8192 MiB") == 3
    assert "--edit-models" in output


def test_a_run_with_the_old_alias(machine):
    run(machine, "quality", fast_models="sdxl-turbo", quality_model="sdxl")
    assert stored("high") == [("sdxl", "fp16")]


# Lo que se rechaza antes de descargar nada


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"profile": "quality", "fast_models": "nope"}, "Unknown model 'nope'.*klein-4b"),
        ({"profile": "quality", "fast_models": "z-image-turbo:fp4"}, "no fp4 precision.*bf16, int8"),
        ({"profile": "quality", "fast_models": "chroma-hd"}, "doesn't have the fast capability"),
        ({"profile": "quality", "quality_models": "klein-4b"}, "doesn't have the high capability"),
        ({"profile": "fast", "quality_models": "sdxl"}, "no high models"),
        ({"profile": "quality", "edit_models": "klein-4b"}, "no edit models"),
        ({"profile": "quality", "fast_models": "klein-4b,klein-4b:bf16"}, "listed twice"),
        ({"profile": "quality", "quality_models": "flux-dev", "loras": "all"}, "LoRAs only work"),
    ],
)
def test_bad_requests_change_nothing(machine, kwargs, message):
    kwargs = {"fast_models": "sdxl-turbo", **kwargs}

    with pytest.raises(ProvisionError, match=message):
        run(machine, **kwargs)

    assert machine.downloads == [] and machine.managed == []
    assert not config.INSTALL_MANIFEST.exists()


def test_not_enough_space_is_found_before_confirming(machine, monkeypatch, capsys):
    monkeypatch.setattr(
        preflight.shutil, "disk_usage", lambda path: type("U", (), {"free": 5})()
    )

    with pytest.raises(ProvisionError, match=r"(?s)Not enough disk space.*Nothing was changed"):
        run(machine, "quality", fast_models="klein-4b", quality_models="sdxl")

    assert machine.downloads == [] and not config.INSTALL_MANIFEST.exists()


def test_the_summary_with_hidream_lists_the_llama_license(capsys, tmp_path):
    catalog = manifest.load()
    profile = catalog.build_set(
        catalog.profiles["quality"],
        manifest.ModelSet(
            {"fast": (Pick("sdxl-turbo", "fp16"),), "high": (Pick("hidream-full", "fp8"),)}
        ),
    )
    setup_command.show_summary(catalog, profile, "managed", tmp_path, tmp_path, profile.bytes)
    output = capsys.readouterr().out
    assert "Llama 3.1 Community License" in output and "Built with Llama" in output
    assert "MIT" in output


# Cambiar el conjunto


def installed_two(box):
    run(box, "full", fast_models="sdxl-turbo,klein-4b", quality_models="chroma-hd:fp8,sdxl",
        edit_models="klein-4b")
    box.downloads.clear()


def test_adding_a_model_needs_no_confirmation_and_keeps_the_rest(machine):
    run(machine, "quality", fast_models="sdxl-turbo", quality_models="sdxl")
    machine.downloads.clear()
    run(machine, "quality", quality_models="sdxl,chroma-hd:fp8")
    assert stored("high") == [("sdxl", "fp16"), ("chroma-hd", "fp8")]
    assert stored("fast") == [("sdxl-turbo", "fp16")]
    assert machine.downloads == ["chroma_hd_fp8", "t5xxl", "flux_vae"]


def test_a_fixed_set_removes_what_is_left_out_but_asks_first(machine):
    installed_two(machine)

    with pytest.raises(ProvisionError, match="needs --yes"):
        run(machine, "quality", fast_models="klein-4b")

    assert "sdxl_turbo" in present(machine)
    run(machine, "quality", fast_models="klein-4b", yes=True)
    assert stored("fast") == [("klein-4b", "bf16")]
    assert "sdxl_turbo" not in present(machine)
    # Not asked for: untouched.
    assert stored("high") == [("chroma-hd", "fp8"), ("sdxl", "fp16")]
    assert stored("edit") == [("klein-4b", "bf16")]
    assert "klein_4b" in present(machine)


def test_shared_weights_stay_while_another_model_uses_them(machine):
    run(machine, "full", fast_models="klein-4b,z-image-turbo:bf16", quality_models="sdxl",
        edit_models="klein-4b")
    run(machine, "full", fast_models="z-image-turbo:bf16", yes=True)
    assert "klein_4b" in present(machine)  # still the editing model
    run(machine, "full", edit_models="kontext", yes=True)
    assert "klein_4b" not in present(machine) and "flux2_vae" not in present(machine)
    # The Qwen3 encoder: Z-Image still needs it.
    assert "qwen3_4b" in present(machine)


def test_a_precision_change_downloads_before_it_deletes(machine, monkeypatch):
    run(machine, "quality", fast_models="z-image-turbo:bf16", quality_models="sdxl")
    machine.downloads.clear()
    order = []
    real = quality.delete_items

    def spy(items, records):
        order.append(("delete", on_disk(machine, "z_image_turbo_int8").exists(), sorted(i.model.name for i in items)))
        return real(items, records)

    monkeypatch.setattr(quality, "delete_items", spy)
    run(machine, "quality", fast_models="z-image-turbo:int8", yes=True)
    assert order == [("delete", True, ["qwen3_4b", "z_image_turbo_bf16"])]
    assert stored("fast") == [("z-image-turbo", "int8")]
    assert machine.downloads == ["z_image_turbo_int8", "qwen3_4b_fp8"]
    assert "qwen3_4b" not in present(machine)


def test_the_plan_names_what_changes_and_why(machine, capsys):
    run(machine, "quality", fast_models="z-image-turbo:bf16", quality_models="sdxl")
    capsys.readouterr()
    run(machine, "quality", fast_models="z-image-turbo:int8", yes=True)
    output = capsys.readouterr().out
    assert "~ Z-Image-Turbo: bf16 -> int8" in output
    assert "To download:" in output and "To delete afterwards: z_image_turbo_bf16" in output
    assert "Z-Image-Turbo bf16 -> int8" in output  # the reason


def test_an_interrupted_change_leaves_the_record_as_it_was(machine, monkeypatch):
    run(machine, "quality", fast_models="sdxl-turbo", quality_models="sdxl")
    real = models.ensure_models

    def fail(items, folder, records_):
        raise ProvisionError("connection lost")

    monkeypatch.setattr(models, "ensure_models", fail)

    with pytest.raises(ProvisionError, match="connection lost"):
        run(machine, "quality", quality_models="chroma-hd:fp8", yes=True)

    monkeypatch.setattr(models, "ensure_models", real)
    assert stored("high") == [("sdxl", "fp16")]
    assert "sdxl_base" in present(machine)


def test_what_the_user_already_had_or_a_foreign_comfyui_is_never_deleted(machine):
    comfy = make_comfy(machine.tmp / "theirs")
    attached = {"attach": str(comfy), "install_node": True}
    run(machine, "quality", fast_models="klein-4b", quality_models="sdxl", **attached)
    run(machine, "quality", fast_models="sdxl-turbo", yes=True, **attached)
    assert (comfy / "models" / manifest.load().models["klein_4b"].dest).exists()
    assert stored("fast") == [("sdxl-turbo", "fp16")]


def test_a_bigger_profile_adds_the_recommended_model_and_keeps_the_rest(machine):
    run(machine, "quality", fast_models="sdxl-turbo", quality_models="sdxl")
    run(machine, "full")
    assert stored("fast") == [("sdxl-turbo", "fp16")] and stored("high") == [("sdxl", "fp16")]
    assert stored("edit") == [("qwen-image-edit", "fp8")]


def test_a_smaller_profile_never_removes_models(machine):
    run(machine, "full", fast_models="sdxl-turbo", quality_models="sdxl", edit_models="kontext")
    machine.downloads.clear()
    run(machine, "fast", fast_models="sdxl-turbo")
    assert records().profile == "full" and stored("edit") == [("kontext", "fp8")]
    assert machine.downloads == []


def test_changing_to_a_model_without_sdxl_deletes_the_loras(machine):
    run(machine, "quality", fast_models="sdxl-turbo", quality_models="sdxl", loras="all")
    assert lora_files(machine) == set(manifest.load().loras)
    run(machine, "quality", quality_models="chroma-hd:fp8", yes=True)
    assert lora_files(machine) == set()


def test_realvisxl_is_replaced_when_a_quality_model_is_chosen(machine, capsys):
    from tests.test_quality_model import old_record, put

    put(machine, "sdxl_turbo", "realvisxl", "sdxl_offset_lora")
    old_record(machine, "quality-sdxl")
    run(machine, "quality", quality_models="sdxl", yes=True)
    # A RealVisXL that setup didn't install is not setup's to delete.
    assert "realvisxl" in present(machine)
    assert stored("high") == [("sdxl", "fp16")] and not records().legacy_quality
    assert "sdxl_base" in present(machine)


# Registro, doctor, uninstall y actualización


def test_the_record_keeps_what_an_older_version_read(machine):
    run(machine, "full", fast_models="sdxl-turbo", quality_models="sdxl", edit_models="klein-4b")
    saved = records()
    assert (saved.quality_model, saved.precision, saved.edit_precision) == ("sdxl", "fp16", "bf16")
    data = json.loads(config.INSTALL_MANIFEST.read_text(encoding="utf-8"))
    assert data["models"]["edit"] == [{"model": "klein-4b", "precision": "bf16"}]


def test_doctor_lists_the_models_by_capability(machine):
    installed_two(machine)
    check = doctor.check_quality_model(config, records(), manifest.load())
    listing = check.details["models"]
    assert [item["model"] for item in listing["fast"]] == ["sdxl-turbo", "klein-4b"]
    assert [item["default"] for item in listing["fast"]] == [True, False]
    assert "Fast:" in check.message and "Editing: klein-4b bf16" in check.message
    models_check = doctor.check_models(config, records(), manifest.load(), False, "linux")
    assert models_check.status == doctor.OK and models_check.details["profiles"] == {
        "fast": True, "quality": True, "full": True,
    }


def test_doctor_finds_a_missing_weight_of_a_second_model(machine):
    installed_two(machine)
    on_disk(machine, "chroma_hd_fp8").unlink()
    check = doctor.check_models(config, records(), manifest.load(), False, "linux")
    assert check.status == doctor.FAIL and "chroma_hd_fp8" in check.details["problems"]


def test_update_downloads_a_missing_weight_of_any_model(machine):
    installed_two(machine)
    on_disk(machine, "chroma_hd_fp8").unlink()
    maintenance.update(argparse.Namespace(accept_licenses=True, non_interactive=True))
    assert machine.downloads == ["chroma_hd_fp8"]


def test_uninstall_removes_every_model_it_installed(machine):
    installed_two(machine)
    foreign = machine.data / "comfyui" / "models" / "checkpoints" / "mine.safetensors"
    foreign.parent.mkdir(parents=True, exist_ok=True)
    foreign.write_bytes(b"mine")
    args = argparse.Namespace(yes=True, remove_models=True, keep_models=False)
    assert maintenance.uninstall(args) == 0
    assert present(machine) == set()
    assert foreign.read_bytes() == b"mine"


# `setup_status` y `setup_start`


def test_status_has_every_model_with_measures_for_this_gpu(machine, monkeypatch):
    from imagehearth_mcp.provisioner import agent_setup

    monkeypatch.setattr(agent_setup.sys, "platform", "linux")
    run(machine, "full", fast_models="klein-4b", quality_models="chroma-hd:fp8", edit_models="klein-4b")
    status = agent_setup.status()
    klein = next(i for i in status["models"]["fast"] if i["name"] == "klein-4b")
    assert klein["installed"] and klein["default"] and klein["installed_precision"] == "bf16"
    assert klein["precisions"][0]["seconds_per_image"] == 1.3
    assert klein["license"]["name"] == "Apache-2.0" and klein["commercial_use"]
    qwen = next(i for i in status["models"]["high"] if i["name"] == "qwen-image")
    assert [p["precision"] for p in qwen["precisions"]] == ["bf16", "fp8", "q4_k_m", "q2_k"]
    assert qwen["recommended"] and next(p for p in qwen["precisions"] if p["precision"] == "fp8")["recommended"]
    assert next(p for p in qwen["precisions"] if p["precision"] == "bf16")["moves_to_ram_gb"] > 0
    assert status["installed_models"]["edit"] == [
        {"model": "klein-4b", "precision": "bf16", "default": True}
    ]
    assert next(i for i in status["models"]["edit"] if i["name"] == "kontext")["commercial_use"] is False


def test_start_takes_the_three_lists(machine, monkeypatch):
    from imagehearth_mcp.provisioner import agent_setup

    spawned = []

    class Process:
        pid = 1

    for name, value in {
        "SETUP_JOB_LOCK": machine.tmp / "job.lock",
        "SETUP_JOB_FILE": machine.tmp / "job.json",
        "SETUP_JOB_LOG": machine.tmp / "job.log",
    }.items():
        monkeypatch.setattr(config, name, value)

    monkeypatch.setattr(agent_setup, "_spawn", lambda *a: spawned.append(a) or Process())
    monkeypatch.setattr(agent_setup.processes, "create_time", lambda pid: 1.0)
    monkeypatch.setattr(agent_setup.sys, "platform", "linux")
    result = agent_setup.start(
        "full", True, fast_models=["klein-4b", "sdxl-turbo"], quality_models=["qwen-image:q4_k_m"],
        edit_models=["klein-4b"],
    )
    assert spawned == [("full", "", "qwen-image:q4_k_m", "", "", "klein-4b,sdxl-turbo", "klein-4b")]
    assert result["models"] == {
        "fast": ["klein-4b:bf16", "sdxl-turbo:fp16"],
        "high": ["qwen-image:q4_k_m"],
        "edit": ["klein-4b:bf16"],
    }
    assert result["defaults"] == {"fast": "klein-4b", "high": "qwen-image", "edit": "klein-4b"}
    args = agent_setup._args(*spawned[0])
    assert (args.fast_models, args.quality_models, args.edit_models) == (
        "klein-4b,sdxl-turbo", "qwen-image:q4_k_m", "klein-4b",
    )
    assert args.yes and args.accept_licenses


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"fast_models": ["nope"]}, "Unknown model 'nope'"),
        ({"quality_models": ["klein-4b"]}, "doesn't have the high capability"),
        ({"fast_models": "klein-4b"}, "must be a list"),
        ({"profile": "fast", "quality_models": ["sdxl"]}, "no high models"),
        ({"quality_models": ["flux-dev"], "loras": ["all"]}, "LoRAs only work with the sdxl"),
    ],
)
def test_start_refuses_bad_lists_before_spawning(machine, monkeypatch, kwargs, message):
    from imagehearth_mcp.provisioner import agent_setup

    monkeypatch.setattr(agent_setup.sys, "platform", "linux")
    monkeypatch.setattr(agent_setup, "_spawn", lambda *a: pytest.fail("spawned"))
    kwargs = {"profile": "quality", **kwargs}

    with pytest.raises(ValueError, match=message):
        agent_setup.start(kwargs.pop("profile"), True, **kwargs)


def test_an_empty_list_changes_nothing(machine, monkeypatch):
    from imagehearth_mcp.provisioner import agent_setup

    run(machine, "quality", fast_models="klein-4b", quality_models="sdxl")
    spawned = []

    class Process:
        pid = 1

    for name, value in {
        "SETUP_JOB_LOCK": machine.tmp / "job.lock",
        "SETUP_JOB_FILE": machine.tmp / "job.json",
        "SETUP_JOB_LOG": machine.tmp / "job.log",
    }.items():
        monkeypatch.setattr(config, name, value)

    monkeypatch.setattr(agent_setup, "_spawn", lambda *a: spawned.append(a) or Process())
    monkeypatch.setattr(agent_setup.processes, "create_time", lambda pid: 1.0)
    monkeypatch.setattr(agent_setup.sys, "platform", "linux")
    result = agent_setup.start("quality", True, fast_models=[], quality_models=None)
    assert spawned == [("quality", "", "")] and "replaces" not in result
    assert result["models"]["fast"] == ["klein-4b:bf16"]


# `update --move-to` con varios modelos y componentes compartidos


def test_a_move_keeps_every_model_and_the_shared_weights(machine, monkeypatch, tmp_path):
    from tests.test_move import FakeRun, move, other_disk, tree, update

    monkeypatch.setattr(config, "LOCK_FILE", machine.data / "engine.lock")
    monkeypatch.setattr(config, "STATE_FILE", machine.data / "state" / "session.json")
    monkeypatch.setattr(setup_command.comfyui, "find_uv", lambda which=None: "/bin/uv")
    run(machine, "full", fast_models="klein-4b,z-image-turbo:bf16", quality_models="sdxl",
        edit_models="klein-4b")
    machine.run = FakeRun()
    monkeypatch.setattr(move.subprocess, "run", machine.run)
    other_disk(monkeypatch)
    before = present(machine)
    target = tmp_path / "disk2" / "ImageHearth"
    assert update(target) == 0
    saved = records()
    assert saved.comfy_dir == str(target / "comfyui")
    assert stored("fast") == [("klein-4b", "bf16"), ("z-image-turbo", "bf16")]
    assert stored("edit") == [("klein-4b", "bf16")]
    moved = {
        name
        for name in manifest.load().models
        if (target / "comfyui" / "models" / manifest.load().models[name].dest).exists()
    }
    assert moved == before and "qwen3_4b" in moved and not tree(machine.data / "comfyui")
