import argparse
import dataclasses
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

from imagehearth_mcp import cli
from imagehearth_mcp.engine import comfyui_manager, config
from imagehearth_mcp.platform import paths
from imagehearth_mcp.provisioner import (
    ProvisionError,
    comfyui,
    detect,
    doctor,
    maintenance,
    manifest,
    models,
    preflight,
    settings,
    smoke,
)
from imagehearth_mcp.provisioner import setup as setup_command
from imagehearth_mcp.provisioner.install_manifest import InstallManifest

GB = 1_000_000_000


@pytest.fixture
def catalog():
    return manifest.load()


@pytest.fixture
def records(tmp_path):
    return InstallManifest(tmp_path / "state" / "install.json")


def make_model(name="m", data=b"weights", dest=None):
    return manifest.Model(
        name,
        "org/repo",
        "a" * 40,
        f"split/{name}.safetensors",
        dest or f"checkpoints/{name}.safetensors",
        len(data),
        hashlib.sha256(data).hexdigest(),
        "lic",
        ("wf",),
    )


def fake_download(data=b"weights", calls=None):
    def download(model, local_dir):
        if calls is not None:
            calls.append(model.name)

        path = Path(local_dir) / model.filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    return download


def make_comfy(path):
    (path / "comfy").mkdir(parents=True)
    (path / "custom_nodes").mkdir()
    (path / "models").mkdir()
    (path / "main.py").write_text("", encoding="utf-8")
    return path


class NoServers:
    """Sesión HTTP en la que nada responde."""

    def get(self, url, timeout=None):
        raise requests.ConnectionError(url)


class Response:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self.ok = status_code == 200
        self._body = body or {}

    def json(self):
        return self._body


class Servers:
    def __init__(self, routes):
        self.routes = routes

    def get(self, url, timeout=None):
        if url in self.routes:
            return self.routes[url]

        raise requests.ConnectionError(url)


def nvidia_run(line="NVIDIA GeForce RTX 4090, 580.178.04, 24564"):
    def run(command, timeout=10):
        return line + "\n" if command[0] == "nvidia-smi" else None

    return run


def detection_for(tmp_path, **kwargs):
    defaults = dict(  # noqa: C408
        run=nvidia_run(),
        session=NoServers(),
        which=lambda _: None,
        system="linux",
        machine="x86_64",
        home=tmp_path,
        environ={},
        sysfs=tmp_path / "no-sysfs",
        running_dirs=[],
    )
    return detect.detect(**{**defaults, **kwargs})


# CLI


def test_no_arguments_serves_mcp(monkeypatch):
    served = []

    def run(transport):
        served.append(transport)

    server = SimpleNamespace(mcp=SimpleNamespace(run=run))
    monkeypatch.setitem(sys.modules, "imagehearth_mcp.server", server)
    cli.main([])
    assert served == ["stdio"]


