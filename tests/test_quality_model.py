"""Elección y cambio del modelo de `quality` (fase 9)."""

import io
import json
import struct
import zlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from imagehearth_mcp import cli
from imagehearth_mcp.engine import catalog as engine_catalog
from imagehearth_mcp.engine import comfyui_manager, config, workflow_runner
from imagehearth_mcp.engine import status as engine_status
from imagehearth_mcp.provisioner import (
    ProvisionError,
    agent_setup,
    detect,
    doctor,
    manifest,
    models,
    quality,
)
from imagehearth_mcp.provisioner import setup as setup_command
from imagehearth_mcp.provisioner.install_manifest import InstallManifest
from tests.test_catalog import install, models_dir, tiny  # noqa: F401
from tests.test_provisioner import fake_download, machine, setup_args, torch_ok  # noqa: F401

REAL_ENSURE = models.ensure_models


@pytest.fixture(autouse=True)
def idle(tmp_path, monkeypatch):
    """Sin generación en curso ni sesión pendiente, aunque la máquina real tenga una."""
    monkeypatch.setattr(config, "LOCK_FILE", tmp_path / "engine.lock")
    monkeypatch.setattr(config, "STATE_FILE", tmp_path / "state.json")


def on_disk(box, name):
    records = InstallManifest.load(config.INSTALL_MANIFEST)
    path = models.resolve_dir(records, box.data / "comfyui") / manifest.load().models[name].dest
    return path


def present(box):
    return {name for name in manifest.load().models if on_disk(box, name).exists()}


def gpu(box, vram):
    box.detection.gpus = [detect.Gpu("nvidia", "RTX", "580.1", vram)]


# Instalación nueva


def test_quality_model_option_installs_only_that_model(machine):
    setup_command.run(setup_args(profile="quality", quality_model="flux-schnell"))
    assert present(machine) == {"sdxl_turbo", "flux_schnell", "t5xxl", "clip_l", "flux_vae"}
    records = InstallManifest.load(config.INSTALL_MANIFEST)
    assert (records.profile, records.quality_model, records.precision) == (
        "quality",
        "flux-schnell",
        "fp8",
    )


def test_sdxl_in_quality_downloads_no_flux_file(machine):
    setup_command.run(setup_args(profile="quality", quality_model="sdxl"))
    assert present(machine) == {"sdxl_turbo", "sdxl_base", "sdxl_offset_lora"}


def test_full_with_sdxl_keeps_the_flux_components_for_kontext(machine):
    setup_command.run(setup_args(profile="full", quality_model="sdxl"))
    assert {"flux_kontext", "t5xxl", "clip_l", "flux_vae", "sdxl_base"} <= present(machine)
    assert "flux_dev" not in present(machine)


def test_without_a_model_the_recommendation_is_used_and_announced(machine, capsys):
    setup_command.run(setup_args(profile="quality"))
    assert "flux_dev" in present(machine)
    assert "recommended" in capsys.readouterr().out



def test_the_recommendation_follows_the_gpu_memory(machine, capsys):
    gpu(machine, 16000)
    setup_command.run(setup_args(profile="quality"))
    assert InstallManifest.load(config.INSTALL_MANIFEST).quality_model == "flux-schnell"
    assert "flux_schnell" in present(machine)


def test_a_model_that_does_not_fit_is_installed_with_a_warning(machine, capsys, monkeypatch):
    monkeypatch.setattr(setup_command.comfyui, "install_custom_node", lambda *a, **k: True)
    gpu(machine, 8192)
    setup_command.run(setup_args(profile="quality", quality_model="flux-dev"))
    output = capsys.readouterr().out
    assert "WARNING" in output and "8192 MiB" in output
    assert InstallManifest.load(config.INSTALL_MANIFEST).quality_model == "flux-dev"


