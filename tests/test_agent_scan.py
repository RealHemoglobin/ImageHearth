"""Búsqueda de entradas y skills de ImageHearth en agentes, sobre carpetas temporales."""

import json

import pytest

from imagehearth_mcp.engine import config
from imagehearth_mcp.provisioner import agent_scan, connect
from imagehearth_mcp.provisioner.install_manifest import InstallManifest

COMMAND = "/opt/bin/imagehearth-mcp"


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(connect.Path, "home", lambda: tmp_path)

    for name in ("XDG_CONFIG_HOME", "CODEX_HOME", "HERMES_HOME"):
        monkeypatch.delenv(name, raising=False)

    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData" / "Roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData" / "Local"))
    monkeypatch.setattr(connect.shutil, "which", lambda name: None)
    monkeypatch.setattr(config, "INSTALL_MANIFEST", tmp_path / "data" / "install.json")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    return tmp_path


def claude_json(home, **values):
    path = home / ".claude.json"
    path.write_text(json.dumps(values), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        (["/opt/bin/imagehearth-mcp"], True),
        (["imagehearth-mcp"], True),
        (["/opt/bin/imageengine-mcp"], True),
        (["C:\\Users\\a\\.local\\bin\\imagehearth-mcp.exe"], True),
        (["/usr/bin/uvx", "imagehearth-mcp"], False),
        (["/bin/caveman"], False),
        ([None], False),
        (None, False),
    ],
)
def test_is_ours(command, expected):
    assert agent_scan.is_ours(command) is expected


def test_windows_names_ignore_case(monkeypatch):
    monkeypatch.setattr(agent_scan.sys, "platform", "win32")
    assert agent_scan.is_ours(["C:\\Tools\\ImageHearth-MCP.EXE"])


def test_claude_code_scopes(home):
    project = home / "work"
    project.mkdir()
    (project / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"imagehearth": {"command": COMMAND}}}), encoding="utf-8"
    )
    claude_json(
        home,
        mcpServers={"imagehearth": {"command": COMMAND}, "other": {"command": "/x"}},
        projects={
            str(project): {"mcpServers": {"imageengine": {"command": "/old/imageengine-mcp"}}},
            str(home / "gone"): {"mcpServers": {}},
        },
    )
    found = agent_scan.scan(clients=[connect.CLIENTS["claude-code"]])
    scopes = {(f.scope, f.name): f for f in found.entries}
    assert set(scopes) == {("user", "imagehearth"), ("local", "imageengine"), ("project", "imagehearth")}
    assert scopes[("local", "imageengine")].project == str(project)
    assert scopes[("project", "imagehearth")].editable is False
    assert all(f.ours for f in found.entries)


def test_registered_depends_on_the_record(home):
    client = connect.CLIENTS["cursor"]
    connect.connect(client, COMMAND, skill=False)
    assert agent_scan.scan(clients=[client]).entries[0].registered is False
    records = InstallManifest.load(config.INSTALL_MANIFEST)
    assert agent_scan.scan(records, [client]).entries[0].registered is True


def test_foreign_command_is_not_ours(home):
    client = connect.CLIENTS["cursor"]
    client.path().parent.mkdir(parents=True)
    client.path().write_text(
        json.dumps({"mcpServers": {"imagehearth": {"command": "/bin/other"}}}), encoding="utf-8"
    )
    [finding] = agent_scan.scan(clients=[client]).entries
    assert not finding.ours
    assert finding.command == ["/bin/other"]


def test_orphans_missing_executable_and_duplicates(home, tmp_path):
    real = tmp_path / "imagehearth-mcp"
    real.write_text("", encoding="utf-8")
    claude_json(
        home,
        mcpServers={
            "imagehearth": {"command": str(real)},
            "imageengine": {"command": str(tmp_path / "gone" / "imageengine-mcp")},
        },
    )
    found = agent_scan.scan(clients=[connect.CLIENTS["claude-code"]])
    by_name = {f.name: f for f in found.entries}
    assert by_name["imagehearth"].orphan is False
    assert by_name["imageengine"].orphan is True

    real_two = tmp_path / "imageengine-mcp"
    real_two.write_text("", encoding="utf-8")
    claude_json(
        home,
        mcpServers={
            "imagehearth": {"command": str(real)},
            "imageengine": {"command": str(real_two)},
        },
    )
    found = agent_scan.scan(clients=[connect.CLIENTS["claude-code"]])
    assert [f.orphan for f in found.entries] == [False, True]
    assert "second" in found.entries[1].reason