def test_version_loads_neither_server_nor_provisioner():
    code = (
        "import sys\n"
        "from imagehearth_mcp import cli\n"
        "try:\n"
        "    cli.main(['--version'])\n"
        "except SystemExit:\n"
        "    pass\n"
        "loaded = [m for m in sys.modules if m.startswith('imagehearth_mcp.')]\n"
        "assert 'imagehearth_mcp.server' not in loaded, loaded\n"
        "assert not [m for m in loaded if 'provisioner' in m], loaded\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True, capture_output=True)


def test_server_does_not_import_provisioner():
    code = (
        "import sys\n"
        "import imagehearth_mcp.server\n"
        "assert not [m for m in sys.modules if 'provisioner' in m]\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True, capture_output=True)


def test_provision_error_exits_with_message(monkeypatch, capsys):
    def fail(args):
        raise ProvisionError("broken")

    monkeypatch.setattr(maintenance, "update", fail)

    with pytest.raises(SystemExit) as exit_info:
        cli.main(["update"])

    assert exit_info.value.code == 1
    assert "broken" in capsys.readouterr().err


# Detección


def test_detects_nvidia(tmp_path):
    result = detection_for(tmp_path)
    gpu = result.primary_gpu
    assert (gpu.vendor, gpu.driver, gpu.vram_mib) == ("nvidia", "580.178.04", 24564)
    assert result.platform.index == "cu130"
    assert result.platform.tier == 1
    assert not result.driver_missing
    json.dumps(result.to_dict())


def test_detects_missing_driver_from_lspci(tmp_path):
    def run(command, timeout=10):
        if command[0] == "lspci":
            return "01:00.0 VGA compatible controller: NVIDIA Corporation TU104\n"

        return None

    result = detection_for(tmp_path, run=run)
    assert result.driver_missing
    assert result.platform.index == "cu130"


def test_detects_gpu_from_sysfs_without_lspci(tmp_path):
    device = tmp_path / "sysfs" / "0000:01:00.0"
    device.mkdir(parents=True)
    (device / "class").write_text("0x030000\n", encoding="utf-8")
    (device / "vendor").write_text("0x1002\n", encoding="utf-8")
    result = detection_for(tmp_path, run=lambda c, timeout=10: None, sysfs=tmp_path / "sysfs")
    assert result.platform.index == "rocm7.2"


def test_no_gpu_is_cpu(tmp_path):
    result = detection_for(tmp_path, run=lambda c, timeout=10: None)
    assert result.gpus == []
    assert (result.platform.index, result.platform.tier) == ("cpu", 3)


def test_windows_adapter_names(tmp_path):
    def run(command, timeout=10):
        return "Intel(R) Arc(TM) A770 Graphics\n" if command[0] == "powershell" else None

    result = detection_for(tmp_path, run=run, system="windows", machine="AMD64")
    assert [gpu.vendor for gpu in result.gpus] == ["intel"]


@pytest.mark.parametrize(
    ("system", "machine", "gpu", "index", "tier", "supported"),
    [
        ("linux", "x86_64", detect.Gpu("nvidia", "NVIDIA GeForce RTX 3060"), "cu130", 1, True),
        ("windows", "AMD64", detect.Gpu("nvidia", "NVIDIA GeForce GTX 1660"), "cu130", 1, True),
        ("linux", "x86_64", detect.Gpu("nvidia", "NVIDIA GeForce GTX 1080"), "cu126", 3, True),
        ("windows", "AMD64", detect.Gpu("nvidia", "NVIDIA GeForce GT 710"), "cu126", 3, True),
        ("linux", "x86_64", detect.Gpu("amd", "Radeon RX 7900"), "rocm7.2", 3, True),
        ("windows", "AMD64", detect.Gpu("amd", "Radeon RX 7900"), "cpu", 3, False),
        ("linux", "x86_64", detect.Gpu("intel", "Intel Arc A770"), "xpu", 3, True),
        ("linux", "x86_64", detect.Gpu("intel", "Intel UHD Graphics 770"), "cpu", 3, True),
        ("darwin", "arm64", None, "metal", 3, True),
        ("darwin", "x86_64", None, "cpu", 3, False),
        ("linux", "aarch64", detect.Gpu("nvidia", "NVIDIA Jetson"), "cpu", 3, False),
    ],
)
def test_classify_matrix(system, machine, gpu, index, tier, supported):
    result = detect.classify(system, machine, [gpu] if gpu else [])
    assert (result.index, result.tier, result.supported) == (index, tier, supported)


def test_finds_comfy_in_known_paths_and_desktop(tmp_path):
    make_comfy(tmp_path / "AI" / "ComfyUI")
    base = tmp_path / "desktop-data"
    (base / "custom_nodes").mkdir(parents=True)
    appdata = tmp_path / "appdata"
    (appdata / "ComfyUI").mkdir(parents=True)
    (appdata / "ComfyUI" / "config.json").write_text(
        json.dumps({"basePath": str(base)}), encoding="utf-8"
    )
    result = detection_for(tmp_path, environ={"APPDATA": str(appdata)})
    assert sorted(i.kind for i in result.comfy_installs) == ["desktop", "source"]


def test_finds_running_comfy_and_local_servers(tmp_path):
    routes = {
        "http://127.0.0.1:8000/system_stats": Response(
            body={"system": {"comfyui_version": "0.43.0"}}
        ),
        "http://127.0.0.1:11434/api/version": Response(),
    }
    result = detection_for(
        tmp_path,
        session=Servers(routes),
        which=lambda binary: "/bin/lms" if binary == "lms" else None,
    )
    assert [(c.port, c.version) for c in result.comfy_running] == [(8000, "0.43.0")]
    servers = {server.name: server for server in result.servers}
    assert servers["ollama"].running
    assert servers["lmstudio"].binary == "/bin/lms"
    assert not servers["vllm"].running


def test_port_8000_vllm_is_not_comfy(tmp_path):
    routes = {"http://127.0.0.1:8000/system_stats": Response(404)}
    assert detection_for(tmp_path, session=Servers(routes)).comfy_running == []


# Manifiesto


def test_profile_sizes_match_documentation(catalog):
    documented = {"fast": 6.9, "quality": 24.5, "full": 36.5}

    for name, size in documented.items():
        assert catalog.profiles[name].bytes / GB == pytest.approx(size, abs=0.1)


def test_every_workflow_has_its_models(catalog):
    files = config.WORKFLOWS_DIR.glob("*.json")
    declared = {
        Path(model.dest).name: model.workflows for model in catalog.models.values()
    }

    for path in files:
        workflow = json.loads(path.read_text(encoding="utf-8"))
        names = [
            value
            for node in workflow.values()
            if isinstance(node, dict)
            for value in node.get("inputs", {}).values()
            if isinstance(value, str) and value.endswith((".safetensors", ".gguf"))
        ]
        assert names, path

        for name in names:
            assert path.stem in declared[name], (path, name)


def test_profiles_are_cumulative(catalog):
    fast, quality, full = (catalog.profiles[n] for n in ("fast", "quality", "full"))
    assert set(fast.models) < set(quality.models) < set(full.models)
    gguf = {"flux_dev_gguf", "flux_kontext_gguf", "t5xxl_gguf"}
    assert {m.name for m in full.models} == set(catalog.models) - gguf


def test_pytorch_matches_platform_matrix(catalog):
    assert catalog.pytorch["cu130"].python == "3.13"
    assert catalog.pytorch["cu126"].python == "3.12"

    for name, pin in catalog.pytorch.items():
        if name == "metal":
            assert all("+" not in package for package in pin.packages)
            continue

        assert all(f"+{name}" in package for package in pin.packages)


def manifest_values():
    with config.data_path("models.toml").open("rb") as file:
        return tomllib.load(file)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("sha256", "abc"),
        ("sha256", "G" * 64),
        ("revision", "main"),
        ("license", "unknown"),
        ("bytes", 0),
    ],
)
def test_rejects_invalid_model(field, value):
    values = manifest_values()
    values["models"][0][field] = value

    with pytest.raises(ProvisionError):
        manifest.parse(values)


def test_rejects_profile_with_unknown_model():
    values = manifest_values()
    values["profiles"]["fast"]["models"] = ["nope"]

    with pytest.raises(ProvisionError):
        manifest.parse(values)


# Descarga de modelos


def test_download_verifies_and_records_as_owned(tmp_path, records):
    model = make_model()
    models.ensure_models([model], tmp_path / "models", records, fake_download(), print)
    final = tmp_path / "models" / model.dest
    assert final.read_bytes() == b"weights"
    assert records.is_owned(final)
    assert not (tmp_path / "models" / models.STAGING_DIR).exists()


def test_present_file_is_not_downloaded_or_claimed(tmp_path, records):
    model = make_model()
    final = tmp_path / "models" / model.dest
    final.parent.mkdir(parents=True)
    final.write_bytes(b"weights")
    calls = []
    models.ensure_models([model], tmp_path / "models", records, fake_download(calls=calls), print)
    assert calls == []
    assert not records.is_owned(final)
    assert records.entry(final) is not None


def test_owned_corrupt_file_is_downloaded_again(tmp_path, records):
    model = make_model()
    calls = []
    download = fake_download(calls=calls)
    models.ensure_models([model], tmp_path / "models", records, download, print)
    final = tmp_path / "models" / model.dest
    final.write_bytes(b"garbage")
    models.ensure_models([model], tmp_path / "models", records, download, print)
    assert len(calls) == 2
    assert final.read_bytes() == b"weights"
    assert records.is_owned(final)


def test_foreign_corrupt_file_is_never_touched(tmp_path, records):
    model = make_model()
    final = tmp_path / "models" / model.dest
    final.parent.mkdir(parents=True)
    final.write_bytes(b"garbage")

    with pytest.raises(ProvisionError, match="won't be touched"):
        models.ensure_models([model], tmp_path / "models", records, fake_download(), print)

    assert final.read_bytes() == b"garbage"


def test_corrupt_download_is_discarded(tmp_path, records):
    model = make_model()

    with pytest.raises(ProvisionError, match="corrupt"):
        models.ensure_models(
            [model], tmp_path / "models", records, fake_download(b"bad"), print
        )

    assert not (tmp_path / "models" / model.dest).exists()


