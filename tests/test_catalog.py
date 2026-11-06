"""Catálogo dinámico, separación del cargador y macOS simulado."""

import dataclasses
import io
import json
import random
import subprocess
import sys
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from imagehearth_mcp.engine import catalog as engine_catalog
from imagehearth_mcp.engine import config, gpu, kontext
from imagehearth_mcp.engine.image_router import create_image
from imagehearth_mcp.engine.validation import (
    available_workflows,
    resolve_edit_workflow,
    resolve_workflow,
)
from imagehearth_mcp.engine.workflow_runner import run_workflow
from imagehearth_mcp.provisioner import (
    ProvisionError,
    comfyui,
    detect,
    doctor,
    manifest,
)
from imagehearth_mcp.provisioner import models as model_files
from imagehearth_mcp.provisioner import setup as setup_command
from imagehearth_mcp.provisioner.install_manifest import InstallManifest
from imagehearth_mcp.server import list_workflows
from tests.harness import EngineTestCase, swap_models
from tests.test_provisioner import machine, setup_args, torch_ok  # noqa: F401

DATA = Path(__file__).parent / "data"


def tiny_catalog():
    """El manifiesto real con modelos de pocos bytes."""
    real = manifest.load()
    return swap_models(
        real,
        {
            name: dataclasses.replace(model, bytes=len(name))
            for name, model in real.models.items()
        },
    )


def install(folder, tiny, profile, quality_model="flux-dev", vram=24564, forced=None):
    resolved = tiny.resolve(tiny.profiles[profile], quality_model, vram, forced)

    for model in resolved.models:
        path = Path(folder) / model.dest
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(model.name.encode())


@pytest.fixture
def tiny(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "COMFY_DIR", tmp_path / "comfy")
    monkeypatch.setattr(config, "INSTALL_MANIFEST", tmp_path / "install.json")
    monkeypatch.setattr(engine_catalog, "current_system", lambda: "linux")
    values = tiny_catalog()
    monkeypatch.setattr(manifest, "load", lambda: values)
    return values


def models_dir():
    return config.COMFY_DIR / "models"


# Catálogo


def test_empty_folder_offers_nothing(tiny):
    assert available_workflows() == []


@pytest.mark.parametrize(
    ("profile", "expected"),
    [
        ("fast", ["sdxl_turbo"]),
        ("quality", ["flux_dev", "sdxl_turbo"]),
        ("full", ["flux_dev", "sdxl_turbo"]),
    ],
)
def test_each_profile(tiny, profile, expected):
    install(models_dir(), tiny, profile)
    assert available_workflows() == expected
    assert engine_catalog.entries()["flux_kontext_dev_basic"].installed == (profile == "full")


def test_wrong_size_is_not_offered(tiny):
    install(models_dir(), tiny, "quality")
    (models_dir() / tiny.models["flux_dev"].dest).write_bytes(b"x")
    assert available_workflows() == ["sdxl_turbo"]


def test_model_shared_by_flux_and_kontext(tiny):
    install(models_dir(), tiny, "full")
    (models_dir() / tiny.models["flux_kontext"].dest).unlink()
    entries = engine_catalog.entries()
    assert entries["flux_dev"].installed
    assert not entries["flux_kontext_dev_basic"].installed

    (models_dir() / tiny.models["t5xxl"].dest).unlink()
    assert not engine_catalog.entries()["flux_dev"].installed


def test_minimum_profile_of_each_workflow(tiny):
    entries = engine_catalog.entries()
    assert {name: entry.profile for name, entry in entries.items()} == {
        "sdxl_turbo": "fast",
        "flux_dev": "quality",
        "flux_dev_gguf": "quality",
        "flux_schnell": "quality",
        "sdxl_base": "quality",
        "sdxl_quality": "quality",
        "flux_kontext_dev_basic": "full",
        "flux_kontext_dev_gguf": "full",
    }


def test_uses_the_recorded_models_folder(tiny, tmp_path):
    records = InstallManifest(config.INSTALL_MANIFEST)
    records.models_dir = str(tmp_path / "elsewhere")
    records.save()
    install(tmp_path / "elsewhere", tiny, "fast")
    assert available_workflows() == ["sdxl_turbo"]