def test_quality_model_makes_no_sense_for_fast(machine):
    with pytest.raises(ProvisionError, match="no quality model"):
        setup_command.run(setup_args(profile="fast", quality_model="sdxl"))

    assert machine.downloads == []


def test_interactive_choice_shows_size_vram_license_and_recommendation(machine, monkeypatch, capsys):
    monkeypatch.setattr(setup_command, "is_interactive", lambda args: True)
    answers = iter(["sdxl"])
    prompts = []

    def fake_input(prompt):
        prompts.append(prompt)
        return next(answers)

    monkeypatch.setattr("builtins.input", fake_input)
    setup_command.run(setup_args(profile="quality", non_interactive=False))
    output = capsys.readouterr().out
    assert "Quality model [flux-dev]" in prompts[0]

    for name in ("flux-dev", "flux-schnell", "sdxl"):
        assert name in output

    assert "recommended" in output and "GB VRAM" in output
    assert "non-commercial" in output and "commercial use" in output
    assert InstallManifest.load(config.INSTALL_MANIFEST).quality_model == "sdxl"


def test_interactive_choice_rejects_an_unknown_model(machine, monkeypatch):
    monkeypatch.setattr(setup_command, "is_interactive", lambda args: True)
    monkeypatch.setattr("builtins.input", lambda prompt: "nope")

    with pytest.raises(ProvisionError, match="Unknown quality model"):
        setup_command.run(setup_args(profile="quality", non_interactive=False))

    assert machine.downloads == []


def test_cli_accepts_the_three_models():
    parser = cli._build_parser()

    for name in ("flux-dev", "flux-schnell", "sdxl"):
        assert parser.parse_args(["setup", "--quality-model", name]).quality_model == name

    with pytest.raises(SystemExit):
        parser.parse_args(["setup", "--quality-model", "realvisxl"])

    assert parser.parse_args(["setup", "--yes"]).yes


# Cambio de modelo


def switch(box, new, profile="quality", **kwargs):
    return setup_command.run(setup_args(profile=profile, quality_model=new, yes=True, **kwargs))


def test_switching_downloads_first_then_deletes_the_old_model(machine, monkeypatch):
    setup_command.run(setup_args(profile="quality", quality_model="flux-dev"))
    machine.downloads.clear()
    order = []
    real_delete = quality.delete_old

    def spy(change, records):
        # By now the new model is on disk and the record already points to it.
        order.append(("delete", on_disk(machine, "sdxl_base").exists(), records.quality_model))
        return real_delete(change, records)

    monkeypatch.setattr(quality, "delete_old", spy)
    switch(machine, "sdxl")
    assert "sdxl_base" in machine.downloads
    assert order == [("delete", True, "sdxl")]
    # Gone: FLUX Dev and what only it used. Kept: Turbo, and the LoRA now used by SDXL.
    assert present(machine) == {"sdxl_turbo", "sdxl_base", "sdxl_offset_lora"}
    assert InstallManifest.load(config.INSTALL_MANIFEST).quality_model == "sdxl"


def test_switch_prints_the_plan(machine, capsys):
    setup_command.run(setup_args(profile="quality", quality_model="flux-dev"))
    capsys.readouterr()
    switch(machine, "flux-schnell")
    output = capsys.readouterr().out
    assert "FLUX.1 Dev -> FLUX.1 Schnell" in output
    assert "To download" in output and "flux_dev_fp8_scaled" in output and "Space freed" in output


def test_switch_needs_confirmation_when_not_interactive(machine):
    setup_command.run(setup_args(profile="quality", quality_model="flux-dev"))
    machine.downloads.clear()

    with pytest.raises(ProvisionError, match="--yes"):
        setup_command.run(setup_args(profile="quality", quality_model="sdxl"))

    assert machine.downloads == []
    assert "flux_dev" in present(machine)