def test_interrupted_download_keeps_staging_and_resumes(tmp_path, records):
    first, second = make_model("a"), make_model("b")
    seen = []

    def interrupted(model, local_dir):
        seen.append((model.name, Path(local_dir)))
        partial = Path(local_dir) / "partial.incomplete"
        partial.write_bytes(b"half")

        if model.name == "b":
            raise KeyboardInterrupt

        return fake_download()(model, local_dir)

    with pytest.raises(KeyboardInterrupt):
        models.ensure_models([first, second], tmp_path / "m", records, interrupted, print)

    # El parcial sigue donde huggingface_hub lo busca.
    staging = tmp_path / "m" / models.STAGING_DIR
    assert (staging / "partial.incomplete").exists()
    assert records.is_owned(staging)
    assert (tmp_path / "m" / first.dest).exists()

    calls = []
    models.ensure_models([first, second], tmp_path / "m", records, fake_download(calls=calls), print)
    assert calls == ["b"]
    assert not staging.exists()


def test_gated_repo_explains_token():
    from huggingface_hub.errors import GatedRepoError

    error = GatedRepoError.__new__(GatedRepoError)
    translated = models._translate(error, make_model())
    assert "HF_TOKEN" in str(translated)
    assert "org/repo" in str(translated)


def test_unknown_download_error_is_not_hidden():
    assert models._translate(ValueError("x"), make_model()) is None


def fake_http_get(monkeypatch, received=b"", error=None):
    from huggingface_hub import file_download

    captured = {}

    def get(url, file, *, resume_size, headers, expected_size, displayed_filename):
        captured.update(url=url, resume=resume_size, headers=headers)

        if error:
            file.write(received)
            raise error

        file.write(received)

    monkeypatch.setattr(file_download, "http_get", get)
    return captured


def test_hf_download_uses_pinned_revision_and_token(monkeypatch, tmp_path):
    monkeypatch.setenv("HF_TOKEN", "test-token")
    model = make_model(data=b"weights")
    captured = fake_http_get(monkeypatch, b"weights")
    path = models.hf_download(model, tmp_path)
    assert path.read_bytes() == b"weights"
    assert model.revision in captured["url"]
    assert captured["resume"] == 0
    assert captured["headers"]["authorization"] == "Bearer test-token"


def test_hf_download_continues_the_partial_file(monkeypatch, tmp_path):
    model = make_model(data=b"weights")
    interrupted = fake_http_get(monkeypatch, b"wei", KeyboardInterrupt())

    with pytest.raises(KeyboardInterrupt):
        models.hf_download(model, tmp_path)

    assert interrupted["resume"] == 0
    captured = fake_http_get(monkeypatch, b"ghts")
    path = models.hf_download(model, tmp_path)
    assert captured["resume"] == 3
    assert path.read_bytes() == b"weights"


def test_hf_download_complete_partial_needs_no_network(monkeypatch, tmp_path):
    model = make_model(data=b"weights")
    (tmp_path / f"{model.name}.part").write_bytes(b"weights")
    captured = fake_http_get(monkeypatch)
    assert models.hf_download(model, tmp_path).read_bytes() == b"weights"
    assert captured == {}


def test_hf_download_discards_oversized_partial(monkeypatch, tmp_path):
    model = make_model(data=b"weights")
    (tmp_path / f"{model.name}.part").write_bytes(b"too many bytes")
    captured = fake_http_get(monkeypatch, b"weights")
    models.hf_download(model, tmp_path)
    assert captured["resume"] == 0


def test_hf_download_restricted_repo_explains_token(monkeypatch, tmp_path):
    from huggingface_hub.errors import GatedRepoError

    error = GatedRepoError.__new__(GatedRepoError)
    fake_http_get(monkeypatch, error=error)

    with pytest.raises(ProvisionError, match="HF_TOKEN"):
        models.hf_download(make_model(), tmp_path)


# Registro de lo instalado


def test_claim_owned_only_if_absent(tmp_path, records):
    new, existing = tmp_path / "new", tmp_path / "existing"
    existing.write_text("x", encoding="utf-8")
    records.claim("file", new)
    records.claim("file", existing)
    assert records.is_owned(new)
    assert not records.is_owned(existing)


def test_repeating_keeps_ownership(tmp_path, records):
    path = tmp_path / "file"
    records.claim("file", path)
    path.write_text("x", encoding="utf-8")
    records.claim("file", path)
    records.note_preexisting("file", path)
    assert records.is_owned(path)
    assert len(records.entries) == 1


def test_preexisting_never_becomes_owned(tmp_path, records):
    path = tmp_path / "file"
    path.write_text("x", encoding="utf-8")
    records.note_preexisting("file", path)
    path.unlink()
    records.claim("file", path)
    records.claim_verified("file", path)
    assert not records.is_owned(path)


def test_record_survives_reload(tmp_path, records):
    records.mode = "managed"
    records.claim("file", tmp_path / "file")
    loaded = InstallManifest.load(records.path)
    assert loaded.mode == "managed"
    assert loaded.is_owned(tmp_path / "file")
    assert not records.path.with_suffix(".tmp").exists()


def test_damaged_record_is_an_error(records):
    records.path.parent.mkdir(parents=True)
    records.path.write_text("{", encoding="utf-8")

    with pytest.raises(ProvisionError):
        InstallManifest.load(records.path)


# config.toml


def test_settings_keep_user_content_and_restore(tmp_path, records):
    path = tmp_path / "config.toml"
    original = '# mine\ncomfy_port = 9000\noutput_dir = "~/Pictures"\n'
    path.write_text(original, encoding="utf-8")
    settings.apply(path, {"comfy_port": 8188, "comfy_dir": r"C:\Comfy UI"}, records)
    values = tomllib.loads(path.read_text(encoding="utf-8"))
    assert values["comfy_port"] == 8188
    assert values["comfy_dir"] == r"C:\Comfy UI"
    assert "# mine" in path.read_text(encoding="utf-8")

    settings.restore(path, records)
    assert tomllib.loads(path.read_text(encoding="utf-8")) == tomllib.loads(original)


def test_restore_respects_user_changes(tmp_path, records):
    path = tmp_path / "config.toml"
    settings.apply(path, {"comfy_port": 8188}, records)
    path.write_text("comfy_port = 7000\n", encoding="utf-8")
    settings.restore(path, records)
    assert "7000" in path.read_text(encoding="utf-8")


def test_repeating_settings_keeps_first_previous_value(tmp_path, records):
    path = tmp_path / "config.toml"
    path.write_text("comfy_port = 1\n", encoding="utf-8")
    settings.apply(path, {"comfy_port": 2}, records)
    settings.apply(path, {"comfy_port": 3}, records)
    settings.restore(path, records)
    assert tomllib.loads(path.read_text(encoding="utf-8"))["comfy_port"] == 1


# ComfyUI


