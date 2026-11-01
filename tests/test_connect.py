"""`connect` contra configuraciones en carpetas temporales, sin tocar las reales."""

import argparse
import json
import re
import stat
import sys
import tomllib
from pathlib import Path
from unittest import mock

import pytest
import yaml

from imagehearth_mcp.engine import config
from imagehearth_mcp.provisioner import ProvisionError, connect, maintenance
from imagehearth_mcp.provisioner.install_manifest import InstallManifest

COMMAND = "/opt/bin/imagehearth-mcp"
EDITED = ("claude-desktop", "codex", "gemini", "opencode", "hermes", "pi", "vscode", "cursor")

HERMES_CONFIG = """\
# Mi configuración
model: local  # no tocar
# mcp_servers:
#   time:
#     command: uvx
mcp_servers:
  caveman:
    command: /bin/caveman
  other:
    command: /bin/other

terminal:
  backend: local
"""
CODEX_CONFIG = """\
# Comentario
model = "x"

[mcp_servers.caveman]
command = "/bin/caveman"

# >>> bloque ajeno
[features]
a = true
"""


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(connect.Path, "home", lambda: tmp_path)

    for name in ("XDG_CONFIG_HOME", "CODEX_HOME", "HERMES_HOME"):
        monkeypatch.delenv(name, raising=False)

    # Sin APPDATA, en Windows se usaría la carpeta real del usuario.
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData" / "Roaming"))

    # Sin CLI oficial, para cubrir la edición del archivo en todos los formatos.
    monkeypatch.setattr(connect.shutil, "which", lambda name: None)
    monkeypatch.setattr(config, "INSTALL_MANIFEST", tmp_path / "data" / "install.json")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    return tmp_path


def entry_of(client):
    text = client.path().read_text(encoding="utf-8")
    return connect._parse(client, text)[client.key][connect.SERVER_NAME]


def backups(client):
    return list(client.path().parent.glob(f"{client.path().name}.imagehearth-*.bak"))


@pytest.mark.parametrize("name", EDITED)
def test_empty_config_gets_the_absolute_command(home, name):
    client = connect.CLIENTS[name]
    assert connect.connect(client, COMMAND, skill=False)
    assert connect._command_of(entry_of(client)) == [COMMAND]
    assert not backups(client)


@pytest.mark.parametrize("name", EDITED)
def test_repeating_changes_nothing(home, name):
    client = connect.CLIENTS[name]
    connect.connect(client, COMMAND, skill=False)
    first = client.path().read_text(encoding="utf-8")
    connect.connect(client, COMMAND, skill=False)
    assert client.path().read_text(encoding="utf-8") == first
    assert not backups(client)
    records = InstallManifest.load(config.INSTALL_MANIFEST)
    assert [c["client"] for c in records.connections] == [name]


@pytest.mark.parametrize("name", EDITED)
def test_corrupt_config_is_left_alone(home, name):
    client = connect.CLIENTS[name]
    client.path().parent.mkdir(parents=True)
    client.path().write_text("{ [ = : not valid", encoding="utf-8")

    with pytest.raises(ProvisionError, match="connect --print"):
        connect.connect(client, COMMAND, skill=False)

    assert client.path().read_text(encoding="utf-8") == "{ [ = : not valid"
    assert not backups(client)


def test_json_keeps_other_entries_and_backs_up(home):
    client = connect.CLIENTS["cursor"]
    client.path().parent.mkdir(parents=True)
    original = {"x": 1, "mcpServers": {"other": {"command": "/bin/other"}}}
    client.path().write_text(json.dumps(original), encoding="utf-8")
    connect.connect(client, COMMAND, skill=False)
    values = json.loads(client.path().read_text(encoding="utf-8"))
    assert values["x"] == 1
    assert values["mcpServers"]["other"] == {"command": "/bin/other"}
    assert json.loads(backups(client)[0].read_text(encoding="utf-8")) == original


def test_old_entry_is_replaced_without_duplicates(home):
    client = connect.CLIENTS["codex"]
    client.path().parent.mkdir(parents=True)
    client.path().write_text(
        CODEX_CONFIG + '\n[mcp_servers.imagehearth]\ncommand = "/old"\n\n[z]\nb = 1\n',
        encoding="utf-8",
    )
    connect.connect(client, COMMAND, skill=False)
    text = client.path().read_text(encoding="utf-8")
    assert text.count("[mcp_servers.imagehearth]") == 1
    values = tomllib.loads(text)
    assert values["mcp_servers"]["imagehearth"]["command"] == COMMAND
    assert values["z"] == {"b": 1}