def test_interactive_switch_declined_changes_nothing(machine, monkeypatch):
    setup_command.run(setup_args(profile="quality", quality_model="flux-dev"))
    monkeypatch.setattr(setup_command, "is_interactive", lambda args: True)
    monkeypatch.setattr("builtins.input", lambda prompt: "n")

    with pytest.raises(ProvisionError, match="not confirmed"):
        setup_command.run(setup_args(profile="quality", quality_model="sdxl", non_interactive=False))

    assert "flux_dev" in present(machine)
    assert InstallManifest.load(config.INSTALL_MANIFEST).quality_model == "flux-dev"


def test_running_setup_again_keeps_the_installed_model(machine):
    setup_command.run(setup_args(profile="quality", quality_model="flux-schnell"))
    machine.downloads.clear()
    setup_command.run(setup_args(profile="quality"))
    assert machine.downloads == []
    assert InstallManifest.load(config.INSTALL_MANIFEST).quality_model == "flux-schnell"


def test_interrupted_switch_leaves_the_previous_model_working(machine, monkeypatch):
    setup_command.run(setup_args(profile="quality", quality_model="flux-dev"))
    before = present(machine)
    failing = {"on": True}

    def download(model, local_dir):
        if failing["on"] and model.name == "sdxl_base":
            raise ProvisionError("connection lost")

        return fake_download(model.name.encode())(model, local_dir)

    monkeypatch.setattr(
        models, "ensure_models", lambda m, d, r: REAL_ENSURE(m, d, r, download, lambda text: None)
    )

    with pytest.raises(ProvisionError, match="connection lost"):
        switch(machine, "sdxl")

    assert before <= present(machine)
    records = InstallManifest.load(config.INSTALL_MANIFEST)
    assert records.quality_model == "flux-dev"
    assert records.is_owned(on_disk(machine, "flux_dev"))

    failing["on"] = False
    switch(machine, "sdxl")
    assert "flux_dev" not in present(machine) and "sdxl_base" in present(machine)


def test_shared_files_are_kept_when_kontext_uses_them(machine):
    setup_command.run(setup_args(profile="full", quality_model="flux-dev"))
    switch(machine, "sdxl", profile="quality")
    kept = present(machine)
    assert "flux_dev" not in kept
    assert {"flux_kontext", "t5xxl", "clip_l", "flux_vae", "sdxl_base"} <= kept
    assert InstallManifest.load(config.INSTALL_MANIFEST).profile == "full"


def test_shared_files_are_kept_when_the_new_model_uses_them(machine):
    setup_command.run(setup_args(profile="quality", quality_model="flux-dev"))
    machine.downloads.clear()
    switch(machine, "flux-schnell")
    assert machine.downloads == ["flux_schnell"]
    assert {"t5xxl", "clip_l", "flux_vae", "flux_schnell"} <= present(machine)
    assert "flux_dev" not in present(machine)


def test_preexisting_models_are_never_deleted(machine):
    folder = machine.data / "comfyui" / "models"
    preexisting = folder / manifest.load().models["flux_dev"].dest
    preexisting.parent.mkdir(parents=True)
    preexisting.write_bytes(b"flux_dev")
    setup_command.run(setup_args(profile="quality", quality_model="flux-dev"))
    switch(machine, "sdxl")
    assert preexisting.exists()


def test_models_of_an_attached_comfyui_are_never_deleted(machine, capsys):
    from tests.test_provisioner import make_comfy

    comfy = make_comfy(machine.tmp / "theirs")
    attached = {"attach": str(comfy), "install_node": True}
    setup_command.run(setup_args(profile="quality", quality_model="flux-dev", **attached))
    dev = comfy / "models" / manifest.load().models["flux_dev"].dest
    assert dev.exists()
    switch(machine, "sdxl", **attached)
    assert dev.exists()
    assert (comfy / "models" / manifest.load().models["sdxl_base"].dest).exists()
    assert InstallManifest.load(config.INSTALL_MANIFEST).quality_model == "sdxl"
    assert "stays" in capsys.readouterr().out