def make_archive(version="0.0.1", extra=b""):
    buffer = io.BytesIO()

    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for name, data in (
            ("main.py", b"main" + extra),
            ("comfy/__init__.py", b""),
            ("requirements.txt", b"torch\n"),
            ("models/checkpoints/put_checkpoints_here", b""),
            ("custom_nodes/example.py.example", b""),
        ):
            info = tarfile.TarInfo(f"ComfyUI-{version}/{name}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))

    return buffer.getvalue()


def comfy_pin(version="0.0.1"):
    return manifest.ComfyPin(version, "http://x", "0" * 64, "comfyui", 7 * GB)


TORCH = manifest.TorchPin("3.13", "http://torch", ("torch==1+cu130",), 580)


def fetch_archive(data):
    def fetch(pin, destination):
        destination.write_bytes(data)

    return fetch


class FakeUv:
    def __init__(self):
        self.commands = []

    def __call__(self, command, check=False):
        self.commands.append(command)

        if command[1] == "venv":
            python = paths.venv_python(Path(command[-1]))
            python.parent.mkdir(parents=True)
            python.write_text("", encoding="utf-8")


def install(target, records, pin=None, data=None, uv=None):
    comfyui.install_managed(
        pin or comfy_pin(),
        TORCH,
        target,
        records,
        run=uv or FakeUv(),
        fetch=fetch_archive(data or make_archive()),
        which=lambda _: "/bin/uv",
    )


def test_managed_install(tmp_path, records):
    target = tmp_path / "comfyui"
    uv = FakeUv()
    install(target, records, uv=uv)
    assert (target / "main.py").exists()
    assert records.is_owned(target)
    assert records.comfyui_version == "0.0.1"
    assert (target / "custom_nodes" / config.STATUS_NODE / "__init__.py").exists()
    assert not target.with_name("comfyui.partial").exists()

    venv, torch, requirements = uv.commands
    assert venv[1:2] == ["venv"] and "--managed-python" in venv
    assert "--default-index" in torch and "torch==1+cu130" in torch
    assert str(target / "requirements.txt") in requirements


def test_repeating_managed_install_changes_nothing(tmp_path, records):
    target = tmp_path / "comfyui"
    install(target, records)
    entries = list(records.entries)
    (target / "marker").write_text("x", encoding="utf-8")

    def no_fetch(pin, destination):
        raise AssertionError("must not download again")

    uv = FakeUv()
    comfyui.install_managed(
        comfy_pin(), TORCH, target, records, run=uv, fetch=no_fetch, which=lambda _: "/bin/uv"
    )
    assert records.entries == entries
    assert (target / "marker").exists()
    assert not any(command[1] == "venv" for command in uv.commands)


def test_new_version_keeps_models_venv_and_nodes(tmp_path, records):
    target = tmp_path / "comfyui"
    install(target, records)
    weights = target / "models" / "checkpoints" / "mine.safetensors"
    weights.write_text("x", encoding="utf-8")
    custom = target / "custom_nodes" / "user_node.py"
    custom.write_text("x", encoding="utf-8")
    (target / "stale.py").write_text("x", encoding="utf-8")

    install(target, records, pin=comfy_pin("0.0.2"), data=make_archive("0.0.2", b"-new"))
    assert (target / "main.py").read_bytes() == b"main-new"
    assert weights.exists() and custom.exists()
    assert not (target / "stale.py").exists()
    assert paths.venv_python(target / "venv").exists()
    assert records.comfyui_version == "0.0.2"


def test_managed_refuses_foreign_folder(tmp_path, records):
    target = make_comfy(tmp_path / "comfyui")
    (target / "main.py").write_text("mine", encoding="utf-8")

    with pytest.raises(ProvisionError, match="--attach"):
        install(target, records)

    assert (target / "main.py").read_text(encoding="utf-8") == "mine"


def test_missing_uv_explains_how_to_install(tmp_path, records):
    with pytest.raises(ProvisionError, match=r"docs\.astral\.sh"):
        comfyui.install_managed(
            comfy_pin(), TORCH, tmp_path / "c", records, run=FakeUv(), fetch=None, which=lambda _: None
        )


def test_bad_archive_hash_is_rejected(tmp_path, monkeypatch):
    class Stream:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def raise_for_status(self):
            pass

        def iter_content(self, size):
            return [b"tampered"]

    monkeypatch.setattr(comfyui.requests, "get", lambda *a, **k: Stream())
    destination = tmp_path / "a.tar.gz"

    with pytest.raises(ProvisionError, match="SHA-256"):
        comfyui._download_archive(comfy_pin(), destination)

    assert not destination.exists()


def test_node_needs_permission_when_attached(tmp_path, records):
    comfy = make_comfy(tmp_path / "comfy")
    node = comfy / "custom_nodes" / config.STATUS_NODE
    assert comfyui.install_node(comfy, records, allowed=False) is False
    assert not node.exists()

    assert comfyui.install_node(comfy, records, allowed=True) is True
    assert records.is_owned(node)


def test_existing_outdated_node_stays_foreign(tmp_path, records):
    comfy = make_comfy(tmp_path / "comfy")
    node = comfy / "custom_nodes" / config.STATUS_NODE
    node.mkdir()
    (node / "__init__.py").write_text("old", encoding="utf-8")
    assert comfyui.install_node(comfy, records, allowed=False) is False
    assert (node / "__init__.py").read_text(encoding="utf-8") == "old"

    assert comfyui.install_node(comfy, records, allowed=True) is True
    assert comfyui.node_is_current(comfy)
    assert not records.is_owned(node)


def test_extra_model_paths_never_overwrites(tmp_path, records):
    comfy = make_comfy(tmp_path / "comfy")
    models_dir = tmp_path / "shared models"
    assert comfyui.write_extra_model_paths(comfy, models_dir, records) is None
    written = comfy / comfyui.EXTRA_PATHS_FILE
    assert str(models_dir) in written.read_text(encoding="utf-8")
    assert records.is_owned(written)

    written.write_text("mine: {}\n", encoding="utf-8")
    block = comfyui.write_extra_model_paths(comfy, models_dir, records)
    assert "base_path" in block
    assert written.read_text(encoding="utf-8") == "mine: {}\n"


def test_engine_finds_dot_venv(tmp_path):
    python = paths.venv_python(tmp_path / ".venv")
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    assert paths.find_venv_python(tmp_path) == python


# Comprobaciones previas


def test_disk_insufficient(tmp_path, monkeypatch):
    monkeypatch.setattr(
        preflight.shutil, "disk_usage", lambda path: SimpleNamespace(free=2 * GB)
    )
    issues = preflight.check_disk({tmp_path / "models": 7 * GB})
    assert [issue.code for issue in issues] == ["disk_space"]
    assert "--profile" in issues[0].message


def test_disk_sums_folders_on_same_device(tmp_path, monkeypatch):
    monkeypatch.setattr(
        preflight.shutil, "disk_usage", lambda path: SimpleNamespace(free=10 * GB)
    )
    assert preflight.check_disk({tmp_path / "a": 8 * GB}) == []
    assert preflight.check_disk({tmp_path / "a": 8 * GB, tmp_path / "b": 8 * GB})


def test_nothing_to_download_needs_no_space(tmp_path, monkeypatch):
    monkeypatch.setattr(
        preflight.shutil, "disk_usage", lambda path: SimpleNamespace(free=0)
    )
    assert preflight.check_disk({tmp_path: 0}) == []


def fake_detection(gpus=(), index="cu130", tier=1, supported=True, note="", driver_missing=False):
    return detect.Detection(
        "linux",
        "x86_64",
        gpus=list(gpus),
        driver_missing=driver_missing,
        platform=detect.TorchPlatform(index, tier, supported, note),
    )


def codes(issues, level=None):
    return [i.code for i in issues if level is None or i.level == level]


def test_driver_missing_blocks_managed(catalog):
    detection = fake_detection(driver_missing=True)
    fast = catalog.profiles["fast"]
    issues = preflight.check_gpu(detection, fast, TORCH, "managed")
    assert codes(issues, preflight.ERROR) == ["driver_missing"]
    assert "nvidia.com/drivers" in issues[0].message
    assert codes(preflight.check_gpu(detection, fast, TORCH, "attached"), preflight.ERROR) == []


def test_unsupported_gpu_blocks_managed_only(catalog):
    detection = fake_detection(index="metal", tier=2, supported=False, note="macOS.")
    fast = catalog.profiles["fast"]
    assert "gpu_unsupported" in codes(preflight.check_gpu(detection, fast, None, "managed"))
    assert codes(preflight.check_gpu(detection, fast, None, "attached"), preflight.ERROR) == []


def test_cpu_only_allows_fast(catalog):
    detection = fake_detection(index="cpu", tier=3, note="CPU.")
    assert codes(preflight.check_gpu(detection, catalog.profiles["fast"], None, "managed"), preflight.ERROR) == []
    assert codes(preflight.check_gpu(detection, catalog.profiles["full"], None, "managed"), preflight.ERROR) == ["gpu_unsupported"]


def test_low_vram_and_old_driver_warn(catalog):
    gpu = detect.Gpu("nvidia", "RTX 3060", "550.1", 12000)
    issues = preflight.check_gpu(fake_detection([gpu]), catalog.profiles["full"], TORCH, "managed")
    assert codes(issues, preflight.WARNING) == ["low_vram", "old_driver"]
    assert codes(issues, preflight.ERROR) == []


def test_busy_port(monkeypatch):
    monkeypatch.setattr(preflight, "port_is_open", lambda port: True)
    monkeypatch.setattr(preflight, "_responds_like_comfy", lambda port: True)
    assert codes(preflight.check_port(8188, "managed")) == ["port_busy"]
    assert "--port" in preflight.check_port(8188, "managed")[0].message
    assert preflight.check_port(8188, "managed", own_instance=True) == []
    assert preflight.check_port(8188, "attached") == []

    monkeypatch.setattr(preflight, "_responds_like_comfy", lambda port: False)
    assert codes(preflight.check_port(8188, "attached")) == ["port_busy"]


def test_uv_check():
    assert codes(preflight.check_uv(lambda _: None)) == ["uv_missing"]
    assert preflight.check_uv(lambda _: "/bin/uv") == []


# setup


def setup_args(**kwargs):
    defaults = dict(  # noqa: C408
        profile="fast",
        accept_licenses=True,
        non_interactive=True,
        managed=False,
        attach=None,
        install_node=False,
        models_dir=None,
        port=None,
        skip_smoke_test=True,
        experimental=False,
    )
    return argparse.Namespace(**{**defaults, **kwargs})


@pytest.fixture
def machine(tmp_path, monkeypatch):
    """Máquina simulada: todo cae en tmp_path y nada toca la red."""
    data = tmp_path / "data"
    monkeypatch.setattr(config, "DATA_DIR", data)
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config" / "config.toml")
    monkeypatch.setattr(config, "COMFY_DIR", data / "comfyui")
    monkeypatch.setattr(config, "COMFY_API", "http://127.0.0.1:1")
    monkeypatch.setattr(config, "COMFY_PORT", 8188)
    monkeypatch.setattr(config, "INSTALL_MANIFEST", data / "install.json")
    monkeypatch.setattr(config, "SETUP_LOCK", data / "setup.lock")
    monkeypatch.setattr(config, "PID_FILE", data / "state" / "comfyui.pid")

    state = SimpleNamespace(
        tmp=tmp_path,
        data=data,
        downloads=[],
        managed=[],
        detection=detect.Detection(
            "linux",
            "x86_64",
            gpus=[detect.Gpu("nvidia", "RTX 4090", "580.1", 24564)],
            disk_free_bytes=1000 * GB,
            platform=detect.TorchPlatform("cu130", 1, True),
        ),
    )
    monkeypatch.setattr(setup_command.detect, "detect", lambda **kw: state.detection)
    monkeypatch.setattr(preflight, "port_is_open", lambda port: False)
    monkeypatch.setattr(preflight, "check_uv", list)
    monkeypatch.setattr(comfyui_manager, "managed_pid", lambda: None)

    real_managed = comfyui.install_managed

    def fake_managed(pin, torch, target, records, **kwargs):
        state.managed.append(target)
        real_managed(
            pin,
            torch,
            target,
            records,
            run=FakeUv(),
            fetch=fetch_archive(make_archive(pin.version)),
            which=lambda _: "/bin/uv",
        )

    monkeypatch.setattr(comfyui, "install_managed", fake_managed)

    small = {
        name: make_model(name, name.encode(), dest=model.dest)
        for name, model in manifest.load().models.items()
    }
    small = {
        name: manifest.Model(**{**model.__dict__, "license": "apache-2"})
        for name, model in small.items()
    }
    catalog = manifest.load()
    fake_catalog = manifest.Manifest(
        catalog.comfyui,
        catalog.pytorch,
        catalog.licenses,
        small,
        {
            name: dataclasses.replace(
                profile, models=tuple(small[m.name] for m in profile.models)
            )
            for name, profile in catalog.profiles.items()
        },
        catalog.nodes,
    )
    monkeypatch.setattr(manifest, "load", lambda: fake_catalog)

    real_ensure = models.ensure_models

    def download(model, local_dir):
        state.downloads.append(model.name)
        return fake_download(model.name.encode())(model, local_dir)

    monkeypatch.setattr(
        models,
        "ensure_models",
        lambda m, d, r: real_ensure(m, d, r, download, lambda text: None),
    )
    return state


def test_non_interactive_without_licenses_downloads_nothing(machine, capsys):
    with pytest.raises(ProvisionError, match="--accept-licenses"):
        setup_command.run(setup_args(accept_licenses=False))

    assert machine.downloads == []
    assert machine.managed == []
    output = capsys.readouterr().out
    assert "Licenses you accept" in output
    assert "GPL-3.0" in output
    assert not config.INSTALL_MANIFEST.exists()


def test_summary_lists_licenses_and_links(capsys, tmp_path):
    catalog = manifest.load()
    full = catalog.profiles["full"]
    setup_command.show_summary(catalog, full, "managed", tmp_path, tmp_path, full.bytes)
    output = capsys.readouterr().out
    assert "36.5 GB" in output

    for entry in catalog.licenses.values():
        assert entry.name in output
        assert entry.url in output


def test_interactive_refusal_downloads_nothing(machine, monkeypatch):
    monkeypatch.setattr(setup_command, "is_interactive", lambda args: True)
    monkeypatch.setattr("builtins.input", lambda prompt: "n")

    with pytest.raises(ProvisionError, match="not accepted"):
        setup_command.run(setup_args(accept_licenses=False, non_interactive=False))

    assert machine.downloads == []


def test_non_interactive_needs_profile(machine):
    with pytest.raises(ProvisionError, match="--profile"):
        setup_command.run(setup_args(profile=None))

    assert machine.downloads == []


def test_setup_fast_only_downloads_fast(machine):
    assert setup_command.run(setup_args()) == 0
    assert machine.downloads == ["sdxl_turbo"]
    assert machine.managed == [machine.data / "comfyui"]
    records = InstallManifest.load(config.INSTALL_MANIFEST)
    assert (records.mode, records.profile) == ("managed", "fast")


def test_widening_profile_reuses_what_exists(machine):
    setup_command.run(setup_args())
    machine.downloads.clear()
    setup_command.run(setup_args(profile="full"))
    assert "sdxl_turbo" not in machine.downloads
    assert "flux_kontext" in machine.downloads
    assert InstallManifest.load(config.INSTALL_MANIFEST).profile == "full"

    machine.downloads.clear()
    setup_command.run(setup_args(profile="fast"))
    assert machine.downloads == []
    assert InstallManifest.load(config.INSTALL_MANIFEST).profile == "full"


def test_insufficient_disk_fails_before_downloading(machine, monkeypatch):
    monkeypatch.setattr(
        preflight.shutil, "disk_usage", lambda path: SimpleNamespace(free=1000)
    )

    with pytest.raises(ProvisionError, match="disk space"):
        setup_command.run(setup_args())

    assert machine.downloads == []
    assert machine.managed == []


def test_existing_comfy_needs_a_decision(machine):
    comfy = make_comfy(machine.tmp / "theirs")
    machine.detection.comfy_installs = [
        detect.ComfyInstall(str(comfy), "source", True)
    ]

    with pytest.raises(ProvisionError, match="--attach"):
        setup_command.run(setup_args())

    assert machine.downloads == []


def test_attach_uses_existing_models_and_needs_node_permission(machine):
    comfy = make_comfy(machine.tmp / "theirs")
    existing = comfy / "models" / "checkpoints" / "sd_xl_turbo_1.0_fp16.safetensors"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"sdxl_turbo")

    assert setup_command.run(setup_args(attach=str(comfy))) == 0
    assert machine.downloads == []
    assert machine.managed == []
    assert not (comfy / "custom_nodes" / config.STATUS_NODE).exists()
    values = tomllib.loads(config.CONFIG_FILE.read_text(encoding="utf-8"))
    assert values["comfy_dir"] == str(comfy.resolve())
    assert values["comfy_port"] == 8188

    setup_command.run(setup_args(attach=str(comfy), install_node=True))
    assert (comfy / "custom_nodes" / config.STATUS_NODE / "__init__.py").exists()