def test_entry_without_the_timeout_is_updated(home):
    client = connect.CLIENTS["codex"]
    client.path().parent.mkdir(parents=True)
    client.path().write_text(f'[mcp_servers.imagehearth]\ncommand = "{COMMAND}"\n', encoding="utf-8")
    connect.connect(client, COMMAND, skill=False)
    assert entry_of(client)["tool_timeout_sec"] == connect.TOOL_TIMEOUT


def test_toml_keeps_comments_and_other_tables(home):
    client = connect.CLIENTS["codex"]
    client.path().parent.mkdir(parents=True)
    client.path().write_text(CODEX_CONFIG, encoding="utf-8")
    connect.connect(client, COMMAND, skill=False)
    text = client.path().read_text(encoding="utf-8")
    assert text.startswith(CODEX_CONFIG)
    assert connect._remove_text(client, text).rstrip() == CODEX_CONFIG.rstrip()


def test_toml_removal_keeps_comment_of_the_next_table(home):
    client = connect.CLIENTS["codex"]
    text = '[mcp_servers.imagehearth]\ncommand = "/x"\n\n# de features\n[features]\na = 1\n'
    assert "# de features\n[features]" in connect._remove_text(client, text)


def test_yaml_keeps_comments_and_other_entries(home):
    client = connect.CLIENTS["hermes"]
    client.path().parent.mkdir(parents=True)
    client.path().write_text(HERMES_CONFIG, encoding="utf-8")
    connect.connect(client, COMMAND, skill=False)
    text = client.path().read_text(encoding="utf-8")

    for line in HERMES_CONFIG.splitlines():
        assert line in text

    values = yaml.safe_load(text)
    assert set(values["mcp_servers"]) == {"imagehearth", "caveman", "other"}
    assert values["terminal"] == {"backend": "local"}
    assert yaml.safe_load(connect._remove_text(client, text)) == yaml.safe_load(HERMES_CONFIG)


def test_yaml_without_section_appends_it(home):
    client = connect.CLIENTS["hermes"]
    client.path().parent.mkdir(parents=True)
    client.path().write_text("model: local", encoding="utf-8")
    connect.connect(client, COMMAND, skill=False)
    assert yaml.safe_load(client.path().read_text(encoding="utf-8")) == {
        "model": "local",
        "mcp_servers": {"imagehearth": {"command": COMMAND, "timeout": connect.TOOL_TIMEOUT}},
    }


def test_yaml_layout_it_cannot_edit_is_refused(home):
    client = connect.CLIENTS["hermes"]
    client.path().parent.mkdir(parents=True)
    original = 'mcp_servers: {other: {command: "/x"}}\n'
    client.path().write_text(original, encoding="utf-8")

    with pytest.raises(ProvisionError, match="connect --print"):
        connect.connect(client, COMMAND, skill=False)

    assert client.path().read_text(encoding="utf-8") == original


@pytest.mark.skipif(sys.platform == "win32", reason="Permisos POSIX")
def test_permissions_are_kept(home):
    client = connect.CLIENTS["codex"]
    client.path().parent.mkdir(parents=True)
    client.path().write_text(CODEX_CONFIG, encoding="utf-8")
    client.path().chmod(0o600)
    connect.connect(client, COMMAND, skill=False)
    assert stat.S_IMODE(client.path().stat().st_mode) == 0o600
    assert stat.S_IMODE(backups(client)[0].stat().st_mode) == 0o600


def test_no_environment_is_copied(home, monkeypatch):
    monkeypatch.setenv("SOME_SECRET", "hunter2")

    for client in connect.CLIENTS.values():
        assert "hunter2" not in connect.snippet(client, COMMAND)
        assert "env" not in connect.snippet(client, COMMAND)


def test_official_cli_is_used_and_verified(home, monkeypatch):
    client = connect.CLIENTS["pi"]
    calls = []
    monkeypatch.setattr(connect.shutil, "which", lambda name: f"/bin/{name}")

    def fake_cli(argv):
        calls.append(argv)
        client.path().parent.mkdir(parents=True, exist_ok=True)
        client.path().write_text(
            json.dumps({"mcpServers": {"imagehearth": {"command": COMMAND}}}), encoding="utf-8"
        )

    monkeypatch.setattr(connect, "_run_cli", fake_cli)
    connect.connect(client, COMMAND, skill=False)
    assert calls == [["/bin/pi", "mcp", "add", "imagehearth", "--exposure", "direct", "--", COMMAND]]