def test_switch_is_refused_while_an_image_is_being_made(machine, monkeypatch):
    setup_command.run(setup_args(profile="quality", quality_model="flux-dev"))
    machine.downloads.clear()
    monkeypatch.setattr(quality.locks, "is_locked", lambda path: True)

    with pytest.raises(ProvisionError, match="being generated"):
        switch(machine, "sdxl")

    assert machine.downloads == []
    assert InstallManifest.load(config.INSTALL_MANIFEST).quality_model == "flux-dev"


def test_switch_is_refused_with_a_session_to_recover(machine):
    setup_command.run(setup_args(profile="quality", quality_model="flux-dev"))
    config.STATE_FILE.write_text(json.dumps({"phase": "generating"}), encoding="utf-8")

    with pytest.raises(ProvisionError, match="recover_engine"):
        switch(machine, "sdxl")


def test_managed_comfyui_is_restarted_after_a_switch(machine, monkeypatch):
    setup_command.run(setup_args(profile="quality", quality_model="flux-dev"))
    restarted = []
    monkeypatch.setattr(comfyui_manager, "managed_pid", lambda: 4242)
    monkeypatch.setattr(comfyui_manager, "restart", lambda: restarted.append(True))
    switch(machine, "sdxl")
    assert restarted == [True]


def test_not_enough_space_for_both_models_is_detected_before_downloading(machine, monkeypatch):
    setup_command.run(setup_args(profile="quality", quality_model="flux-dev"))
    machine.downloads.clear()
    monkeypatch.setattr(
        setup_command.preflight.shutil, "disk_usage", lambda path: SimpleNamespace(free=1000)
    )

    with pytest.raises(ProvisionError, match="disk space"):
        switch(machine, "sdxl")

    assert machine.downloads == []
    assert "flux_dev" in present(machine)


# Instalaciones anteriores


def old_record(box, profile, **fields):
    records = InstallManifest(config.INSTALL_MANIFEST)
    records.mode = "managed"
    records.comfy_dir = str(box.data / "comfyui")
    records.profile = profile
    records.__dict__.update(fields)
    records._normalize_legacy_profile()
    records.save()
    return InstallManifest.load(config.INSTALL_MANIFEST)


def put(box, *names):
    for name in names:
        path = box.data / "comfyui" / "models" / manifest.load().models[name].dest
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(name.encode())


def test_old_record_with_flux_dev_is_deduced(machine):
    put(machine, "flux_dev")
    records = old_record(machine, "quality")
    found = quality.current(manifest.load(), records, machine.data / "comfyui" / "models")
    assert found == quality.Current("flux-dev")


def test_old_gguf_record_is_deduced_with_its_precision(machine):
    put(machine, "flux_dev_gguf")
    records = old_record(machine, "quality-gguf")
    assert (records.profile, records.precision) == ("quality", "gguf")
    found = quality.current(manifest.load(), records, machine.data / "comfyui" / "models")
    assert found == quality.Current("flux-dev")
    profile = quality.resolve_installed(manifest.load(), records, machine.data / "comfyui" / "models")
    assert profile.name == "quality-gguf" and "flux_dev_gguf" in {m.name for m in profile.models}


def test_old_full_gguf_record_keeps_kontext_gguf(machine):
    records = old_record(machine, "full-gguf")
    assert (records.profile, records.precision, records.edit_precision) == ("full", "gguf", "gguf")


def test_old_record_with_realvisxl_is_legacy(machine):
    put(machine, "realvisxl")
    records = old_record(machine, "quality-sdxl")
    folder = machine.data / "comfyui" / "models"
    assert quality.current(manifest.load(), records, folder) == quality.Current("sdxl", legacy=True)
    profile = quality.resolve_installed(manifest.load(), records, folder)
    assert {"realvisxl", "sdxl_offset_lora"} <= {m.name for m in profile.models}
    assert "sdxl_base" not in {m.name for m in profile.models}


