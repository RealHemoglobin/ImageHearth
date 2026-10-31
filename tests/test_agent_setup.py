"""`setup_status` y `setup_start` con subprocesos simulados."""

import json
import subprocess
import sys
import time

import pytest

from imagehearth_mcp.engine import config
from imagehearth_mcp.platform import locks
from imagehearth_mcp.provisioner import (
    ProvisionError,
    agent_setup,
    detect,
    manifest,
    models,
)


@pytest.fixture
def paths(tmp_path, monkeypatch):
    for name, value in {
        "DATA_DIR": tmp_path,
        "COMFY_DIR": tmp_path / "comfyui",
        "INSTALL_MANIFEST": tmp_path / "install.json",
        "SETUP_LOCK": tmp_path / "setup.lock",
        "SETUP_JOB_LOCK": tmp_path / "job.lock",
        "SETUP_JOB_FILE": tmp_path / "state" / "job.json",
        "SETUP_JOB_LOG": tmp_path / "logs" / "job.log",
        "CONFIG_FILE": tmp_path / "config.toml",
    }.items():
        monkeypatch.setattr(config, name, value)

    return tmp_path


class FakeProcess:
    pid = 4242


@pytest.fixture
def spawned(paths, monkeypatch):
    calls = []

    def spawn(profile, existing):
        calls.append((profile, existing))
        return FakeProcess()

    monkeypatch.setattr(agent_setup, "_spawn", spawn)
    monkeypatch.setattr(agent_setup.processes, "create_time", lambda pid: 1.0)
    return calls


def test_refuses_without_acceptance(spawned):
    for value in (False, None, "yes", 1):
        with pytest.raises(ValueError, match="licenses"):
            agent_setup.start("fast", value)

    assert not spawned


def test_refuses_unknown_and_experimental_profiles(spawned):
    with pytest.raises(ValueError, match="Unknown profile"):
        agent_setup.start("huge", True)

    with pytest.raises(ValueError, match=r"Unknown|experimental"):
        agent_setup.start("mac-fast", True)

    assert not spawned


def test_experimental_on_macos_is_refused(spawned, monkeypatch):
    monkeypatch.setattr(agent_setup.sys, "platform", "darwin")

    with pytest.raises(ValueError, match="experimental"):
        agent_setup.start("mac-fast", True)

    assert not spawned


def test_tool_requires_both_arguments():
    import asyncio

    from imagehearth_mcp.server import mcp

    tools = {tool.name: tool for tool in asyncio.run(mcp.list_tools())}
    assert set(tools["setup_start"].inputSchema["required"]) == {"profile", "accept_licenses"}


def test_start_records_the_job_and_refuses_a_second(spawned, monkeypatch):
    assert agent_setup.start("fast", True)["state"] == "running"
    assert spawned == [("fast", "")]
    monkeypatch.setattr(agent_setup.processes, "is_same_process", lambda pid, created: True)

    with pytest.raises(RuntimeError, match="already running"):
        agent_setup.start("full", True)

    assert len(spawned) == 1


def test_refuses_while_a_manual_setup_holds_the_lock(spawned):
    with locks.held(config.SETUP_LOCK, timeout=1), pytest.raises(RuntimeError, match="already"):
        # El bloqueo de archivo es por objeto: desde el mismo proceso también se ve.
        agent_setup.start("fast", True)

    assert not spawned


REAL_DETECT = detect.detect


def fake_detection(tmp_path, **extra):
    return REAL_DETECT(
        disk_path=tmp_path,
        run=lambda *a, **k: None,
        session=_NoServer(),
        which=lambda name: None,
        system="linux",
        machine="x86_64",
        home=tmp_path,
        environ={},
        sysfs=tmp_path / "none",
        running_dirs=[],
        **extra,
    )


class _NoServer:
    def get(self, *args, **kwargs):
        import requests

        raise requests.ConnectionError