def test_damaged_record_falls_back_to_comfy_folder(tiny):
    config.INSTALL_MANIFEST.write_text("{broken", encoding="utf-8")
    install(models_dir(), tiny, "fast")
    assert available_workflows() == ["sdxl_turbo"]


def write_extra_paths(text):
    config.COMFY_DIR.mkdir(parents=True, exist_ok=True)
    (config.COMFY_DIR / "extra_model_paths.yaml").write_text(text, encoding="utf-8")


def test_model_in_extra_paths_is_installed(tiny, tmp_path):
    install(models_dir(), tiny, "fast")
    install(models_dir(), tiny, "quality")
    kontext_model = tiny.models["flux_kontext"]
    shared = tmp_path / "shared" / "diffusion_models"
    shared.mkdir(parents=True)
    (shared / Path(kontext_model.dest).name).write_bytes(kontext_model.name.encode())
    assert not engine_catalog.entries()["flux_kontext_dev_basic"].installed

    write_extra_paths(
        f"mine:\n  base_path: {json.dumps(str(tmp_path / 'shared'))}\n"
        "  is_default: true\n  diffusion_models: diffusion_models\n"
    )
    assert engine_catalog.entries()["flux_kontext_dev_basic"].installed
    check = doctor.check_models(
        config, InstallManifest(config.INSTALL_MANIFEST), tiny, False, "linux"
    )
    assert check.details["profiles"]["full"]


def test_extra_paths_accepts_several_lines_legacy_names_and_relative_base(tiny):
    write_extra_paths(
        "mine:\n  base_path: shared\n  unet: |\n    one\n    two\n  clip: three\n"
    )
    base = config.COMFY_DIR / "shared"
    assert model_files.extra_search_paths(config.COMFY_DIR) == {
        "diffusion_models": [base / "one", base / "two"],
        "text_encoders": [base / "three"],
    }


def test_extra_paths_wrong_size_is_not_installed(tiny, tmp_path):
    install(models_dir(), tiny, "quality")
    model = tiny.models["flux_dev"]
    (models_dir() / model.dest).unlink()
    (tmp_path / "flux").mkdir()
    (tmp_path / "flux" / Path(model.dest).name).write_bytes(b"x")
    write_extra_paths(
        f"mine:\n  base_path: {json.dumps(str(tmp_path))}\n  diffusion_models: flux\n"
    )
    assert not engine_catalog.entries()["flux_dev"].installed


@pytest.mark.parametrize("text", ["{broken", "- a list", "mine: text", ""])
def test_damaged_extra_paths_are_ignored(tiny, text):
    install(models_dir(), tiny, "fast")
    write_extra_paths(text)
    assert available_workflows() == ["sdxl_turbo"]