def test_old_installations_keep_generating(tiny, tmp_path):
    install(models_dir(), tiny, "quality")
    assert "flux_dev" in engine_catalog.entries() and engine_catalog.entries()["flux_dev"].installed
    assert engine_catalog.choose("high", 24564) == "flux_dev"

    for model in ("realvisxl", "sdxl_offset_lora"):
        path = models_dir() / tiny.models[model].dest
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(model.encode())

    (models_dir() / tiny.models["flux_dev"].dest).unlink()
    assert engine_catalog.choose("high", 24564) == "sdxl_quality"
    assert engine_catalog.active_quality_model()["name"] == "sdxl"


def test_legacy_installation_is_not_changed_without_asking(machine, capsys):
    put(machine, "sdxl_turbo", "realvisxl", "sdxl_offset_lora")
    old_record(machine, "quality-sdxl")
    setup_command.run(setup_args(profile="quality"))
    assert "sdxl_base" not in present(machine) and "realvisxl" in present(machine)
    assert "no longer offered" in capsys.readouterr().out


def test_legacy_installation_moves_to_sdxl_and_deletes_realvisxl_if_owned(machine):
    setup_command.run(setup_args(profile="quality", quality_model="sdxl"))
    # Make it look like a record from before the phase: RealVisXL installed by us.
    records = InstallManifest.load(config.INSTALL_MANIFEST)
    put(machine, "realvisxl")
    real = on_disk(machine, "realvisxl")
    records.claim_verified("model", real)
    records.quality_model = None
    records.save()
    on_disk(machine, "sdxl_base").unlink()
    assert quality.current(manifest.load(), records, real.parents[1]).legacy

    switch(machine, "sdxl")
    assert not real.exists()
    assert "sdxl_base" in present(machine)
    assert InstallManifest.load(config.INSTALL_MANIFEST).quality_model == "sdxl"


def test_preexisting_realvisxl_is_not_deleted(machine):
    put(machine, "sdxl_turbo", "realvisxl", "sdxl_offset_lora")
    old_record(machine, "quality-sdxl")
    switch(machine, "sdxl")
    assert "sdxl_base" in present(machine) and "realvisxl" in present(machine)


# doctor, estado y listado


def test_doctor_reports_the_quality_model_and_its_license(machine):
    setup_command.run(setup_args(profile="quality", quality_model="flux-schnell"))
    records = InstallManifest.load(config.INSTALL_MANIFEST)
    check = doctor.check_quality_model(config, records, manifest.load())
    assert check.status == doctor.OK
    assert check.details["name"] == "flux-schnell" and check.details["commercial_use"] is True
    assert "Apache" in check.message


def test_doctor_flags_a_migratable_installation(machine):
    put(machine, "realvisxl")
    records = old_record(machine, "quality-sdxl")
    check = doctor.check_quality_model(config, records, manifest.load())
    assert check.status == doctor.WARN
    assert "--quality-model sdxl" in check.fix and check.details["legacy"]


def test_doctor_models_check_follows_the_installed_model(machine):
    setup_command.run(setup_args(profile="quality", quality_model="sdxl"))
    records = InstallManifest.load(config.INSTALL_MANIFEST)
    check = doctor.check_models(config, records, manifest.load(), False, "linux")
    assert check.status == doctor.OK


def test_active_model_comes_from_the_installed_workflow(tiny):
    assert engine_catalog.active_quality_model() is None
    install(models_dir(), tiny, "quality", "flux-schnell")
    active = engine_catalog.active_quality_model()
    assert active["name"] == "flux-schnell" and active["workflow"] == "flux_schnell"
    assert active["commercial_use"] is True and "Apache" in active["license"]
    assert engine_catalog.choose("high", 24564) == "flux_schnell"


