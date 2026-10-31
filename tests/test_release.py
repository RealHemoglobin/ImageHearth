"""Lo que se publica: versión única, paquete limpio, scripts y documentos públicos."""

import json
import os
import re
import shutil
import subprocess
import tarfile
import tomllib
import zipfile
from pathlib import Path

import jsonschema
import pytest
import yaml

from imagehearth_mcp import cli

ROOT = Path(__file__).resolve().parent.parent
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
    "version"
]
SCRIPTS = ("install.sh", "install.ps1")
READMES = ("README.md", "README.es.md")
SERVER_NAME = "io.github.RealHemoglobin/imagehearth"
LOCAL = ("engine.lock", "state/", "logs/", "output/", "specs/", ".venv/", ".env")
MODELS = (".safetensors", ".gguf", ".ckpt", ".pth")


def read(name):
    return (ROOT / name).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("dist")
    subprocess.run(
        ["uv", "build", "--quiet", "--out-dir", str(out)], cwd=ROOT, check=True
    )
    return out


def assert_clean(names):
    for name in names:
        assert not name.endswith(MODELS), name
        assert not any(f"/{part}" in f"/{name}" for part in LOCAL), name


def test_version_command_matches_pyproject(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--version"])

    assert capsys.readouterr().out.split() == ["imagehearth-mcp", VERSION]


@pytest.mark.parametrize("name", SCRIPTS)
def test_scripts_pin_the_package_version(name):
    assert re.search(rf'^\s*\$?VERSION\s*=\s*"{re.escape(VERSION)}"', read(name), re.MULTILINE | re.IGNORECASE)


@pytest.mark.parametrize("name", ["llms-install.md", "docs/agents.md", *READMES])
def test_manual_commands_pin_the_package_version(name):
    assert set(re.findall(r"imagehearth-mcp==([0-9a-z.]*[0-9a-z])", read(name))) == {VERSION}


@pytest.mark.parametrize("name", SCRIPTS)
def test_scripts_never_elevate_or_accept_licenses(name):
    text = read(name)
    assert "sudo" not in text
    assert "--accept-licenses" not in text
    assert "RunAs" not in text


@pytest.mark.skipif(not shutil.which("sh"), reason="needs a POSIX shell")
def test_install_sh_syntax():
    subprocess.run(["sh", "-n", str(ROOT / "install.sh")], check=True)


@pytest.mark.skipif(not shutil.which("setsid"), reason="needs setsid")
def test_install_sh_without_terminal_stops_before_changing_anything(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    marker = tmp_path / "uv-was-called"
    uv = bin_dir / "uv"
    uv.write_text(f'#!/bin/sh\ntouch "{marker}"\n', encoding="utf-8")
    uv.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}

    # setsid deja al proceso sin terminal de control: /dev/tty no se puede abrir.
    result = subprocess.run(
        ["setsid", "--wait", "sh", str(ROOT / "install.sh")],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 1
    assert "No terminal available" in result.stderr
    assert not marker.exists()


def test_server_json_is_valid_and_matches_the_package():
    server = json.loads(read("server.json"))
    schema = json.loads(read("tests/data/server.schema.json"))

    jsonschema.validate(server, schema)
    assert server["$schema"] == schema["$id"]
    assert server["name"] == SERVER_NAME
    assert server["version"] == VERSION
    assert [package["version"] for package in server["packages"]] == [VERSION]
    assert server["packages"][0]["identifier"] == "imagehearth-mcp"


def test_readme_has_the_registry_ownership_marker():
    assert f"<!-- mcp-name: {SERVER_NAME} -->" in read("README.md")


@pytest.mark.parametrize("name", READMES)
def test_readme_works_outside_github(name):
    text = read(name)
    links = re.findall(r"\]\(([^)\s]+)", text)

    assert links
    assert not [link for link in links if not link.startswith(("http", "#"))]
    # PyPI muestra estas alertas de GitHub como texto.
    assert "[!" not in text


def test_wheel_contents(built):
    with zipfile.ZipFile(next(built.glob("*.whl"))) as wheel:
        names = wheel.namelist()

    assert_clean(names)
    assert not [name for name in names if name.startswith(("tests/", "scripts/", "docs/"))]

    for expected in (
        "imagehearth_mcp/data/models.toml",
        "imagehearth_mcp/data/skill/SKILL.md",
        "imagehearth_mcp/data/imagehearth_status/__init__.py",
        "imagehearth_mcp/data/imagehearth_status/LICENSE",
        "imagehearth_mcp/data/workflows/sdxl_turbo.json",
    ):
        assert expected in names

    licenses = [name for name in names if ".dist-info/licenses/" in name]
    assert {Path(name).name for name in licenses} >= {"LICENSE", "THIRD_PARTY_NOTICES.md"}


def test_sdist_contents(built):
    with tarfile.open(next(built.glob("*.tar.gz"))) as sdist:
        names = [name.partition("/")[2] for name in sdist.getnames()]

    assert_clean(names)

    for expected in (
        "pyproject.toml",
        "README.md",
        "LICENSE",
        "THIRD_PARTY_NOTICES.md",
        "src/imagehearth_mcp/data/imagehearth_status/LICENSE",
        "src/imagehearth_mcp/data/models.toml",
    ):
        assert expected in names


@pytest.mark.parametrize("name", ["install_failure.yml", "bug_report.yml"])
def test_failure_templates_require_doctor_output(name):
    template = yaml.safe_load(read(f".github/ISSUE_TEMPLATE/{name}"))
    fields = [
        field
        for field in template["body"]
        if "doctor --json" in field["attributes"].get("label", "")
    ]

    assert fields
    assert fields[0]["validations"]["required"] is True