def test_workflow_without_manifest_entry_is_not_offered(tiny, tmp_path, monkeypatch):
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "sdxl_turbo.json").write_text("{}", encoding="utf-8")
    (workflows / "mine.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(config, "WORKFLOWS_DIR", workflows)
    assert set(engine_catalog.entries()) == {"sdxl_turbo"}


def test_catalog_does_not_read_the_models(tiny, monkeypatch):
    install(models_dir(), tiny, "fast")

    def fail(*args, **kwargs):
        raise AssertionError("the catalog must only stat the files")

    monkeypatch.setattr(model_files, "sha256", fail)
    assert available_workflows() == ["sdxl_turbo"]


def test_doctor_and_catalog_agree(tiny):
    install(models_dir(), tiny, "quality")
    records = InstallManifest(config.INSTALL_MANIFEST)
    records.profile = "quality"
    check = doctor.check_models(config, records, tiny, False, "linux")
    entries = engine_catalog.entries()

    assert check.details["profiles"] == {"fast": True, "quality": True, "full": False}
    assert entries["flux_dev"].installed
    assert not entries["flux_kontext_dev_basic"].installed


def test_server_does_not_import_huggingface_hub():
    code = (
        "import sys, imagehearth_mcp.server;"
        "sys.exit('huggingface_hub' in sys.modules)"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


# Variantes por plataforma


def test_linux_picks_the_best_installed_variant_that_fits(tiny):
    install(models_dir(), tiny, "mac-full")
    install(models_dir(), tiny, "full")
    assert engine_catalog.choose("high", 24000) == "flux_dev"
    assert engine_catalog.choose("high", 16000) == "flux_dev_gguf"
    assert engine_catalog.choose("high", None) == "flux_dev"
    assert engine_catalog.choose("edit", 24000) == "flux_kontext_dev_basic"
    assert engine_catalog.choose("edit", 16000) == "flux_kontext_dev_gguf"


def test_linux_uses_fp8_when_it_is_the_only_one_installed(tiny):
    install(models_dir(), tiny, "full")
    assert engine_catalog.choose("high", 16000) == "flux_dev"


def test_editing_is_unavailable_below_12_gb(tiny):
    install(models_dir(), tiny, "full")

    with (
        monkeypatch_gpu(8000),
        pytest.raises(ValueError, match=r"Image editing is not available.*12000 MiB"),
    ):
        resolve_edit_workflow()


def monkeypatch_gpu(total):
    from unittest import mock

    return mock.patch("imagehearth_mcp.engine.gpu.total_mib", return_value=total)


def test_mac_resolves_to_gguf_variants(tiny, monkeypatch):
    monkeypatch.setattr(engine_catalog, "current_system", lambda: "darwin")
    assert engine_catalog.choose("high") == "flux_dev_gguf"
    assert engine_catalog.choose("edit") == "flux_kontext_dev_gguf"
    assert "flux_dev" not in engine_catalog.entries()

    with pytest.raises(ValueError, match="--profile mac-quality"):
        resolve_workflow("", "high")

    install(models_dir(), tiny, "mac-full")
    assert resolve_workflow("", "high") == "flux_dev_gguf"
    assert available_workflows() == ["flux_dev_gguf", "sdxl_turbo"]


# Motor con solo `fast`


class OnlyFast(EngineTestCase):
    def setUp(self):
        super().setUp()
        self.models_present.side_effect = None
        self.installed = {"sdxl_turbo"}
        self.models_present.side_effect = lambda items, folder, extra=None: [
            model_files.ModelState(
                item,
                Path(folder) / item.dest,
                model_files.PRESENT if item.name in self.installed else model_files.MISSING,
            )
            for item in items
        ]

    def assert_untouched(self):
        self.assertEqual(self.comfy.workflows, [])
        self.assertEqual(self.comfy.events, [])
        self.assertEqual(self.ollama.events, [])

    def test_quality_high_names_the_profile(self):
        with self.assertRaisesRegex(ValueError, "setup --profile quality"):
            create_image("gato", quality="high")

        self.assert_untouched()

    def test_edit_names_the_full_profile(self):
        reference = self.tmp / "ref.png"
        reference.write_bytes(b"not read")

        with self.assertRaisesRegex(ValueError, "Image editing .*setup --profile full"):
            create_image("gato", image_paths=[str(reference)])

        self.assert_untouched()

    def test_run_workflow_checks_too(self):
        with self.assertRaisesRegex(ValueError, "setup --profile quality"):
            run_workflow("flux_dev.json", "gato")

        self.assert_untouched()

    def test_never_switches_model_silently(self):
        with self.assertRaises(ValueError):
            create_image("gato", workflow="flux_dev")

        self.assertEqual(self.comfy.workflows, [])

    def test_fast_works(self):
        create_image("gato")
        self.assertEqual(len(self.comfy.workflows), 1)

    def test_list_keeps_its_shape(self):
        self.assertEqual(
            list_workflows(), [{"name": "sdxl_turbo", "file": "sdxl_turbo.json"}]
        )

    def test_more_models_show_up_without_restart(self):
        self.assertEqual(available_workflows(), ["sdxl_turbo"])
        self.installed |= {"flux_dev", "t5xxl", "clip_l", "flux_vae"}
        self.assertEqual(available_workflows(), ["flux_dev", "sdxl_turbo"])


# Separación del cargador


@pytest.mark.parametrize(
    ("name", "references"),
    [
        ("one", ["a/reference_1.png"]),
        ("many", ["a/reference_1.png", "a/reference_2.jpg", "a/reference_3.webp"]),
    ],
)
def test_build_workflow_matches_reference(name, references):
    # Guardado con el código anterior a la separación del cargador.
    expected = json.loads(
        (DATA / f"kontext_{name}_reference.json").read_text(encoding="utf-8")
    )
    random.seed(1234)
    workflow = kontext.build_workflow(
        references, "change the sky", 1024, 768, "imagehearth/golden"
    )
    assert workflow == expected


def test_gguf_variant_links_its_own_loaders():
    workflow = kontext.build_workflow(
        ["a/r.png"], "x", 1024, 1024, "f", workflow_name="flux_kontext_dev_gguf"
    )
    classes = {node["class_type"] for node in workflow.values()}
    assert {"UnetLoaderGGUF", "DualCLIPLoaderGGUF"} <= classes
    assert not {"UNETLoader", "DualCLIPLoader", "ImageStitch"} & classes
    unet = kontext.find_node(workflow, "UnetLoaderGGUF")
    sampler = kontext.find_node(workflow, "KSampler")
    assert workflow[sampler]["inputs"]["model"] == [unet, 0]


def test_find_node_by_role():
    workflow = {
        "a": {"class_type": "CLIPTextEncode", "_meta": {"title": "Negative"}},
        "b": {"class_type": "CLIPTextEncode", "_meta": {"title": "CLIP (Positive Prompt)"}},
    }
    assert kontext.find_node(workflow, "CLIPTextEncode", role="positive") == "b"


def test_find_node_fails_clearly():
    workflow = {"a": {"class_type": "KSampler"}, "b": {"class_type": "KSampler"}}

    with pytest.raises(RuntimeError, match="several KSampler"):
        kontext.find_node(workflow, "KSampler")

    with pytest.raises(RuntimeError, match="VAELoader is missing"):
        kontext.find_node(workflow, "VAELoader")


# Manifiesto de macOS


def test_existing_profiles_do_not_change():
    catalog = manifest.load()
    names = {
        n: [m.name for m in catalog.resolve(p, "flux-dev", 24564).models]
        for n, p in catalog.profiles_for("linux").items()
    }
    assert names == {
        "fast": ["sdxl_turbo"],
        "quality": ["sdxl_turbo", "flux_dev", "t5xxl", "clip_l", "flux_vae"],
        "full": ["sdxl_turbo", "flux_dev", "flux_kontext", "t5xxl", "clip_l", "flux_vae"],
    }
    assert list(catalog.profiles_for("windows")) == list(names)
    assert all(not p.nodes for p in catalog.profiles_for("linux").values())


def test_mac_profiles():
    catalog = manifest.load()
    profiles = catalog.profiles_for("darwin")
    assert list(profiles) == ["mac-fast", "mac-quality", "mac-full"]
    assert set(profiles["mac-fast"].models) < set(profiles["mac-quality"].models)
    assert set(profiles["mac-quality"].models) < set(profiles["mac-full"].models)
    assert profiles["mac-fast"].models[0] is catalog.models["sdxl_turbo"]
    assert not profiles["mac-fast"].nodes
    assert profiles["mac-full"].nodes == (catalog.nodes["comfyui-gguf"],)
    assert catalog.pytorch["metal"].install_bytes < catalog.comfyui.install_bytes
    assert catalog.install_bytes(catalog.pytorch["metal"]) == catalog.pytorch["metal"].install_bytes
    assert catalog.install_bytes(catalog.pytorch["cu130"]) == catalog.comfyui.install_bytes


def test_gguf_workflows_use_the_manifest_files():
    catalog = manifest.load()

    for name in ("flux_dev_gguf", "flux_kontext_dev_gguf"):
        text = (config.WORKFLOWS_DIR / f"{name}.json").read_text(encoding="utf-8")

        for model in catalog.models_for(name):
            assert Path(model.dest).name in text


def test_gguf_node_is_in_the_licenses():
    catalog = manifest.load()
    keys = [entry.key for entry in catalog.licenses_for(catalog.profiles["mac-full"])]
    assert "apache-2" in keys


# ComfyUI-GGUF


def node_archive(destination):
    buffer = io.BytesIO()

    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        data = b"# node"
        info = tarfile.TarInfo("ComfyUI-GGUF-abc/__init__.py")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))

    destination.write_bytes(buffer.getvalue())