def test_catalog_offers_only_the_installed_quality_workflow(tiny):
    install(models_dir(), tiny, "quality", "sdxl")
    entries = engine_catalog.entries()
    assert entries["sdxl_base"].installed and entries["sdxl_base"].quality_model == "sdxl"
    assert not entries["flux_schnell"].installed and not entries["flux_dev"].installed
    assert engine_catalog.choose("high", 24564) == "sdxl_base"


def test_list_workflows_marks_the_active_model(tiny):
    from imagehearth_mcp.server import list_workflows

    install(models_dir(), tiny, "quality", "flux-dev")
    items = {item["name"]: item for item in list_workflows()}
    assert items["flux_dev"]["active"] and items["flux_dev"]["quality_model"] == "flux-dev"
    assert items["flux_dev"]["commercial_use"] is False
    assert "quality_model" not in items["sdxl_turbo"]


def test_engine_status_includes_the_quality_model(tiny, monkeypatch):
    install(models_dir(), tiny, "quality", "sdxl")
    monkeypatch.setattr(engine_status, "_comfyui_status", lambda: {"status": "running", "gpu_devices": []})
    monkeypatch.setattr(engine_status, "_ollama_status", lambda: {"status": "disabled"})
    monkeypatch.setattr(engine_status, "_status_node_issue", lambda: None)
    monkeypatch.setattr(engine_status.memory, "describe", dict)
    monkeypatch.setattr(engine_status.gpu, "free_mib", lambda: 1000)
    monkeypatch.setattr(engine_status.orchestrator, "is_busy", lambda: False)
    monkeypatch.setattr(engine_status.state, "read", lambda: None)
    result = engine_status.get_status()
    assert result["imageengine"]["quality_model"]["name"] == "sdxl"


def test_not_installed_error_names_the_quality_model(tiny):
    from imagehearth_mcp.engine.validation import resolve_workflow

    with pytest.raises(ValueError, match="--profile quality --quality-model flux-schnell"):
        resolve_workflow("flux_schnell", "high")


# Metadatos del PNG


def png_with_comfy_text():
    from PIL.PngImagePlugin import PngInfo

    info = PngInfo()
    info.add_text("prompt", '{"1": {}}')
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(buffer, "PNG", pnginfo=info)
    return buffer.getvalue()


def test_png_carries_model_and_workflow_and_keeps_comfyuis_text(tmp_path):
    path = tmp_path / "image.png"
    path.write_bytes(png_with_comfy_text())
    workflow_runner.stamp_png(path, "flux_schnell")

    with Image.open(path) as image:
        image.load()
        assert image.text["ImageHearth-Workflow"] == "flux_schnell"
        assert image.text["ImageHearth-Quality-Model"] == "flux-schnell"
        assert image.text["prompt"] == '{"1": {}}'
        assert image.size == (8, 8)


def test_png_of_a_non_quality_workflow_has_no_model(tmp_path):
    path = tmp_path / "image.png"
    path.write_bytes(png_with_comfy_text())
    workflow_runner.stamp_png(path, "sdxl_turbo")

    with Image.open(path) as image:
        image.load()
        assert image.info["ImageHearth-Workflow"] == "sdxl_turbo"
        assert "ImageHearth-Quality-Model" not in image.info


def test_stamp_leaves_a_file_that_is_not_a_png_alone(tmp_path):
    path = tmp_path / "image.png"
    path.write_bytes(b"not a png")
    workflow_runner.stamp_png(path, "flux_dev")
    assert path.read_bytes() == b"not a png"
    chunk = workflow_runner.png_text_chunk("k", "v")
    length, kind = struct.unpack(">I4s", chunk[:8])
    assert (length, kind) == (3, b"tEXt")
    assert struct.unpack(">I", chunk[-4:])[0] == zlib.crc32(chunk[4:-4])


# Agentes


