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


# Desconexión completa: lo que `connect` no registró (fase 10)


def connect_unregistered(client, skill=False):
    """Conectado como antes de perder el registro: la entrada existe y `install.json` no."""
    connect.connect(client, COMMAND, skill=skill)
    config.INSTALL_MANIFEST.unlink(missing_ok=True)


def write_json(path, values):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(values, indent=2), encoding="utf-8")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def claude_project(home, **servers):
    """Un proyecto conocido por `~/.claude.json`, con su `.mcp.json` si hay `project`."""
    folder = home / "work"
    folder.mkdir(exist_ok=True)
    project = servers.pop("project", None)

    if project:
        write_json(folder / ".mcp.json", {"mcpServers": project})

    return folder, servers


@pytest.fixture
def uninstall_env(home, monkeypatch):
    monkeypatch.setattr(maintenance, "_stop_managed", lambda: None)
    monkeypatch.setattr(config, "SETUP_LOCK", home / "data" / "setup.lock")
    monkeypatch.setattr(config, "CONFIG_FILE", home / "config.toml")
    monkeypatch.setattr(config, "SETUP_JOB_FILE", home / "data" / "setup_job.json")
    (home / "data").mkdir(exist_ok=True)
    return argparse.Namespace(yes=True, keep_models=True, remove_models=False)


def test_unregistered_entry_needs_confirmation(home, monkeypatch, capsys):
    client = connect.CLIENTS["cursor"]
    connect_unregistered(client)
    monkeypatch.setattr(connect, "ask", lambda question: False)
    connect.disconnect(client, interactive=True)
    assert entry_of(client)
    monkeypatch.setattr(connect, "ask", lambda question: True)
    connect.disconnect(client, interactive=True)
    assert "mcpServers" not in read_json(client.path())
    assert len(backups(client)) >= 1
    assert "Restart the agents" in capsys.readouterr().out


def test_unregistered_entry_goes_with_yes(home):
    client = connect.CLIENTS["cursor"]
    connect_unregistered(client)
    connect.disconnect(client, yes=True, interactive=False)
    assert "mcpServers" not in read_json(client.path())


def test_non_interactive_without_yes_lists_and_touches_nothing(home, capsys):
    client = connect.CLIENTS["cursor"]
    connect_unregistered(client)
    connect.disconnect(client, interactive=False)
    assert entry_of(client)
    out = capsys.readouterr().out
    assert "connect --remove cursor --yes" in out


def test_old_name_imageengine_is_removed(home):
    client = connect.CLIENTS["cursor"]
    write_json(
        client.path(),
        {"mcpServers": {"imageengine": {"command": "/old/imageengine-mcp"}, "x": {"command": "/x"}}},
    )
    connect.disconnect(client, yes=True)
    assert read_json(client.path()) == {"mcpServers": {"x": {"command": "/x"}}}


def test_command_changed_by_a_reinstall_is_still_removed(home):
    client = connect.CLIENTS["cursor"]
    connect.connect(client, COMMAND, skill=False)
    write_json(client.path(), {"mcpServers": {"imagehearth": {"command": "/new/path/imagehearth-mcp"}}})
    connect.disconnect(client)
    assert "mcpServers" not in read_json(client.path())


def test_foreign_command_is_kept_and_reported(home, capsys):
    client = connect.CLIENTS["cursor"]
    write_json(client.path(), {"mcpServers": {"imagehearth": {"command": "/bin/other-tool"}}})
    connect.disconnect(client, yes=True)
    assert entry_of(client) == {"command": "/bin/other-tool"}
    out = capsys.readouterr().out
    assert "/bin/other-tool" in out
    assert str(client.path()) in out


def test_claude_code_local_scope_keeps_the_rest_of_the_project(home):
    folder, _ = claude_project(home)
    client = connect.CLIENTS["claude-code"]
    write_json(
        client.path(),
        {
            "numStartups": 3,
            "mcpServers": {"keep": {"command": "/k"}},
            "projects": {
                str(folder): {
                    "allowedTools": ["a"],
                    "mcpServers": {
                        "imageengine": {"command": "/o/imageengine-mcp"},
                        "keep": {"command": "/k"},
                    },
                }
            },
        },
    )
    connect.disconnect(client, yes=True)
    assert read_json(client.path()) == {
        "numStartups": 3,
        "mcpServers": {"keep": {"command": "/k"}},
        "projects": {
            str(folder): {"allowedTools": ["a"], "mcpServers": {"keep": {"command": "/k"}}}
        },
    }
    assert len(backups(client)) >= 1