def status(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_setup.detect, "detect", lambda **k: fake_detection(tmp_path))
    monkeypatch.setattr(agent_setup.sys, "platform", "linux")
    return agent_setup.status()


def test_status_lists_sizes_licenses_and_next_step(paths, monkeypatch):
    result = status(paths, monkeypatch)
    names = [profile["name"] for profile in result["profiles"]]
    assert names == list(manifest.load().profiles_for("linux"))
    fast = result["profiles"][0]
    assert fast["download_gb"] > 0
    assert fast["licenses"]
    assert not fast["installed"]
    assert result["comfyui"]["installed"] is False
    assert result["installation"] == {"state": "none"}
    assert "setup_start" in result["next_step"]


def test_status_reports_download_progress(paths, monkeypatch):
    profile = manifest.load().profiles["fast"]
    staging = paths / "comfyui" / "models" / models.STAGING_DIR
    staging.mkdir(parents=True)
    (staging / f"{profile.models[0].name}.part").write_bytes(b"x" * 1000)
    agent_setup._write_job(state="running", profile="fast", pid=None)
    monkeypatch.setattr(agent_setup.processes, "is_same_process", lambda pid, created: True)
    job = status(paths, monkeypatch)["installation"]
    assert job["state"] == "interrupted"  # Sin PID no hay proceso vivo.
    assert job["model_bytes"] == {"downloaded": 1000, "total": profile.bytes}


def test_dead_process_is_reported_as_interrupted(paths, monkeypatch):
    agent_setup._write_job(state="running", profile="fast", pid=999999, create_time=1.0)
    monkeypatch.setattr(agent_setup.processes, "is_same_process", lambda pid, created: False)
    job = status(paths, monkeypatch)["installation"]
    assert job["state"] == "interrupted"
    assert "setup_start" in job["error"]


def test_failure_midway_is_recorded(paths, monkeypatch, capsys):
    def fail(args):
        raise ProvisionError("no space")

    monkeypatch.setattr("imagehearth_mcp.provisioner.setup.run", fail)
    assert agent_setup.main(["fast"]) == 1
    job = agent_setup._read_job()
    assert job["state"] == "failed"
    assert job["error"] == "no space"


def test_success_is_recorded_with_noninteractive_arguments(paths, monkeypatch):
    seen = []

    def succeed(args):
        seen.append(args)
        return 0

    monkeypatch.setattr("imagehearth_mcp.provisioner.setup.run", succeed)
    assert agent_setup.main(["fast"]) == 0
    assert agent_setup._read_job()["state"] == "finished"
    assert seen[0].accept_licenses
    assert seen[0].non_interactive
    assert seen[0].managed
    assert seen[0].profile == "fast"


def test_process_survives_its_parent(paths):
    """El lanzador muere nada más empezar y el proceso desacoplado sigue escribiendo."""
    marker = paths / "survived"
    child = (
        "import time,pathlib;time.sleep(1.5);"
        f"pathlib.Path({str(marker)!r}).write_text('yes',encoding='utf-8')"
    )
    launcher = (
        "import subprocess,sys;"
        "from imagehearth_mcp.platform import spawn;"
        f"subprocess.Popen([sys.executable,'-c',{child!r}],stdin=subprocess.DEVNULL,"
        "stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,**spawn.detached_options())"
    )
    subprocess.run([sys.executable, "-c", launcher], check=True, timeout=30)
    assert not marker.exists()
    deadline = time.monotonic() + 15

    while not marker.exists() and time.monotonic() < deadline:
        time.sleep(0.1)

    assert marker.exists()


def test_import_of_server_stays_light():
    code = (
        "import sys, imagehearth_mcp.server, imagehearth_mcp.cli;"
        "bad=[m for m in ('huggingface_hub','torch') if m in sys.modules];"
        "print(json.dumps(bad))"
    )
    output = subprocess.run(
        [sys.executable, "-c", "import json;" + code],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert json.loads(output) == []