@pytest.fixture
def comfy_with_venv(tmp_path):
    comfy = tmp_path / "comfy"
    (comfy / "custom_nodes").mkdir(parents=True)
    python = comfy / "venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    return comfy


def install_gguf(comfy, records, allowed=True, calls=None):
    pin = manifest.load().nodes["comfyui-gguf"]
    calls = [] if calls is None else calls
    return comfyui.install_custom_node(
        pin,
        comfy,
        records,
        allowed,
        run=lambda command, check: calls.append(command),
        fetch=lambda _pin, path: node_archive(path),
        which=lambda _: "/bin/uv",
    )


def test_node_is_installed_recorded_and_its_packages_pinned(comfy_with_venv, tmp_path):
    records = InstallManifest(tmp_path / "install.json")
    calls = []
    assert install_gguf(comfy_with_venv, records, calls=calls)
    destination = comfy_with_venv / "custom_nodes" / "ComfyUI-GGUF"
    assert (destination / "__init__.py").exists()
    assert records.is_owned(destination)
    assert "gguf==0.19.0" in calls[0]
    assert not list((comfy_with_venv / "custom_nodes").glob("*.partial"))


def test_foreign_node_is_never_replaced(comfy_with_venv, tmp_path):
    records = InstallManifest(tmp_path / "install.json")
    destination = comfy_with_venv / "custom_nodes" / "ComfyUI-GGUF"
    destination.mkdir()
    (destination / "mine.py").write_text("x", encoding="utf-8")
    assert install_gguf(comfy_with_venv, records)
    assert (destination / "mine.py").exists()
    assert not records.is_owned(destination)