def test_attach_rejects_other_folders(machine, tmp_path):
    with pytest.raises(ProvisionError, match=r"main\.py"):
        setup_command.run(setup_args(attach=str(tmp_path)))


def test_models_dir_is_shared_with_yaml(machine):
    comfy = make_comfy(machine.tmp / "theirs")
    shared = machine.tmp / "shared"
    setup_command.run(setup_args(attach=str(comfy), models_dir=str(shared)))
    assert (shared / "checkpoints" / "sd_xl_turbo_1.0_fp16.safetensors").exists()
    assert str(shared.resolve()) in (comfy / "extra_model_paths.yaml").read_text(
        encoding="utf-8"
    )


def test_smoke_runs_at_the_end(machine, monkeypatch, capsys):
    monkeypatch.setattr(smoke, "run_smoke", lambda: Path("image.png"))
    setup_command.run(setup_args(skip_smoke_test=False))
    assert "image.png" in capsys.readouterr().out


def test_propose_profile(catalog):
    def proposal(vram, disk=1000 * GB):
        detection = detect.Detection(
            "linux",
            "x86_64",
            gpus=[detect.Gpu("nvidia", "x", "1", vram)],
            disk_free_bytes=disk,
        )
        return setup_command.propose_profile(detection, catalog)

    assert proposal(24000) == "full"
    assert proposal(8000) == "fast"
    assert proposal(2000) == "fast"
    assert proposal(24000, disk=10 * GB) == "fast"


