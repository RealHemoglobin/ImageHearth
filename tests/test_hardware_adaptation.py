"""Fase 7: PATH en doctor y llama-server de un solo modelo que se para y vuelve."""

import shutil
import socket
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from unittest import mock

import psutil
import pytest
import requests

from imagehearth_mcp.engine import config, memory_servers, orchestrator, state
from imagehearth_mcp.engine.image_router import create_image
from imagehearth_mcp.platform import processes
from imagehearth_mcp.provisioner import doctor
from tests.harness import EngineTestCase

ROOT = Path(__file__).resolve().parent.parent

FAKE_LLAMA = textwrap.dedent(
    """
    import json, sys
    from http.server import BaseHTTPRequestHandler, HTTPServer

    port, model = int(sys.argv[1]), sys.argv[2]

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.path != "/props":
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            body = json.dumps(
                {"default_generation_settings": {}, "model_path": model}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
    """
)


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_installers_update_the_shell_without_root_or_licenses():
    for name in ("install.sh", "install.ps1"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "uv tool update-shell" in text
        assert "sudo" not in text.replace("never uses root", "")
        assert "--accept-licenses" not in text

    # Windows has no `sh` unless Git Bash is on the PATH; the syntax check is for POSIX hosts.
    sh = shutil.which("sh")
    if sh:
        subprocess.run([sh, "-n", str(ROOT / "install.sh")], check=True)


def test_doctor_path_ok_when_the_command_is_found():
    check = doctor.check_path(which=lambda name: "/home/u/.local/bin/imagehearth-mcp")
    assert check.status == doctor.OK


def test_doctor_path_gives_the_exact_command_per_shell():
    def run(*args, **kwargs):
        return subprocess.CompletedProcess(args, 0, stdout="/home/u/.local/bin\n")

    with mock.patch.dict("os.environ", {"SHELL": "/usr/bin/fish"}):
        check = doctor.check_path(run=run, which=lambda name: None, system="linux")

    assert check.status == doctor.WARN
    assert 'fish_add_path "/home/u/.local/bin"' in check.fix
    assert check.details["bin_dir"] == "/home/u/.local/bin"
    assert "~/.zshenv" in doctor.path_fix_command("/b", "linux", "/bin/zsh")
    assert "~/.profile" in doctor.path_fix_command("/b", "linux", "/bin/bash")
    assert "SetEnvironmentVariable" in doctor.path_fix_command("C:\\b", "win32")


def test_doctor_path_without_uv_still_helps():
    def run(*args, **kwargs):
        raise FileNotFoundError

    check = doctor.check_path(run=run, which=lambda name: None)
    assert check.status == doctor.WARN
    assert "uv tool update-shell" in check.fix


def test_launch_info_refuses_other_programs_users_and_services():
    process = mock.Mock()
    process.exe.return_value = "/usr/bin/python3"

    with mock.patch("psutil.Process", return_value=process):
        try:
            processes.launch_info(1, "llama-server")
        except processes.LaunchUnavailable as error:
            assert "not llama-server" in str(error)
        else:
            raise AssertionError

    process.exe.return_value = "/opt/llama/llama-server"
    process.username.return_value = "someone-else"

    with (
        mock.patch("psutil.Process", return_value=process),
        mock.patch.object(processes, "_current_username", return_value="me"),
    ):
        try:
            processes.launch_info(1, "llama-server")
        except processes.LaunchUnavailable as error:
            assert "another user" in str(error)
        else:
            raise AssertionError

    process.username.return_value = "me"
    process.cmdline.return_value = ["llama-server", "-m", "x.gguf"]
    process.cwd.return_value = "/opt/llama"
    process.create_time.return_value = 1.0
    process.environ.return_value = {"INVOCATION_ID": "abc"}

    with (
        mock.patch("psutil.Process", return_value=process),
        mock.patch.object(processes, "_current_username", return_value="me"),
        mock.patch.object(processes, "_cgroup_unit", return_value=None),
    ):
        try:
            processes.launch_info(1, "llama-server")
        except processes.LaunchUnavailable as error:
            assert "service" in str(error)
        else:
            raise AssertionError

        process.environ.return_value = {"A": "1"}
        info = processes.launch_info(1, "llama-server")
        assert info["args"] == ["-m", "x.gguf"] and info["env"] == {"A": "1"}

        process.environ.side_effect = psutil.AccessDenied()
        info = processes.launch_info(1, "llama-server")
        assert info["env"] is None and info["env_inherited"] is True


class SingleLlamaServer(EngineTestCase):
    """Un llama-server de un solo modelo, como proceso real de usuario."""

    def setUp(self):
        super().setUp()
        self.port = free_port()
        self.script = self.tmp / "fake_llama.py"
        self.script.write_text(FAKE_LLAMA, encoding="utf-8")
        self.model = "/models/qwen.gguf"
        self.args = [str(self.script), str(self.port), self.model]

        for setting, value in {
            "LLAMACPP_API": f"http://127.0.0.1:{self.port}",
            "LMSTUDIO_API": "http://127.0.0.1:9",
            "VLLM_API": "http://127.0.0.1:9",
            "LOG_DIR": self.tmp / "logs",
        }.items():
            patcher = mock.patch.object(config, setting, value)
            patcher.start()
            self.addCleanup(patcher.stop)

        self.process = None
        self.addCleanup(self.stop_all)
        self.start_server()

        for target, replacement in {
            "listener_pid": lambda port: self.find_server(),
            "launch_info": lambda pid, name: self.launch(pid),
        }.items():
            patcher = mock.patch.object(processes, target, replacement)
            patcher.start()
            self.addCleanup(patcher.stop)

    def launch(self, pid):
        return {
            "pid": pid,
            "exe": sys.executable,
            "args": self.args,
            "cwd": str(self.tmp),
            "env": None,
            "env_inherited": False,
            "create_time": psutil.Process(pid).create_time(),
        }

    def start_server(self):
        self.process = subprocess.Popen([sys.executable, *self.args], cwd=self.tmp)
        self.wait_for(self.responds)

    def responds(self):
        try:
            return requests.get(f"http://127.0.0.1:{self.port}/props", timeout=0.5).ok
        except requests.RequestException:
            return False

    @staticmethod
    def wait_for(condition, timeout=15):
        deadline = time.monotonic() + timeout

        while not condition():
            assert time.monotonic() < deadline, "timeout"
            time.sleep(0.05)

    def find_server(self):
        for process in psutil.process_iter(["cmdline"]):
            if (process.info["cmdline"] or [])[-3:] == self.args:
                return process.pid

        return None

    def stop_all(self):
        while (pid := self.find_server()) is not None:
            psutil.Process(pid).kill()
            time.sleep(0.05)

    def generate(self):
        return create_image("a cat")

    def test_it_is_stopped_for_the_generation_and_started_again(self):
        original = self.process.pid
        seen = []
        self.comfy.on_prompt = lambda: seen.append(self.responds())

        with mock.patch.object(config, "UNLOAD_TIMEOUT", 10), mock.patch.object(
            config, "RESTORE_TIMEOUT", 15
        ):
            result = self.generate()

        assert seen == [False]
        assert "WARNING: llamacpp/qwen.gguf was stopped" in result
        assert self.responds()
        assert state.read() is None
        assert (self.tmp / "logs" / "llama-server.log").exists()
        assert self.process.poll() is not None
        assert self.find_server() not in (None, original)

    def test_manual_and_off_never_stop_anything(self):
        for mode in ("manual", "off"):
            with mock.patch.object(config, "memory_mode", return_value=mode):
                self.generate()
                assert self.process.poll() is None
                assert self.responds()

    def test_an_unreadable_process_only_warns(self):
        def refuse(pid, name):
            raise processes.LaunchUnavailable("It runs as a system service.")

        with mock.patch.object(processes, "launch_info", refuse):
            result = self.generate()

        assert self.process.poll() is None
        assert "system service" in result

    def test_failure_to_start_again_requires_recovery_and_recover_retries(self):
        real_start = memory_servers.LlamaCppProvider._start
        calls = []

        def broken(provider, model):
            calls.append(model)
            raise OSError("no such file")

        with (
            mock.patch.object(memory_servers.LlamaCppProvider, "_start", broken),
            mock.patch.object(config, "UNLOAD_TIMEOUT", 10),
            mock.patch.object(config, "RESTORE_TIMEOUT", 0.2),
        ):
            result = self.generate()

        assert "recovery_required" in result
        assert not self.responds()
        assert state.read()["models"][0]["launch"]["exe"] == sys.executable

        with (
            mock.patch.object(memory_servers.LlamaCppProvider, "_start", real_start),
            mock.patch.object(config, "RESTORE_TIMEOUT", 15),
        ):
            assert orchestrator.recover()["restored"] == ["llamacpp/qwen.gguf"]

        assert self.responds()
        assert state.read() is None


def test_comfy_args_are_chosen_by_hardware():
    from imagehearth_mcp.engine import comfy_args

    assert comfy_args.choose("linux", 24564, 64000) == []
    assert comfy_args.choose("linux", 16384, 32000) == ["--reserve-vram", "0.5"]
    assert comfy_args.choose("windows", 16384, 32000) == ["--reserve-vram", "1.0"]
    assert comfy_args.choose("linux", 8192, 16000) == ["--reserve-vram", "0.5"]
    assert comfy_args.choose("linux", 6144, 16000) == ["--lowvram"]
    assert comfy_args.choose("windows", 2048, 16000) == ["--novram"]
    assert comfy_args.choose("linux", 0, 16000) == []


def test_comfy_args_from_config_win_over_the_chosen_ones():
    from imagehearth_mcp.engine import comfy_args

    detected = ("linux", 16384, 32000)

    with mock.patch.object(config, "COMFY_ARGS", ["--reserve-vram", "3", "--fp16-vae"]):
        assert comfy_args.effective(detected) == ["--reserve-vram", "3", "--fp16-vae"]

    with mock.patch.object(config, "COMFY_ARGS", ["--reserve-vram=3"]):
        assert comfy_args.effective(detected) == ["--reserve-vram=3"]

    with mock.patch.object(config, "COMFY_ARGS", ["--highvram"]):
        assert comfy_args.effective(("linux", 6144, 16000)) == ["--highvram"]

    with mock.patch.object(config, "COMFY_ARGS", ["--cpu"]):
        assert comfy_args.effective(("linux", 6144, 16000)) == ["--lowvram", "--cpu"]


def test_comfy_args_setting_accepts_a_string_or_a_list():
    assert config._args_setting({"comfy_args": "--lowvram --fp16-vae"}, "comfy_args", "X_NOPE") == [
        "--lowvram",
        "--fp16-vae",
    ]
    assert config._args_setting({"comfy_args": ["--a b"]}, "comfy_args", "X_NOPE") == ["--a b"]

    with mock.patch.dict("os.environ", {"X_ARGS": "--novram"}):
        assert config._args_setting({"comfy_args": "--lowvram"}, "comfy_args", "X_ARGS") == ["--novram"]


def test_doctor_shows_the_effective_comfy_arguments():
    detection = mock.Mock(system="linux", ram_mib=32000)
    detection.primary_gpu = mock.Mock(vram_mib=16384)

    with mock.patch.object(config, "COMFY_ARGS", ["--fp16-vae"]):
        assert doctor.comfy_arguments(config, detection) == ["--reserve-vram", "0.5", "--fp16-vae"]


class MemoryLimits(EngineTestCase):
    def check(self, free, ram, required=16000):
        session = orchestrator.Session("run", [])

        with (
            mock.patch("imagehearth_mcp.engine.gpu.free_mib", return_value=free),
            mock.patch.object(orchestrator, "_free_ram_mib", return_value=ram),
        ):
            orchestrator._check_free_memory(required, "Free some.", session)

        return session.warnings

    def test_it_fits_in_vram(self):
        assert self.check(20000, 0) == []

    def test_it_fits_with_system_ram_and_warns(self):
        warnings = self.check(10000, 12000)
        assert len(warnings) == 1 and "slower" in warnings[0]

    def test_it_does_not_fit_and_says_how_much_is_missing(self):
        with self.assertRaisesRegex(MemoryError, "4000 MiB are missing. Free some"):
            self.check(8000, 4000)

    def test_unknown_free_memory_never_blocks(self):
        assert self.check(None, 0) == []


def _catalog():
    from imagehearth_mcp.provisioner import manifest

    return manifest.load()


def test_the_ladder_picks_the_precision_that_fits_the_vram():
    catalog = _catalog()
    quality = catalog.profiles["quality"]
    full = catalog.profiles["full"]

    def resolved(profile, model, vram, forced=None):
        item = catalog.resolve(profile, model, vram, forced)
        return item.name, item.precision

    assert resolved(quality, "flux-dev", 24564) == ("quality", "fp8")
    assert resolved(quality, "flux-dev", 20480) == ("quality", "fp8")
    assert resolved(quality, "flux-dev", 16384) == ("quality-gguf", "gguf")
    assert resolved(quality, "flux-dev", 12288) == ("quality-gguf", "gguf")
    assert resolved(full, "flux-dev", 16384) == ("full-gguf", "gguf")
    assert resolved(quality, "flux-dev", 0) == ("quality", "fp8")
    assert resolved(quality, "flux-dev", 24564, "gguf") == ("quality-gguf", "gguf")
    assert resolved(quality, "flux-schnell", 24564) == ("quality", "fp8")
    assert resolved(quality, "sdxl", 8192) == ("quality", "fp16")
    # SDXL with editing: Kontext still picks its precision by memory.
    assert catalog.resolve(full, "sdxl", 16384).edit_precision == "gguf"
    assert catalog.resolve(full, "sdxl", 24564).edit_precision == "fp8"
    # Profiles with no quality model are left to the preflight checks.
    assert catalog.resolve(catalog.profiles["fast"], None, 1000).name == "fast"
    # Without a model, the recommended one.
    assert catalog.resolve(quality, None, 24564).quality_model == "flux-dev"
    assert catalog.resolve(quality, None, 16000).quality_model == "flux-schnell"
    assert catalog.resolve(quality, None, 8192).quality_model == "sdxl"


def test_recommendation_follows_the_vram_bands():
    catalog = _catalog()
    assert catalog.recommend(24564) == "flux-dev"
    assert catalog.recommend(20000) == "flux-dev"
    assert catalog.recommend(19999) == "flux-schnell"
    assert catalog.recommend(12000) == "flux-schnell"
    assert catalog.recommend(11999) == "sdxl"
    assert catalog.recommend(4000) == "sdxl"
    assert catalog.recommend(0) == "flux-dev"


def test_a_model_that_does_not_fit_is_resolved_with_a_warning():
    catalog = _catalog()
    quality = catalog.profiles["quality"]

    assert catalog.fits("flux-dev", 24564) and catalog.warning("flux-dev", 24564) is None
    assert catalog.fits("flux-dev", 0)
    # FLUX Dev still resolves, to its leanest option, and says what it needs.
    resolved = catalog.resolve(quality, "flux-dev", 8192)
    assert resolved.precision == "gguf"
    warning = catalog.warning("flux-dev", 8192)
    assert "12000 MiB" in warning and "8192 MiB" in warning
    assert "flux-schnell" not in str(catalog.warning("sdxl", 8192))


def test_where_nothing_fits_editing_says_what_to_use_instead():
    from imagehearth_mcp.provisioner import ProvisionError

    catalog = _catalog()

    with pytest.raises(ProvisionError) as error:
        catalog.resolve(catalog.profiles["full"], "sdxl", 10240)

    assert "12000 MiB" in str(error.value) and "--profile quality" in str(error.value)
    assert "editing" in str(error.value)

    with pytest.raises(ProvisionError, match="fp8, gguf"):
        catalog.resolve(catalog.profiles["quality"], "flux-dev", 16000, "nope")

    with pytest.raises(ProvisionError, match="Unknown quality model"):
        catalog.resolve(catalog.profiles["quality"], "nope", 16000)


def test_sdxl_is_licensed_for_commercial_use_and_pinned():
    catalog = _catalog()
    resolved = catalog.resolve(catalog.profiles["quality"], "sdxl", 8192)
    assert not resolved.nodes
    added = {m.name: m for m in resolved.models if m.name != "sdxl_turbo"}
    assert set(added) == {"sdxl_base", "sdxl_offset_lora"}
    assert {m.license for m in added.values()} == {"openrail-pp"}
    assert "openrail-pp" in {entry.key for entry in catalog.licenses_for(resolved)}
    assert catalog.minimum_profile("sdxl_base", "linux").base == "quality"
    assert catalog.minimum_profile("sdxl_quality", "linux").base == "quality"
    assert catalog.models["realvisxl"].legacy
    notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    assert "SDXL 1.0" in notices and "offset LoRA" in notices


def test_schnell_and_sdxl_carry_no_non_commercial_license():
    catalog = _catalog()

    for model in ("flux-schnell", "sdxl"):
        for name in ("quality", "full"):
            resolved = catalog.resolve(catalog.profiles[name], model, 24564)
            keys = {entry.key for entry in catalog.licenses_for(resolved)}
            expected = name == "full"  # only Kontext, for editing
            assert ("flux-dev-non-commercial" in keys) == expected
            assert {m.name for m in resolved.models} & {"flux_dev", "flux_dev_gguf"} == set()

    assert catalog.describe_quality("flux-dev", 24564)["commercial_use"] is False
    assert catalog.describe_quality("flux-schnell", 24564)["commercial_use"] is True
    assert catalog.describe_quality("sdxl", 24564)["commercial_use"] is True


def test_full_with_sdxl_includes_the_flux_components_through_kontext():
    catalog = _catalog()
    resolved = catalog.resolve(catalog.profiles["full"], "sdxl", 24564)
    assert {"t5xxl", "clip_l", "flux_vae", "flux_kontext"} <= {m.name for m in resolved.models}
    quality = catalog.resolve(catalog.profiles["quality"], "sdxl", 24564)
    assert not {"t5xxl", "clip_l", "flux_vae"} & {m.name for m in quality.models}


def test_sdxl_workflows_fit_the_template_conventions():
    import json

    from imagehearth_mcp.engine import catalog as engine_catalog
    from imagehearth_mcp.engine import config as engine_config
    from imagehearth_mcp.engine.workflow_runner import negative_prompt_applies

    for name in ("sdxl_base", "sdxl_quality"):
        workflow = json.loads((engine_config.WORKFLOWS_DIR / f"{name}.json").read_text(encoding="utf-8"))
        kinds = {node["class_type"] for node in workflow.values()}
        assert {"CheckpointLoaderSimple", "LoraLoader", "KSampler", "SaveImage"} <= kinds
        assert negative_prompt_applies(workflow)
        sampler = next(n for n in workflow.values() if n["class_type"] == "KSampler")
        assert sampler["inputs"]["steps"] > 4

    base = json.loads((engine_config.WORKFLOWS_DIR / "sdxl_base.json").read_text(encoding="utf-8"))
    assert base["1"]["inputs"]["ckpt_name"] == "sd_xl_base_1.0.safetensors"
    assert engine_catalog.VARIANTS["high"] == (
        "flux_dev",
        "flux_dev_gguf",
        "flux_schnell",
        "sdxl_base",
        "sdxl_quality",
    )


def test_schnell_workflow_has_four_steps_and_no_guidance():
    import json

    from imagehearth_mcp.engine import config as engine_config

    workflow = json.loads((engine_config.WORKFLOWS_DIR / "flux_schnell.json").read_text(encoding="utf-8"))
    kinds = {node["class_type"] for node in workflow.values()}
    assert "FluxGuidance" not in kinds
    sampler = next(n for n in workflow.values() if n["class_type"] == "KSampler")
    assert sampler["inputs"]["steps"] == 4 and sampler["inputs"]["cfg"] == 1.0
    assert workflow["1"]["inputs"]["unet_name"] == "flux1-schnell-fp8-e4m3fn.safetensors"
    save = next(n for n in workflow.values() if n["class_type"] == "SaveImage")
    assert save["inputs"]["filename_prefix"] == "imagehearth/flux_schnell"


def test_profiles_are_proposed_by_vram():
    from types import SimpleNamespace

    from imagehearth_mcp.provisioner import setup

    catalog = _catalog()
    assert list(catalog.profiles_for("linux")) == ["fast", "quality", "full"]

    def propose(vram):
        gpu = SimpleNamespace(vram_mib=vram)
        detection = SimpleNamespace(
            primary_gpu=gpu, system="linux", disk_free_bytes=10**12
        )
        return setup.propose_profile(detection, catalog)

    assert propose(24564) == "full"
    assert propose(16384) == "full"
    assert propose(12288) == "full"
    assert propose(8192) == "quality"
    assert propose(6144) == "fast"


def test_gguf_options_carry_their_node_models_and_licenses():
    catalog = _catalog()
    resolved = catalog.resolve(catalog.profiles["quality"], "flux-dev", 16000)
    assert resolved.variant_of == "quality" and resolved.base == "quality"
    assert [node.folder for node in resolved.nodes]
    assert {"flux_dev_gguf", "t5xxl_gguf"} <= {model.name for model in resolved.models}
    assert resolved.bytes < catalog.resolve(catalog.profiles["quality"], "flux-dev", 24564).bytes
    assert "flux-dev-non-commercial" in {entry.key for entry in catalog.licenses_for(resolved)}


def test_service_is_told_by_its_cgroup_when_there_is_one():
    environment = {"INVOCATION_ID": "inherited from a terminal"}

    with mock.patch.object(processes, "_cgroup_unit", return_value="app-terminal-1.scope"):
        assert not processes._runs_as_service(1, environment)

    with mock.patch.object(processes, "_cgroup_unit", return_value="llama.service"):
        assert processes._runs_as_service(1, {})