def test_node_needs_permission_when_attached(comfy_with_venv, tmp_path):
    records = InstallManifest(tmp_path / "install.json")
    assert not install_gguf(comfy_with_venv, records, allowed=False)
    assert not (comfy_with_venv / "custom_nodes" / "ComfyUI-GGUF").exists()


def test_new_pin_replaces_own_node(comfy_with_venv, tmp_path):
    records = InstallManifest(tmp_path / "install.json")
    install_gguf(comfy_with_venv, records)
    destination = comfy_with_venv / "custom_nodes" / "ComfyUI-GGUF"
    (destination / comfyui.NODE_PIN_FILE).write_text("old", encoding="utf-8")
    (destination / "stale.py").write_text("x", encoding="utf-8")
    assert install_gguf(comfy_with_venv, records)
    assert not (destination / "stale.py").exists()
    assert comfyui.custom_node_is_current(manifest.load().nodes["comfyui-gguf"], comfy_with_venv)


# macOS simulado


APPLE = detect.Gpu("apple", "Apple M3 Max", "", 65536)


def mac_detection():
    return detect.Detection(
        "darwin",
        "arm64",
        gpus=[APPLE],
        disk_free_bytes=1000 * 10**9,
        platform=detect.classify("darwin", "arm64", [APPLE]),
    )


@pytest.fixture
def mac(machine, monkeypatch):  # noqa: F811
    machine.detection = mac_detection()
    machine.nodes = []
    monkeypatch.setattr(
        comfyui,
        "install_custom_node",
        lambda pin, directory, records, allowed: machine.nodes.append(pin.name) or True,
    )
    return machine


def test_mac_rejected_without_experimental(mac, capsys):
    with pytest.raises(ProvisionError, match="--experimental"):
        setup_command.run(setup_args(profile="mac-fast"))

    assert mac.downloads == []
    assert mac.managed == []
    assert "Licenses" not in capsys.readouterr().out