# Prueba de humo


def completed(stdout="", stderr="", returncode=0):
    return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)


def test_smoke_validates_the_image(tmp_path):
    from PIL import Image

    path = tmp_path / "ok.png"
    Image.new("RGB", (8, 8)).save(path)
    result = smoke.run_smoke(run=lambda *a, **k: completed(f"{path}\nWARNING: x\n"))
    assert result == path


def test_smoke_rejects_invalid_image(tmp_path):
    path = tmp_path / "bad.png"
    path.write_text("nope", encoding="utf-8")

    with pytest.raises(ProvisionError, match="not valid"):
        smoke.run_smoke(run=lambda *a, **k: completed(str(path)))


def test_smoke_missing_output_is_an_error():
    with pytest.raises(ProvisionError, match="not valid"):
        smoke.run_smoke(run=lambda *a, **k: completed(""))


@pytest.mark.parametrize(
    ("message", "layer"),
    [
        ("ComfyUI not found in /x.", "ComfyUI"),
        ("ComfyUI exited at startup (code 1).", "ComfyUI environment"),
        ("Value not in list: ckpt_name: 'x.safetensors'", "models"),
        ("CUDA out of memory", "GPU"),
        ("Something else", "engine"),
    ],
)
def test_smoke_names_the_layer(message, layer):
    with pytest.raises(ProvisionError) as error:
        smoke.run_smoke(run=lambda *a, **k: completed(stderr=message, returncode=1))

    assert f"in the {layer} layer" in str(error.value)
    assert "doctor" in str(error.value)


# doctor


def torch_ok(*args, **kwargs):
    return completed("2.14.1+cu130 True\n")


def healthy_install(machine, catalog):
    comfy = make_comfy(config.COMFY_DIR)
    python = paths.venv_python(comfy / "venv")
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    records = InstallManifest(config.INSTALL_MANIFEST)
    comfyui.install_node(comfy, records)
    records.profile = "fast"
    records.mode = "managed"
    records.save()

    for model in catalog.profiles["fast"].models:
        path = comfy / "models" / model.dest
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(model.name.encode())

    return comfy