@pytest.mark.parametrize("name", ["codex", "hermes", "opencode", "pi", "gemini"])
def test_other_formats_are_found(home, name):
    client = connect.CLIENTS[name]
    connect.connect(client, COMMAND, skill=False)
    [finding] = agent_scan.scan(clients=[client]).entries
    assert (finding.agent, finding.name, finding.ours) == (name, "imagehearth", True)
    assert finding.command[0] == COMMAND


def test_skill_states(home):
    client = connect.CLIENTS["hermes"]
    skill = client.skills() / "imagehearth"

    def state():
        found = agent_scan.scan(
            InstallManifest.load(config.INSTALL_MANIFEST), [client]
        ).skills
        return next(s.state for s in found if s.name == "imagehearth")

    assert state() == agent_scan.ABSENT
    connect.connect(client, COMMAND)
    assert state() == agent_scan.OWNED
    records = InstallManifest.load(config.INSTALL_MANIFEST)
    records.forget(skill)
    records.save()
    assert state() == agent_scan.IDENTICAL
    (skill / "SKILL.md").write_text("mine", encoding="utf-8")
    assert state() == agent_scan.MODIFIED


def test_old_skill_is_only_reported(home):
    client = connect.CLIENTS["hermes"]
    old = client.skills() / "imageengine"
    old.mkdir(parents=True)
    (old / "SKILL.md").write_text("x", encoding="utf-8")
    skills = agent_scan.scan(clients=[client]).skills
    assert [(s.name, s.state) for s in skills] == [
        ("imagehearth", agent_scan.ABSENT),
        ("imageengine", agent_scan.MODIFIED),
    ]


def test_broken_file_is_reported_and_the_rest_scanned(home):
    broken = connect.CLIENTS["claude-desktop"]
    broken.path().parent.mkdir(parents=True)
    broken.path().write_text("{ not json", encoding="utf-8")
    connect.connect(connect.CLIENTS["cursor"], COMMAND, skill=False)
    found = agent_scan.scan()
    assert [e[0] for e in found.errors] == ["claude-desktop"]
    assert [f.agent for f in found.entries] == ["cursor"]


def test_scan_writes_nothing(home):
    claude_json(home, mcpServers={"imagehearth": {"command": COMMAND}})
    before = sorted(p.name for p in home.rglob("*"))
    agent_scan.scan()
    assert sorted(p.name for p in home.rglob("*")) == before


# doctor


def test_doctor_agents_layer_lists_entries_and_orphans(home, capsys):
    from imagehearth_mcp.provisioner import doctor

    claude_json(
        home,
        mcpServers={"imagehearth": {"command": str(home / "gone" / "imagehearth-mcp")}},
        projects={str(home / "p"): {"mcpServers": {"imageengine": {"command": "/x/imageengine-mcp"}}}},
    )
    connect.connect(connect.CLIENTS["cursor"], COMMAND, skill=False)
    records = InstallManifest.load(config.INSTALL_MANIFEST)
    before = sorted(str(p) for p in home.rglob("*"))
    check = doctor.check_agents(records)
    assert check.layer == "agents"
    assert check.status == doctor.WARN
    assert "connect --remove claude-code" in check.fix
    by_key = {(e["agent"], e["scope"], e["name"]): e for e in check.details["entries"]}
    assert by_key[("claude-code", "user", "imagehearth")]["orphan"] is True
    assert by_key[("claude-code", "local", "imageengine")]["project"] == str(home / "p")
    assert by_key[("cursor", "file", "imagehearth")]["registered"] is True
    json.dumps(doctor.to_json([check]))
    assert sorted(str(p) for p in home.rglob("*")) == before

    lines = doctor._agent_lines(check)
    assert any("ORPHAN" in line for line in lines)
    assert any("registered" in line and "cursor" in line for line in lines)


def test_doctor_agents_layer_is_ok_with_nothing(home):
    from imagehearth_mcp.provisioner import doctor

    check = doctor.check_agents(InstallManifest(config.INSTALL_MANIFEST))
    assert check.status == doctor.OK
    assert check.details["entries"] == []


def test_doctor_agents_layer_reports_unreadable_files(home):
    from imagehearth_mcp.provisioner import doctor

    desktop = connect.CLIENTS["claude-desktop"]
    desktop.path().parent.mkdir(parents=True)
    desktop.path().write_text("{ nope", encoding="utf-8")
    check = doctor.check_agents(InstallManifest(config.INSTALL_MANIFEST))
    assert check.status == doctor.WARN
    assert check.details["errors"][0]["agent"] == "claude-desktop"