def test_cli_that_lies_is_reported(home, monkeypatch):
    monkeypatch.setattr(connect.shutil, "which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(connect, "_run_cli", lambda argv: None)

    with pytest.raises(ProvisionError, match="reported success"):
        connect.connect(connect.CLIENTS["pi"], COMMAND, skill=False)


def test_print_formats_parse(home):
    for client in connect.CLIENTS.values():
        values = connect._parse(client, connect.snippet(client, COMMAND))
        assert connect._command_of(values[client.key]["imagehearth"]) == [COMMAND]


def test_jetbrains_only_prints(home, capsys):
    assert not connect.connect(connect.CLIENTS["jetbrains"], COMMAND)
    assert "Model Context Protocol" in capsys.readouterr().out


def test_unknown_client_points_to_print():
    with pytest.raises(ProvisionError, match="--print"):
        connect.get_client("nope")


@pytest.mark.parametrize(
    ("platform", "expected"),
    [
        ("linux", ".config/Claude/claude_desktop_config.json"),
        ("darwin", "Library/Application Support/Claude/claude_desktop_config.json"),
    ],
)
def test_paths_per_system(home, monkeypatch, platform, expected):
    monkeypatch.setattr(connect.sys, "platform", platform)
    assert connect.CLIENTS["claude-desktop"].path() == home / expected


def test_windows_path_uses_appdata(home, monkeypatch):
    monkeypatch.setattr(connect.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(home / "Roaming"))
    assert connect.CLIENTS["vscode"].path() == home / "Roaming" / "Code" / "User" / "mcp.json"


def test_skill_is_installed_and_removed_only_if_own(home):
    client = connect.CLIENTS["hermes"]
    connect.connect(client, COMMAND)
    skill = home / ".hermes" / "skills" / "imagehearth" / "SKILL.md"
    assert skill.is_file()
    connect.disconnect(client)
    assert not skill.exists()

    foreign = home / ".hermes" / "skills" / "imagehearth" / "SKILL.md"
    foreign.parent.mkdir(parents=True)
    foreign.write_text("mine", encoding="utf-8")
    connect.connect(client, COMMAND)
    assert foreign.read_text(encoding="utf-8") == "mine"
    connect.disconnect(client)
    assert foreign.read_text(encoding="utf-8") == "mine"


def test_remove_keeps_the_rest(home):
    client = connect.CLIENTS["cursor"]
    client.path().parent.mkdir(parents=True)
    client.path().write_text(
        json.dumps({"mcpServers": {"other": {"command": "/x"}}}), encoding="utf-8"
    )
    connect.connect(client, COMMAND, skill=False)
    connect.disconnect(client)
    assert json.loads(client.path().read_text(encoding="utf-8")) == {
        "mcpServers": {"other": {"command": "/x"}}
    }


def test_uninstall_undoes_only_what_connect_registered(home, monkeypatch):
    own = connect.CLIENTS["cursor"]
    changed = connect.CLIENTS["claude-desktop"]
    connect.connect(own, COMMAND, skill=False)
    connect.connect(changed, COMMAND, skill=False)
    changed.path().write_text(
        json.dumps({"mcpServers": {"imagehearth": {"command": "/user/changed"}}}),
        encoding="utf-8",
    )

    monkeypatch.setattr(maintenance, "_stop_managed", lambda: None)
    monkeypatch.setattr(config, "SETUP_LOCK", home / "data" / "setup.lock")
    monkeypatch.setattr(config, "CONFIG_FILE", home / "config.toml")
    job = home / "data" / "setup_job.json"
    job.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(config, "SETUP_JOB_FILE", job)
    args = argparse.Namespace(yes=True, keep_models=True, remove_models=False)
    assert maintenance.uninstall(args) == 0
    assert not job.exists()
    assert "imagehearth" not in json.loads(own.path().read_text(encoding="utf-8")).get(
        "mcpServers", {}
    )
    assert json.loads(changed.path().read_text(encoding="utf-8"))["mcpServers"]["imagehearth"] == {
        "command": "/user/changed"
    }


def test_detect_needs_yes_without_terminal(home, monkeypatch):
    client = connect.CLIENTS["cursor"]
    client.path().parent.mkdir(parents=True)
    monkeypatch.setattr(connect.sys, "stdin", mock.Mock(isatty=lambda: False))
    args = argparse.Namespace(yes=False, no_skill=True)

    with pytest.raises(ProvisionError, match="--yes"):
        connect._detect(args, COMMAND)

    assert not client.path().exists()
    args.yes = True
    assert connect._detect(args, COMMAND) == 0
    assert client.path().exists()


def test_docs_match_print():
    """Cada fragmento de docs/agents.md es lo que imprime `connect --print`."""
    docs = Path(__file__).parent.parent / "docs" / "agents.md"
    text = docs.read_text(encoding="utf-8")
    placeholder = "/absolute/path/to/imagehearth-mcp"

    for client in connect.CLIENTS.values():
        match = re.search(
            rf"<!-- snippet:{client.name} -->\s*```\w+\n(.*?)```", text, re.DOTALL
        )
        assert match, client.name
        assert match.group(1) == connect.snippet(client, placeholder), client.name
        section = text[text.index(f"<!-- snippet:{client.name} -->") - 400 : match.start()]
        assert client.level.capitalize() in section, client.name