def test_status_lists_the_quality_models(machine, monkeypatch):
    monkeypatch.setattr(agent_setup.sys, "platform", "linux")
    result = agent_setup.status()
    entries = {item["name"]: item for item in result["quality_models"]}
    assert set(entries) == {"flux-dev", "flux-schnell", "sdxl"}
    assert entries["flux-dev"]["recommended"] and not entries["flux-schnell"]["recommended"]
    assert entries["flux-dev"]["commercial_use"] is False and entries["sdxl"]["commercial_use"]
    assert entries["sdxl"]["license"]["url"]
    assert all(item["fits_this_gpu"] for item in entries.values())
    assert result["installed_quality_model"] is None
    assert "quality model" in result["next_step"]


def test_status_flags_what_does_not_fit_and_what_is_installed(machine, monkeypatch):
    monkeypatch.setattr(agent_setup.sys, "platform", "linux")
    setup_command.run(setup_args(profile="quality", quality_model="sdxl"))
    gpu(machine, 8192)
    result = agent_setup.status()
    entries = {item["name"]: item for item in result["quality_models"]}
    assert entries["sdxl"]["installed"] and entries["sdxl"]["recommended"]
    assert not entries["flux-dev"]["fits_this_gpu"] and "8192 MiB" in entries["flux-dev"]["warning"]
    assert result["installed_quality_model"] == {"name": "sdxl", "legacy": False}


@pytest.fixture
def spawned(machine, monkeypatch):
    calls = []

    class Process:
        pid = 4242

    def spawn(profile, existing, quality_model=""):
        calls.append((profile, existing, quality_model))
        return Process()

    for name, value in {
        "SETUP_JOB_LOCK": machine.tmp / "job.lock",
        "SETUP_JOB_FILE": machine.tmp / "job.json",
        "SETUP_JOB_LOG": machine.tmp / "job.log",
    }.items():
        monkeypatch.setattr(config, name, value)

    monkeypatch.setattr(agent_setup, "_spawn", spawn)
    monkeypatch.setattr(agent_setup.processes, "create_time", lambda pid: 1.0)
    monkeypatch.setattr(agent_setup.sys, "platform", "linux")
    return calls


def test_start_passes_the_model_and_returns_the_one_used(spawned):
    result = agent_setup.start("quality", True, "", "flux-schnell")
    assert spawned == [("quality", "", "flux-schnell")]
    assert result["quality_model"] == "flux-schnell" and "warning" not in result


def test_start_without_a_model_uses_the_recommendation(spawned, machine):
    gpu(machine, 16000)
    assert agent_setup.start("quality", True)["quality_model"] == "flux-schnell"


def test_start_returns_the_hardware_warning(spawned, machine):
    gpu(machine, 8192)
    result = agent_setup.start("quality", True, "", "flux-dev")
    assert "8192 MiB" in result["warning"]
    assert spawned  # It is installed anyway: the last word is the user's.


def test_start_refuses_an_unknown_model_or_a_profile_without_one(spawned):
    with pytest.raises(ValueError, match="Unknown quality model"):
        agent_setup.start("quality", True, "", "realvisxl")

    with pytest.raises(ValueError, match="no quality model"):
        agent_setup.start("fast", True, "", "sdxl")

    assert not spawned


def test_start_on_an_installation_says_it_replaces_the_model(spawned, machine):
    setup_command.run(setup_args(profile="quality", quality_model="flux-dev"))
    result = agent_setup.start("quality", True, "", "sdxl")
    assert "replaced" in result["replaces"]


def test_the_spawned_setup_confirms_the_choice_the_user_made():
    args = agent_setup._args("quality", "", "sdxl")
    assert args.quality_model == "sdxl" and args.yes and args.accept_licenses
    assert agent_setup._args("quality", "").quality_model is None