def test_mac_full_flow(mac, capsys):
    assert setup_command.run(setup_args(profile="mac-full", experimental=True)) == 0
    assert mac.nodes == ["comfyui-gguf"]
    assert set(mac.downloads) == {
        "sdxl_turbo",
        "flux_dev_gguf",
        "t5xxl_gguf",
        "clip_l",
        "flux_vae",
        "flux_kontext_gguf",
    }
    output = capsys.readouterr().out
    assert "never been run" in output
    records = InstallManifest.load(config.INSTALL_MANIFEST)
    assert records.profile == "mac-full"


def test_mac_fast_needs_no_custom_node(mac):
    setup_command.run(setup_args(profile="mac-fast", experimental=True))
    assert mac.nodes == []
    assert mac.downloads == ["sdxl_turbo"]


def test_mac_rejects_other_platform_profiles(mac):
    with pytest.raises(ProvisionError, match="not for darwin"):
        setup_command.run(setup_args(profile="full", experimental=True))


def test_linux_rejects_mac_profiles(machine):  # noqa: F811
    with pytest.raises(ProvisionError, match="not for linux"):
        setup_command.run(setup_args(profile="mac-full"))

    assert machine.downloads == []


def test_mac_proposes_by_unified_memory():
    catalog = manifest.load()

    def proposal(memory):
        detection = mac_detection()
        detection.gpus = [detect.Gpu("apple", "M", "", memory)]
        return setup_command.propose_profile(detection, catalog)

    assert proposal(16384) == "mac-fast"
    assert proposal(32768) == "mac-full"


def test_intel_mac_is_not_supported():
    result = detect.classify("darwin", "x86_64", [])
    assert not result.supported
    assert "Intel" in result.note


def test_detect_never_calls_nvidia_smi_on_mac(tmp_path):
    commands = []

    def run(command, timeout=10):
        commands.append(command[0])
        return "Apple M3\n"

    result = detect.detect(
        disk_path=tmp_path,
        run=run,
        session=SimpleNamespace(get=lambda *a, **k: (_ for _ in ()).throw(detect.requests.ConnectionError())),
        which=lambda _: None,
        system="darwin",
        machine="arm64",
        home=tmp_path,
        environ={},
        running_dirs=[],
    )
    assert commands == ["sysctl"]
    assert result.primary_gpu.vendor == "apple"
    assert result.primary_gpu.vram_mib == result.ram_mib
    assert (result.platform.index, result.platform.tier) == ("metal", 3)


def test_engine_memory_never_calls_nvidia_smi_on_mac(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(gpu, "_from_comfyui", lambda: None)

    def fail():
        raise AssertionError("nvidia-smi on macOS")

    monkeypatch.setattr(gpu, "_from_nvidia_smi", fail)
    assert gpu.free_mib() is None


def test_doctor_on_mac(mac):
    setup_command.run(setup_args(profile="mac-full", experimental=True))
    comfy = config.COMFY_DIR
    (comfy / "comfy").mkdir(parents=True, exist_ok=True)
    (comfy / "main.py").write_text("", encoding="utf-8")

    checks = {
        check.layer: check
        for check in doctor.collect(
            session=SimpleNamespace(get=lambda *a, **k: (_ for _ in ()).throw(doctor.requests.ConnectionError())),
            run=torch_ok,
            detection=mac_detection(),
        )
    }
    assert checks["gpu"].status == doctor.WARN
    assert "untested" in checks["gpu"].message
    assert checks["custom_nodes"].status == doctor.FAIL
    assert "ComfyUI-GGUF" in checks["custom_nodes"].message
    assert list(checks["models"].details["profiles"]) == ["mac-fast", "mac-quality", "mac-full"]
    json.dumps(doctor.to_json(list(checks.values())))

    (comfy / "custom_nodes" / "ComfyUI-GGUF").mkdir(parents=True)
    records = InstallManifest.load(config.INSTALL_MANIFEST)
    assert doctor.check_custom_nodes(config, records, manifest.load()).status == doctor.OK


def test_doctor_skips_custom_nodes_on_desktop_profiles(machine):  # noqa: F811
    records = InstallManifest(config.INSTALL_MANIFEST)
    records.profile = "full"
    assert doctor.check_custom_nodes(config, records, manifest.load()).status == doctor.SKIP