def test_project_file_is_reported_and_not_edited(home, capsys):
    folder, _ = claude_project(home, project={"imagehearth": {"command": COMMAND}})
    client = connect.CLIENTS["claude-code"]
    write_json(client.path(), {"projects": {str(folder): {"mcpServers": {}}}})
    before = (folder / ".mcp.json").read_text(encoding="utf-8")
    connect.disconnect(client, yes=True)
    assert (folder / ".mcp.json").read_text(encoding="utf-8") == before
    out = capsys.readouterr().out
    assert "claude mcp remove --scope project imagehearth" in out
    assert str(folder) in out


def test_official_cli_is_used_per_scope(home, monkeypatch):
    folder, _ = claude_project(home)
    client = connect.CLIENTS["claude-code"]
    write_json(
        client.path(),
        {
            "mcpServers": {"imagehearth": {"command": COMMAND}},
            "projects": {str(folder): {"mcpServers": {"imageengine": {"command": "/o/imageengine-mcp"}}}},
        },
    )
    monkeypatch.setattr(connect.shutil, "which", lambda name: "/bin/claude")
    calls = []

    def fake(argv, cwd=None):
        calls.append((argv, cwd))
        values = read_json(client.path())

        if "local" in argv:
            del values["projects"][str(folder)]["mcpServers"]["imageengine"]
        else:
            del values["mcpServers"]["imagehearth"]

        write_json(client.path(), values)

    monkeypatch.setattr(connect, "_run_cli", fake)
    connect.disconnect(client, yes=True)
    assert (["/bin/claude", "mcp", "remove", "--scope", "local", "imageengine"], str(folder)) in calls
    assert (["/bin/claude", "mcp", "remove", "--scope", "user", "imagehearth"], None) in calls


def test_cli_that_leaves_the_entry_falls_back_to_the_file(home, monkeypatch):
    client = connect.CLIENTS["claude-code"]
    write_json(client.path(), {"mcpServers": {"imagehearth": {"command": COMMAND}, "x": {"command": "/x"}}})
    monkeypatch.setattr(connect.shutil, "which", lambda name: "/bin/claude")
    monkeypatch.setattr(connect, "_run_cli", lambda argv, cwd=None: None)
    connect.disconnect(client, yes=True)
    assert read_json(client.path()) == {"mcpServers": {"x": {"command": "/x"}}}


def test_cli_that_fails_falls_back_to_the_file(home, monkeypatch):
    client = connect.CLIENTS["claude-code"]
    write_json(client.path(), {"mcpServers": {"imagehearth": {"command": COMMAND}}})
    monkeypatch.setattr(connect.shutil, "which", lambda name: "/bin/claude")

    def broken(argv, cwd=None):
        raise ProvisionError("boom")

    monkeypatch.setattr(connect, "_run_cli", broken)
    connect.disconnect(client, yes=True)
    assert "mcpServers" not in read_json(client.path())


@pytest.mark.parametrize("name", ["codex", "hermes", "opencode", "pi", "gemini"])
def test_every_format_is_cleaned_without_a_record(home, name):
    client = connect.CLIENTS[name]
    connect_unregistered(client)
    connect.disconnect(client, yes=True)
    text = client.path().read_text(encoding="utf-8")
    assert "imagehearth" not in text
    assert len(backups(client)) >= 1


def test_old_name_in_toml_and_yaml(home):
    codex = connect.CLIENTS["codex"]
    codex.path().parent.mkdir(parents=True)
    codex.path().write_text(
        CODEX_CONFIG + '\n[mcp_servers.imageengine]\ncommand = "/o/imageengine-mcp"\n', encoding="utf-8"
    )
    hermes = connect.CLIENTS["hermes"]
    hermes.path().parent.mkdir(parents=True)
    hermes.path().write_text(
        HERMES_CONFIG.replace("  other:", "  imageengine:\n    command: /o/imageengine-mcp\n  other:"),
        encoding="utf-8",
    )
    connect.disconnect(codex, yes=True)
    connect.disconnect(hermes, yes=True)
    assert tomllib.loads(codex.path().read_text(encoding="utf-8"))["mcp_servers"] == {
        "caveman": {"command": "/bin/caveman"}
    }
    assert set(yaml.safe_load(hermes.path().read_text(encoding="utf-8"))["mcp_servers"]) == {
        "caveman",
        "other",
    }


