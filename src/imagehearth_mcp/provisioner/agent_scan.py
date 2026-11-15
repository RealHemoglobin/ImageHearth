"""Búsqueda de lo que ImageHearth ha dejado en los agentes: entradas MCP y skills.

Solo lee. Encuentra las entradas `imagehearth` e `imageengine` de cada cliente
conocido (en Claude Code, en cada ámbito) y las skills, y las clasifica. Quitarlas
es cosa de `connect.py`, que conserva la escritura y las copias de seguridad.
"""

import json
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from imagehearth_mcp.provisioner import ProvisionError, connect

NAMES = ("imagehearth", "imageengine")
EXECUTABLES = ("imagehearth-mcp", "imageengine-mcp")
USER, LOCAL, PROJECT, FILE = "user", "local", "project", "file"
OWNED, IDENTICAL, MODIFIED, ABSENT = "owned", "identical", "modified", "absent"
CLAUDE_CODE = "claude-code"
CLAUDE_CODE_KEY = "mcpServers"
PROJECT_FILE = ".mcp.json"


@dataclass
class Finding:
    agent: str
    scope: str
    file: Path
    name: str
    command: object = None
    project: object = None
    ours: bool = False
    registered: bool = False
    exists: bool = True
    editable: bool = True
    orphan: bool = False
    reason: str = ""
    error: str = ""

    @property
    def command_text(self):
        return " ".join(str(part) for part in self.command or () if part) or "(none)"


@dataclass
class SkillFinding:
    agent: str
    path: Path
    name: str
    state: str


@dataclass
class Scan:
    entries: list = field(default_factory=list)
    skills: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    @property
    def empty(self):
        return not self.entries and not [s for s in self.skills if s.state != ABSENT]


def executable_name(command):
    """Nombre normalizado del ejecutable: sin carpeta, sin `.exe` y sin mayúsculas en Windows."""
    if not command or not isinstance(command[0], str):
        return ""

    name = command[0].replace("\\", "/").rsplit("/", 1)[-1]

    if name.lower().endswith(".exe"):
        name = name[:-4]

    return name.lower() if sys.platform == "win32" else name


def is_ours(command):
    """Es nuestra si el ejecutable es `imagehearth-mcp` o `imageengine-mcp`, esté donde esté."""
    return executable_name(command) in EXECUTABLES


def _executable_exists(command):
    if not command or not isinstance(command[0], str) or not command[0]:
        return False

    program = command[0]
    return Path(program).exists() if Path(program).is_absolute() else bool(shutil.which(program))


def _finding(client, scope, file, name, entry, project=None, records=None):
    command = connect._command_of(entry)
    ours = is_ours(command)
    registered = False

    if records is not None and ours and scope in (USER, FILE):
        registered = any(
            c["client"] == client.name and Path(c["path"]) == file for c in records.connections
        )

    return Finding(
        agent=client.name,
        scope=scope,
        file=file,
        name=name,
        command=command,
        project=project,
        ours=ours,
        registered=registered,
        exists=_executable_exists(command) if ours else True,
        editable=scope != PROJECT,
    )


def _named(section):
    if not isinstance(section, dict):
        return {}

    return {name: section[name] for name in NAMES if name in section}


def _project_servers(values):
    """(carpeta, mcpServers) de cada proyecto que `~/.claude.json` conoce."""
    projects = values.get("projects")

    if not isinstance(projects, dict):
        return

    for folder, settings in projects.items():
        if isinstance(settings, dict):
            yield folder, settings.get(CLAUDE_CODE_KEY)


def _scan_client(client, records, scan):
    path = client.path()

    try:
        _, values = connect._read_config(client, path)
    except ProvisionError as error:
        scan.errors.append((client.name, path, str(error)))
        return

    scope = USER if client.name == CLAUDE_CODE else FILE

    for name, entry in _named(values.get(client.key)).items():
        scan.entries.append(_finding(client, scope, path, name, entry, records=records))

    if client.name != CLAUDE_CODE:
        return

    for folder, section in _project_servers(values):
        for name, entry in _named(section).items():
            scan.entries.append(
                _finding(client, LOCAL, path, name, entry, project=folder, records=records)
            )

        _scan_project_file(client, folder, scan)


def _scan_project_file(client, folder, scan):
    path = Path(folder) / PROJECT_FILE

    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return
    except (OSError, UnicodeError) as error:
        scan.errors.append((client.name, path, f"Can't read {path}: {error}."))
        return

    try:
        values = json.loads(text) if text.strip() else {}
    except ValueError as error:
        scan.errors.append((client.name, path, f"{path} is not valid JSON: {error}."))
        return

    section = values.get(CLAUDE_CODE_KEY) if isinstance(values, dict) else None

    for name, entry in _named(section).items():
        scan.entries.append(_finding(client, PROJECT, path, name, entry, project=folder))


def _skill_state(target, records):
    if not (target.exists() or target.is_symlink()):
        return ABSENT

    if records is not None and records.is_owned(target):
        return OWNED

    try:
        same = (target / "SKILL.md").read_bytes() == (connect._skill_source() / "SKILL.md").read_bytes()
    except OSError:
        same = False

    return IDENTICAL if same else MODIFIED


def _scan_skills(client, records, scan):
    folder = client.skills()
    scan.skills.append(
        SkillFinding(client.name, folder / "imagehearth", "imagehearth", _skill_state(folder / "imagehearth", records))
    )
    legacy = folder / "imageengine"

    if legacy.exists() or legacy.is_symlink():
        scan.skills.append(SkillFinding(client.name, legacy, "imageengine", MODIFIED))


def _mark_orphans(scan):
    seen = {}

    for finding in scan.entries:
        if not finding.ours:
            continue

        if not finding.exists:
            finding.orphan, finding.reason = True, "its executable no longer exists"
        elif finding.agent in seen:
            finding.orphan, finding.reason = True, "a second ImageHearth entry in this agent"

        seen.setdefault(finding.agent, finding)


def scan(records=None, clients=None):
    """Hallazgos en los clientes dados (por defecto, todos los que tienen archivo)."""
    result = Scan()

    for client in clients or connect.CLIENTS.values():
        if client.path is not None:
            _scan_client(client, records, result)

        if client.skills is not None:
            _scan_skills(client, records, result)

    _mark_orphans(result)
    return result


def current_entry(finding):
    """La entrada tal como está ahora en su archivo, o None si ya no está."""
    client = connect.CLIENTS[finding.agent]

    try:
        if finding.scope == PROJECT:
            values = json.loads(finding.file.read_text(encoding="utf-8"))
            return _named(values.get(CLAUDE_CODE_KEY)).get(finding.name)

        _, values = connect._read_config(client, finding.file)
    except (OSError, ValueError, ProvisionError):
        return None

    if finding.scope == LOCAL:
        section = dict(_project_servers(values)).get(finding.project)
    else:
        section = values.get(client.key)

    return _named(section).get(finding.name)


def describe(finding):
    place = f"{finding.agent} ({finding.scope}"
    place += f", {finding.project})" if finding.project else ")"
    return f"{place}: {finding.name} in {finding.file} runs {finding.command_text}"