def collect_checks(**kwargs):
    checks = doctor.collect(
        session=kwargs.pop("session", NoServers()),
        run=kwargs.pop("run", torch_ok),
        detection=kwargs.pop(
            "detection",
            detect.Detection(
                "linux",
                "x86_64",
                gpus=[detect.Gpu("nvidia", "RTX 4090", "580.1", 24564)],
                platform=detect.TorchPlatform("cu130", 1, True),
            ),
        ),
        **kwargs,
    )
    return {check.layer: check for check in checks}


def test_doctor_healthy(machine):
    healthy_install(machine, manifest.load())
    checks = collect_checks()
    assert list(checks) == list(doctor.LAYERS)
    failing = {k: v.message for k, v in checks.items() if v.status == doctor.FAIL}
    assert failing == {}


def test_doctor_json_format_is_stable(machine):
    healthy_install(machine, manifest.load())
    checks = doctor.collect(
        session=NoServers(),
        run=torch_ok,
        detection=fake_detection([detect.Gpu("nvidia", "x", "1", 1)]),
    )
    result = doctor.to_json(checks)
    assert set(result) == {"schema", "ok", "checks"}
    assert result["schema"] == 1
    assert [c["layer"] for c in result["checks"]] == list(doctor.LAYERS)

    for check in result["checks"]:
        assert set(check) == {"layer", "status", "message", "fix", "details"}
        assert check["status"] in ("ok", "warn", "fail", "skip")

    json.dumps(result)


def test_doctor_missing_comfy_skips_dependents(machine):
    checks = collect_checks()
    assert checks["comfyui"].status == doctor.FAIL
    assert "setup" in checks["comfyui"].fix
    assert checks["environment"].status == doctor.SKIP
    assert not doctor.to_json(list(checks.values()))["ok"]


def test_doctor_broken_torch(machine):
    healthy_install(machine, manifest.load())
    checks = collect_checks(run=lambda *a, **k: completed(returncode=1))
    assert checks["environment"].status == doctor.FAIL
    assert checks["environment"].fix


def test_doctor_missing_venv(machine):
    comfy = healthy_install(machine, manifest.load())
    paths.venv_python(comfy / "venv").unlink()
    assert collect_checks()["environment"].status == doctor.FAIL


def test_doctor_old_node(machine):
    comfy = healthy_install(machine, manifest.load())
    init = comfy / "custom_nodes" / config.STATUS_NODE / "__init__.py"
    init.write_text("VERSION = 0\n", encoding="utf-8")
    assert collect_checks()["node"].status == doctor.FAIL


def test_doctor_missing_node(machine):
    comfy = healthy_install(machine, manifest.load())
    (comfy / "custom_nodes" / config.STATUS_NODE / "__init__.py").unlink()
    assert "--install-node" in collect_checks()["node"].fix


def test_doctor_node_not_loaded_warns(machine):
    healthy_install(machine, manifest.load())
    session = Servers({f"{config.COMFY_API}{config.STATUS_ROUTE}": Response(404)})
    assert collect_checks(session=session)["node"].status == doctor.WARN


def test_doctor_models_by_size_and_by_hash(machine):
    catalog = manifest.load()
    comfy = healthy_install(machine, catalog)
    path = comfy / "models" / catalog.models["sdxl_turbo"].dest
    path.write_bytes(b"x" * path.stat().st_size)

    assert collect_checks()["models"].status == doctor.OK
    check = collect_checks(verify_hashes=True)["models"]
    assert check.status == doctor.FAIL
    assert "sdxl_turbo" in check.details["problems"]
    assert "--profile fast" in check.fix

    path.unlink()
    assert collect_checks()["models"].status == doctor.FAIL


def test_doctor_gpu_and_port(machine, monkeypatch):
    healthy_install(machine, manifest.load())
    assert collect_checks(detection=fake_detection(driver_missing=True))["gpu"].status == doctor.FAIL
    monkeypatch.setattr(preflight, "port_is_open", lambda port: True)
    check = collect_checks()["port"]
    assert check.status == doctor.FAIL
    assert "comfy_port" in check.fix


def test_doctor_ollama_is_optional(machine, monkeypatch):
    healthy_install(machine, manifest.load())
    monkeypatch.setattr(config, "OLLAMA_MODE", "auto")
    assert collect_checks()["ollama"].status == doctor.SKIP
    monkeypatch.setattr(config, "OLLAMA_MODE", "off")
    assert collect_checks()["ollama"].status == doctor.SKIP


def test_doctor_exit_code(machine, monkeypatch, capsys):
    monkeypatch.setattr(
        doctor,
        "collect",
        lambda verify: [doctor.Check("comfyui", doctor.FAIL, "broken", "do this")],
    )
    args = argparse.Namespace(json=False, verify_hashes=False)
    assert doctor.run(args) == 1
    output = capsys.readouterr().out
    assert "broken" in output and "do this" in output

    monkeypatch.setattr(
        doctor, "collect", lambda verify: [doctor.Check("comfyui", doctor.OK, "fine")]
    )
    args.json = True
    assert doctor.run(args) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_invalid_config_is_reported_by_doctor(tmp_path):
    toml = tmp_path / "config.toml"
    toml.write_text("comfy_port = 'nope'\n", encoding="utf-8")
    env = {**os.environ, "IMAGEHEARTH_CONFIG_FILE": str(toml)}
    result = subprocess.run(
        [sys.executable, "-c", "from imagehearth_mcp.cli import main; main(['doctor', '--json'])"],
        capture_output=True,
        encoding="utf-8",
        env=env,
        check=False,
    )
    assert result.returncode == 1, result.stderr
    checks = {c["layer"]: c for c in json.loads(result.stdout)["checks"]}
    assert checks["package"]["status"] == "ok"
    assert checks["config"]["status"] == "fail"
    assert "comfy_port" in checks["config"]["message"]


# update y uninstall


def uninstall_args(**kwargs):
    return argparse.Namespace(**{"yes": True, "remove_models": False, "keep_models": False, **kwargs})


def update_args(**kwargs):
    return argparse.Namespace(**{"accept_licenses": True, "non_interactive": True, **kwargs})


def test_update_without_install_is_an_error(machine):
    with pytest.raises(ProvisionError, match="setup"):
        maintenance.update(update_args())


def test_update_applies_version_and_missing_models(machine, monkeypatch):
    setup_command.run(setup_args())
    comfy = machine.data / "comfyui"
    (comfy / "models" / "checkpoints" / "sd_xl_turbo_1.0_fp16.safetensors").unlink()
    records = InstallManifest.load(config.INSTALL_MANIFEST)
    records.comfyui_version = "0.0.0"
    records.save()
    (comfy / "stale.py").write_text("x", encoding="utf-8")

    machine.downloads.clear()
    assert maintenance.update(update_args()) == 0
    assert machine.downloads == ["sdxl_turbo"]
    assert not (comfy / "stale.py").exists()
    assert InstallManifest.load(config.INSTALL_MANIFEST).comfyui_version == manifest.load().comfyui.version