def test_skills_identical_removed_modified_kept_old_reported(home, capsys):
    client = connect.CLIENTS["hermes"]
    connect_unregistered(client, skill=True)
    skill = client.skills() / "imagehearth"
    assert skill.is_dir()
    old = client.skills() / "imageengine"
    old.mkdir()
    (old / "SKILL.md").write_text("x", encoding="utf-8")
    connect.disconnect(client, yes=True)
    assert not skill.exists()
    assert old.exists()
    assert "Old skill left as it is" in capsys.readouterr().out

    skill.mkdir()
    (skill / "SKILL.md").write_text("mine", encoding="utf-8")
    connect.disconnect(client, yes=True)
    assert (skill / "SKILL.md").read_text(encoding="utf-8") == "mine"
    assert "modified" in capsys.readouterr().out


def test_broken_file_does_not_stop_the_other_agents(home, uninstall_env, capsys):
    cursor = connect.CLIENTS["cursor"]
    connect.connect(cursor, COMMAND, skill=False)
    desktop = connect.CLIENTS["claude-desktop"]
    desktop.path().parent.mkdir(parents=True)
    desktop.path().write_text("{ nope", encoding="utf-8")
    assert maintenance.uninstall(uninstall_env) == 0
    assert "mcpServers" not in read_json(cursor.path())
    assert desktop.path().read_text(encoding="utf-8") == "{ nope"
    assert "Could not check" in capsys.readouterr().out


def test_recorded_file_that_cannot_be_read_fails_uninstall(home, uninstall_env):
    desktop = connect.CLIENTS["claude-desktop"]
    connect.connect(desktop, COMMAND, skill=False)
    desktop.path().write_text("{ nope", encoding="utf-8")
    assert maintenance.uninstall(uninstall_env) == 1


def test_uninstall_finds_entries_without_a_record(home, uninstall_env, capsys):
    client = connect.CLIENTS["cursor"]
    write_json(client.path(), {"mcpServers": {"imageengine": {"command": "/o/imageengine-mcp"}}})
    assert maintenance.uninstall(uninstall_env) == 0
    assert "mcpServers" not in read_json(client.path())
    assert not config.INSTALL_MANIFEST.exists()
    out = capsys.readouterr().out
    assert "Restart the agents" in out
    assert "uv tool uninstall imagehearth-mcp" in out


def test_uninstall_without_record_and_without_entries_does_nothing(home, uninstall_env, capsys):
    assert maintenance.uninstall(uninstall_env) == 0
    assert "No install record found" in capsys.readouterr().out


def test_uninstall_non_interactive_without_yes_lists_the_rest(home, uninstall_env, monkeypatch, capsys):
    registered = connect.CLIENTS["cursor"]
    connect.connect(registered, COMMAND, skill=False)
    stray = connect.CLIENTS["claude-desktop"]
    write_json(stray.path(), {"mcpServers": {"imagehearth": {"command": COMMAND}}})
    monkeypatch.setattr(maintenance.sys, "stdin", mock.Mock(isatty=lambda: False))
    # La confirmación general la da --yes de uninstall; las no registradas, no.
    records = InstallManifest.load(config.INSTALL_MANIFEST)
    report = connect.disconnect_all(records, yes=False, interactive=False)
    assert report.failures == []
    assert [f.agent for f in report.removed] == ["cursor"]
    assert [f.agent for f in report.pending] == ["claude-desktop"]
    assert entry_of(stray)
    connect.print_report(report)
    assert "connect --remove claude-desktop --yes" in capsys.readouterr().out


def test_uninstall_with_yes_removes_the_unregistered_too(home, uninstall_env):
    stray = connect.CLIENTS["claude-desktop"]
    write_json(stray.path(), {"mcpServers": {"imagehearth": {"command": COMMAND}}})
    connect.connect(connect.CLIENTS["cursor"], COMMAND, skill=False)
    assert maintenance.uninstall(uninstall_env) == 0
    assert "mcpServers" not in read_json(stray.path())


def test_uninstall_keeps_foreign_things(home, uninstall_env):
    client = connect.CLIENTS["hermes"]
    connect_unregistered(client, skill=True)
    skill = client.skills() / "imagehearth"
    (skill / "SKILL.md").write_text("edited by me", encoding="utf-8")
    connect.connect(connect.CLIENTS["cursor"], COMMAND, skill=False)
    cursor = connect.CLIENTS["cursor"]
    write_json(cursor.path(), {"mcpServers": {"imagehearth": {"command": "/bin/other-tool"}}})
    assert maintenance.uninstall(uninstall_env) == 0
    assert (skill / "SKILL.md").read_text(encoding="utf-8") == "edited by me"
    assert entry_of(cursor) == {"command": "/bin/other-tool"}


def test_connect_remove_clears_the_record(home):
    client = connect.CLIENTS["cursor"]
    connect.connect(client, COMMAND, skill=False)
    connect.disconnect(client)
    assert InstallManifest.load(config.INSTALL_MANIFEST).connections == []