def test_tool_and_instructions_expose_the_model():
    import asyncio

    from imagehearth_mcp.server import INSTRUCTIONS, mcp

    tools = {tool.name: tool for tool in asyncio.run(mcp.list_tools())}
    properties = tools["setup_start"].inputSchema["properties"]
    assert "quality_model" in properties
    assert "quality_model" not in tools["setup_start"].inputSchema["required"]
    assert "quality model" in INSTRUCTIONS and "recommended" in INSTRUCTIONS


def test_main_reads_the_model_from_the_command_line(machine, monkeypatch):
    seen = []
    monkeypatch.setattr(
        "imagehearth_mcp.provisioner.setup.run", lambda args: seen.append(args) or 0
    )
    monkeypatch.setattr(config, "SETUP_JOB_FILE", machine.tmp / "job.json")
    assert agent_setup.main(["quality", "", "flux-schnell"]) == 0
    assert seen[0].quality_model == "flux-schnell" and seen[0].profile == "quality"
    assert Path(config.SETUP_JOB_FILE).exists()


# Estilo fotográfico


def test_auto_style_adds_photo_cues_for_schnell_and_sdxl():
    for workflow in ("flux_schnell", "sdxl_base", "sdxl_quality"):
        prompt, _ = workflow_runner.apply_style(workflow, "a red fox in a meadow", "")
        assert prompt.startswith("a red fox in a meadow, RAW photo")


def test_auto_style_leaves_other_media_and_other_models_alone():
    for text in ("a watercolor of a lighthouse", "anime girl", "a logo for a bakery", "a photo of a cat"):
        assert workflow_runner.apply_style("sdxl_base", text, "") == (text, "")

    for workflow in ("flux_dev", "flux_dev_gguf", "sdxl_turbo"):
        assert workflow_runner.apply_style(workflow, "a red fox", "x") == ("a red fox", "x")


def test_photo_style_forces_cues_and_none_sends_the_prompt_as_written():
    prompt, _ = workflow_runner.apply_style("flux_schnell", "a watercolor fox", "", "photo")
    assert "RAW photo" in prompt
    assert workflow_runner.apply_style("sdxl_base", "a red fox", "", "none") == ("a red fox", "")

    with pytest.raises(ValueError, match="style"):
        workflow_runner.apply_style("sdxl_base", "a fox", "", "cartoon")


def test_only_sdxl_gets_a_negative_prompt_and_keeps_the_users():
    _, negative = workflow_runner.apply_style("sdxl_base", "a fox", "no hats")
    assert negative.startswith("no hats, illustration") and "cartoon" in negative
    assert workflow_runner.apply_style("flux_schnell", "a fox", "") == (
        "a fox, " + workflow_runner.PHOTO_CUES,
        "",
    )


def test_style_reaches_the_workflow_and_is_validated(tiny):
    from imagehearth_mcp.engine import batch, image_router

    install(models_dir(), tiny, "quality", "sdxl")
    request = image_router.plan_request("a fox", quality="high", style="photo")
    assert request.style == "photo"

    with pytest.raises(ValueError, match="style"):
        image_router.plan_request("a fox", quality="high", style="nope")

    _, prepared = batch.validate(["a fox", {"prompt": "a cat", "style": "none"}], quality="high")
    texts = [
        next(n["inputs"]["text"] for n in item.workflow.values() if n["class_type"] == "CLIPTextEncode")
        for item in prepared
    ]
    assert "RAW photo" in texts[0] and texts[1] == "a cat"
    negatives = [
        [n["inputs"]["text"] for n in item.workflow.values() if n["class_type"] == "CLIPTextEncode"][1]
        for item in prepared
    ]
    assert "illustration" in negatives[0] and negatives[1] == ""


def test_create_image_tool_exposes_style():
    import asyncio

    from imagehearth_mcp.server import mcp

    tools = {tool.name: tool for tool in asyncio.run(mcp.list_tools())}
    assert "style" in tools["create_image"].inputSchema["properties"]
    assert "style" not in tools["create_image"].inputSchema.get("required", [])