def test_update_needs_consent_to_download(machine):
    setup_command.run(setup_args())
    (machine.data / "comfyui" / "models" / "checkpoints" / "sd_xl_turbo_1.0_fp16.safetensors").unlink()
    machine.downloads.clear()

    with pytest.raises(ProvisionError, match="--accept-licenses"):
        maintenance.update(update_args(accept_licenses=False))

    assert machine.downloads == []


def test_update_leaves_attached_comfy_alone(machine):
    comfy = make_comfy(machine.tmp / "theirs")
    (comfy / "main.py").write_text("theirs", encoding="utf-8")
    setup_command.run(setup_args(attach=str(comfy)))
    assert maintenance.update(update_args()) == 0
    assert machine.managed == []
    assert (comfy / "main.py").read_text(encoding="utf-8") == "theirs"
    assert not (comfy / "custom_nodes" / config.STATUS_NODE).exists()


def test_uninstall_without_record_removes_nothing(machine, capsys):
    comfy = make_comfy(config.COMFY_DIR)
    assert maintenance.uninstall(uninstall_args()) == 0
    assert (comfy / "main.py").exists()
    assert "nothing was removed" in capsys.readouterr().out


def test_uninstall_managed_keeps_models_without_confirmation(machine):
    setup_command.run(setup_args())
    comfy = machine.data / "comfyui"
    weights = comfy / "models" / "checkpoints" / "sd_xl_turbo_1.0_fp16.safetensors"
    assert maintenance.uninstall(uninstall_args()) == 0
    assert weights.exists()
    assert not (comfy / "main.py").exists()
    assert not (comfy / "venv").exists()
    assert InstallManifest.load(config.INSTALL_MANIFEST).is_owned(weights)

    # Reinstalar sobre los modelos conservados funciona y no los descarga.
    machine.downloads.clear()
    assert setup_command.run(setup_args(managed=True)) == 0
    assert machine.downloads == []
    assert setup_command.run(setup_args()) == 0


def test_uninstall_managed_with_models_removes_everything_owned(machine):
    setup_command.run(setup_args())
    assert maintenance.uninstall(uninstall_args(remove_models=True)) == 0
    assert not (machine.data / "comfyui").exists()
    assert not config.INSTALL_MANIFEST.exists()


def test_uninstall_keeps_user_file_in_models_folder(machine):
    setup_command.run(setup_args())
    mine = machine.data / "comfyui" / "models" / "checkpoints" / "mine.safetensors"
    mine.write_text("x", encoding="utf-8")
    maintenance.uninstall(uninstall_args(remove_models=True))
    assert mine.exists()


def test_uninstall_leaves_preexisting_comfy_and_models_intact(machine):
    comfy = make_comfy(machine.tmp / "theirs")
    (comfy / "main.py").write_text("theirs", encoding="utf-8")
    theirs = comfy / "models" / "checkpoints" / "sd_xl_turbo_1.0_fp16.safetensors"
    theirs.parent.mkdir(parents=True)
    theirs.write_bytes(b"sdxl_turbo")
    config.CONFIG_FILE.parent.mkdir(parents=True)
    config.CONFIG_FILE.write_text("# mine\ncomfy_port = 9999\n", encoding="utf-8")

    setup_command.run(setup_args(attach=str(comfy), install_node=True, port=9999))
    node = comfy / "custom_nodes" / config.STATUS_NODE
    assert node.exists()

    assert maintenance.uninstall(uninstall_args(remove_models=True)) == 0
    assert (comfy / "main.py").read_text(encoding="utf-8") == "theirs"
    assert theirs.read_bytes() == b"sdxl_turbo"
    assert not node.exists()
    values = tomllib.loads(config.CONFIG_FILE.read_text(encoding="utf-8"))
    assert "comfy_dir" not in values
    assert values["comfy_port"] == 9999
    assert "# mine" in config.CONFIG_FILE.read_text(encoding="utf-8")


def test_uninstall_keeps_preexisting_node(machine):
    comfy = make_comfy(machine.tmp / "theirs")
    node = comfy / "custom_nodes" / config.STATUS_NODE
    node.mkdir()
    (node / "__init__.py").write_bytes(
        config.data_path(config.STATUS_NODE, "__init__.py").read_bytes()
    )
    setup_command.run(setup_args(attach=str(comfy)))
    maintenance.uninstall(uninstall_args(remove_models=True))
    assert node.exists()


def test_uninstall_removes_config_it_created(machine):
    comfy = make_comfy(machine.tmp / "theirs")
    setup_command.run(setup_args(attach=str(comfy)))
    assert config.CONFIG_FILE.exists()
    maintenance.uninstall(uninstall_args(remove_models=True))
    assert not config.CONFIG_FILE.exists()


def test_uninstall_refuses_protected_paths(machine, monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    records = InstallManifest(config.INSTALL_MANIFEST)
    records.entries.append({"kind": "staging", "path": str(tmp_path), "owned": True})
    records.save()
    keep = tmp_path / "keep"
    keep.write_text("x", encoding="utf-8")
    assert maintenance.uninstall(uninstall_args()) == 1
    assert keep.exists()


def test_uninstall_reports_locked_files_and_can_retry(machine, monkeypatch, capsys):
    setup_command.run(setup_args())
    real = maintenance._remove_comfy_dir

    def locked(path):
        raise PermissionError("in use")

    monkeypatch.setattr(maintenance, "_remove_comfy_dir", locked)
    assert maintenance.uninstall(uninstall_args()) == 1
    assert "in use" in capsys.readouterr().out
    assert config.INSTALL_MANIFEST.exists()

    monkeypatch.setattr(maintenance, "_remove_comfy_dir", real)
    assert maintenance.uninstall(uninstall_args()) == 0
    assert not (machine.data / "comfyui" / "main.py").exists()


def test_uninstall_stops_only_its_own_comfy(machine, monkeypatch):
    setup_command.run(setup_args())
    stopped = []
    monkeypatch.setattr(comfyui_manager, "managed_pid", lambda: 4321)
    monkeypatch.setattr(
        maintenance.processes, "terminate", lambda pid, timeout: stopped.append(pid) or True
    )
    maintenance.uninstall(uninstall_args())
    assert stopped == [4321]


def test_non_interactive_uninstall_needs_yes(machine):
    setup_command.run(setup_args())

    with pytest.raises(ProvisionError, match="--yes"):
        maintenance.uninstall(uninstall_args(yes=False))

    assert (machine.data / "comfyui" / "main.py").exists()
