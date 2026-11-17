"""Subcomando `connect`: añade el servidor MCP a la configuración de cada cliente.

Un descriptor por cliente. Se usa su CLI oficial si es no interactiva; si no, se
edita su archivo. Editar nunca toca el resto: JSON se conserva por contenido, y
TOML y YAML por texto, comprobando después que lo ajeno sigue igual.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from platformdirs import user_config_path

from imagehearth_mcp.engine import config
from imagehearth_mcp.platform import files
from imagehearth_mcp.provisioner import ProvisionError, agent_scan, menu
from imagehearth_mcp.provisioner.install_manifest import InstallManifest

SERVER_NAME = "imagehearth"
EXECUTABLE = "imagehearth-mcp"
CLI_TIMEOUT = 60
# Igual que el mayor plazo del motor (IMAGEHEARTH_LOCK_TIMEOUT).
TOOL_TIMEOUT = 1800
TESTED = "tested"
UNTESTED = "untested"


@dataclass(frozen=True)
class Client:
    name: str
    label: str
    level: str
    format: str
    key: str
    binary: str = ""
    path: object = None
    entry: object = None
    add: object = None
    remove: object = None
    skills: object = None
    note: str = ""


def _plain_entry(command):
    return {"command": command}


def _pi_entry(command):
    # Con su exposición por defecto (codemode), un modelo de 9B no encontró la herramienta.
    return {"command": command, "exposure": "direct"}


def _codex_entry(command):
    # Sin esto, Codex corta la llamada a los 300 s aunque haya progreso.
    return {"command": command, "tool_timeout_sec": TOOL_TIMEOUT}


def _hermes_entry(command):
    # Hermes también corta a los 300 s por defecto.
    return {"command": command, "timeout": TOOL_TIMEOUT}


def _typed_entry(command):
    return {"type": "stdio", "command": command}


def _opencode_entry(command):
    return {"type": "local", "command": [command], "enabled": True}


def _xdg_config():
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")


def _home_dir(variable, default):
    return Path(os.environ.get(variable) or Path.home() / default)


def _editor_config(*parts):
    """Carpeta de usuario de una aplicación de escritorio, en cada sistema."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / Path(*parts)

    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA") or user_config_path()) / Path(*parts)

    return _xdg_config() / Path(*parts)


def _claude_desktop_config():
    """Dónde lee Claude Desktop su config en Windows.

    Las versiones recientes la guardan en %LOCALAPPDATA%\\Claude-Data\\claude_<id>; las anteriores
    de la Microsoft Store, en la carpeta del paquete, porque Windows redirige %APPDATA%.
    """
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")

        data = Path(local) / "Claude-Data" if local else None

        if data is not None and data.is_dir():
            for folder in sorted(data.glob("claude_*")):
                if folder.is_dir():
                    return folder / "claude_desktop_config.json"

        packages = Path(local) / "Packages" if local else None

        if packages is not None and packages.is_dir():
            for package in sorted(packages.glob("Claude_*")):
                return package / "LocalCache" / "Roaming" / "Claude" / "claude_desktop_config.json"

    return _editor_config("Claude", "claude_desktop_config.json")


CLIENTS = {
    client.name: client
    for client in (
        Client(
            "claude-code",
            "Claude Code",
            TESTED,
            "json",
            "mcpServers",
            "claude",
            lambda: Path.home() / ".claude.json",
            _plain_entry,
            lambda exe, cmd: [exe, "mcp", "add", "--scope", "user", SERVER_NAME, "--", cmd],
            lambda exe, name=SERVER_NAME, scope="user": [exe, "mcp", "remove", "--scope", scope, name],
            lambda: Path.home() / ".claude" / "skills",
        ),
        Client(
            "claude-desktop",
            "Claude Desktop",
            UNTESTED,
            "json",
            "mcpServers",
            path=_claude_desktop_config,
            entry=_plain_entry,
        ),
        Client(
            "codex",
            "Codex",
            TESTED,
            "toml",
            "mcp_servers",
            "codex",
            lambda: _home_dir("CODEX_HOME", ".codex") / "config.toml",
            _codex_entry,
            skills=lambda: _home_dir("CODEX_HOME", ".codex") / "skills",
        ),
        Client(
            "gemini",
            "Gemini CLI",
            UNTESTED,
            "json",
            "mcpServers",
            "gemini",
            lambda: Path.home() / ".gemini" / "settings.json",
            _plain_entry,
            lambda exe, cmd: [exe, "mcp", "add", "--scope", "user", SERVER_NAME, cmd],
            lambda exe, name=SERVER_NAME, scope="user": [exe, "mcp", "remove", "--scope", "user", name],
        ),
        # `codex mcp add` no fija el plazo; `opencode mcp add` y `hermes mcp add`
        # preguntan: se edita el archivo.
        # `code --add-mcp` abre el editor: en VS Code también.
        Client(
            "opencode",
            "opencode",
            TESTED,
            "json",
            "mcp",
            "opencode",
            lambda: _xdg_config() / "opencode" / "opencode.json",
            _opencode_entry,
            skills=lambda: _xdg_config() / "opencode" / "skills",
        ),
        Client(
            "hermes",
            "Hermes",
            TESTED,
            "yaml",
            "mcp_servers",
            "hermes",
            lambda: _home_dir("HERMES_HOME", ".hermes") / "config.yaml",
            _hermes_entry,
            skills=lambda: _home_dir("HERMES_HOME", ".hermes") / "skills",
        ),
        Client(
            "pi",
            "pi",
            TESTED,
            "json",
            "mcpServers",
            "pi",
            lambda: Path.home() / ".pi" / "agent" / "mcp.json",
            _pi_entry,
            lambda exe, cmd: [exe, "mcp", "add", SERVER_NAME, "--exposure", "direct", "--", cmd],
            lambda exe, name=SERVER_NAME, scope="user": [exe, "mcp", "remove", name],
            lambda: Path.home() / ".pi" / "agent" / "skills",
        ),
        Client(
            "vscode",
            "VS Code",
            UNTESTED,
            "json",
            "servers",
            "code",
            lambda: _editor_config("Code", "User", "mcp.json"),
            _typed_entry,
        ),
        Client(
            "cursor",
            "Cursor",
            UNTESTED,
            "json",
            "mcpServers",
            "cursor",
            lambda: Path.home() / ".cursor" / "mcp.json",
            _typed_entry,
        ),
        Client(
            "jetbrains",
            "IntelliJ and other JetBrains IDEs",
            UNTESTED,
            "json",
            "mcpServers",
            entry=_plain_entry,
            note="JetBrains keeps this in its settings: open Settings | Tools | AI "
            "Assistant | Model Context Protocol (MCP), choose Add and paste the snippet.",
        ),
    )
}


def get_client(name):
    client = CLIENTS.get(name)

    if client is None:
        raise ProvisionError(
            f"Unknown client {name!r}. Known clients: {', '.join(CLIENTS)}. For any "
            "other client, adapt the output of `connect --print claude-desktop`."
        )

    return client


def server_command():
    """Ruta absoluta del ejecutable: no depende del PATH de una aplicación gráfica."""
    found = shutil.which(EXECUTABLE)
    sibling = Path(sys.executable).parent / EXECUTABLE

    if sibling.exists():
        found = str(sibling)

    if not found:
        raise ProvisionError(
            f"Can't find the {EXECUTABLE} executable. Install it with "
            "`uv tool install imagehearth-mcp`."
        )

    return str(Path(found).absolute())


def _toml_value(value):
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"

    return json.dumps(value)


def _toml_block(key, entry):
    lines = [f"[{key}.{SERVER_NAME}]"]
    lines += [f"{name} = {_toml_value(value)}" for name, value in entry.items()]
    return "\n".join(lines) + "\n"


def _yaml_block(key, entry):
    return yaml.safe_dump({key: {SERVER_NAME: entry}}, sort_keys=False)


def snippet(client, command):
    """El fragmento que pegar en la configuración del cliente."""
    entry = client.entry(command)

    if client.format == "toml":
        return _toml_block(client.key, entry)

    if client.format == "yaml":
        return _yaml_block(client.key, entry)

    return json.dumps({client.key: {SERVER_NAME: entry}}, indent=2) + "\n"


def _parse(client, text):
    if client.format == "toml":
        return tomllib.loads(text)

    if client.format == "yaml":
        return yaml.safe_load(text) or {}

    return json.loads(text) if text.strip() else {}


def _read_config(client, path):
    """(texto, valores) del archivo. Uno ilegible no se toca."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return "", {}
    except (OSError, UnicodeError) as error:
        raise ProvisionError(f"Can't read {path}: {error}. Nothing was changed.") from error

    try:
        values = _parse(client, text)
    except (ValueError, yaml.YAMLError) as error:
        raise ProvisionError(
            f"{path} is not valid {client.format.upper()}, so it was not touched: {error}. "
            f"Fix it, or add the entry by hand with `connect --print {client.name}`."
        ) from error

    if not isinstance(values, dict) or not isinstance(values.get(client.key, {}), dict):
        raise ProvisionError(
            f"{path} has an unexpected structure, so it was not touched. "
            f"Add the entry by hand with `connect --print {client.name}`."
        )

    return text, values


def _command_of(entry):
    """Línea de comandos de una entrada, sea cual sea el formato del cliente."""
    if not isinstance(entry, dict):
        return None

    command = entry.get("command")

    if isinstance(command, list):
        return command

    return [command, *(entry.get("args") or [])]


def _backup(path):
    if not path.exists():
        return None

    backup = path.with_name(f"{path.name}.imagehearth-{time.strftime('%Y%m%d-%H%M%S')}.bak")
    number = 1

    while backup.exists():
        backup = backup.with_name(f"{backup.name}.{number}")
        number += 1

    shutil.copy2(path, backup)
    return backup


def _write(path, text):
    """Escritura atómica que conserva los permisos: estos archivos guardan secretos."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.imagehearth.tmp")
    temporary.write_text(text, encoding="utf-8")

    if path.exists():
        shutil.copymode(path, temporary)

    files.replace(temporary, path)


def _without_server(client, values, name=SERVER_NAME):
    """Copia de los valores sin nuestra entrada, y sin su sección si queda vacía."""
    result = dict(values)
    section = dict(result.get(client.key, {}))
    section.pop(name, None)
    result[client.key] = section

    if not section:
        result.pop(client.key)

    return result


def _strip_toml(client, text, name=SERVER_NAME):
    header = re.compile(
        rf"^\s*\[+\s*{re.escape(client.key)}\.{re.escape(name)}\s*[\].]", re.MULTILINE
    )
    any_table = re.compile(r"^\s*\[", re.MULTILINE)

    while match := header.search(text):
        following = any_table.search(text, match.end())
        end = following.start() if following else len(text)
        # Un comentario justo antes de la tabla siguiente es de esa tabla.
        block = text[match.start() : end]
        kept = re.search(r"(?:^[ \t]*(?:#.*)?\n)+\Z", block, re.MULTILINE)
        text = text[: match.start()] + (kept.group(0) if kept else "") + text[end:]

        if not header.search(text):
            break

    return text


def _strip_yaml(client, text, name=SERVER_NAME):
    lines = text.splitlines(keepends=True)
    result = []
    inside_section = False
    skipping = False
    indent = 0

    for line in lines:
        stripped = line.strip()
        current = len(line) - len(line.lstrip())
        code = bool(stripped) and not stripped.startswith("#")

        if code and current == 0:
            inside_section = line.startswith(f"{client.key}:")
            skipping = False

        if skipping and code and current <= indent:
            skipping = False

        own_entry = re.match(rf"['\"]?{re.escape(name)}['\"]?\s*:", stripped)

        if inside_section and code and not skipping and current > 0 and own_entry:
            skipping = True
            indent = current

        if not skipping:
            result.append(line)

    return "".join(result)


def _empty_yaml_section(client, text):
    """`clave:` sin nada debajo vale null: se quita al dejarla vacía."""
    values = yaml.safe_load(text) or {}

    if client.key in values and values[client.key] is None:
        return re.sub(rf"^{re.escape(client.key)}:[ \t]*\n", "", text, count=1, flags=re.MULTILINE)

    return text


def _add_yaml(client, text, entry):
    block = yaml.safe_dump({SERVER_NAME: entry}, sort_keys=False)
    block = "".join(f"  {line}\n" for line in block.splitlines())
    section = re.search(rf"^{re.escape(client.key)}:[ \t]*(\{{\}})?[ \t]*\n", text, re.MULTILINE)

    if section:
        return f"{text[: section.start()]}{client.key}:\n{block}{text[section.end() :]}"

    if text and not text.endswith("\n"):
        text += "\n"

    return f"{text}{client.key}:\n{block}"


def _edit_text(client, text, entry):
    """Texto con la entrada; None si se añade por contenido y no por texto."""
    if client.format == "toml":
        stripped = _strip_toml(client, text)
        separator = "" if not stripped or stripped.endswith("\n\n") else "\n"

        if stripped and not stripped.endswith("\n"):
            separator = "\n\n"

        return f"{stripped}{separator}{_toml_block(client.key, entry)}"

    if client.format == "yaml":
        return _add_yaml(client, _empty_yaml_section(client, _strip_yaml(client, text)), entry)

    values = json.loads(text) if text.strip() else {}
    values.setdefault(client.key, {})[SERVER_NAME] = entry
    return json.dumps(values, indent=2, ensure_ascii=False) + "\n"


def _remove_text(client, text, name=SERVER_NAME):
    if client.format == "toml":
        return _strip_toml(client, text, name)

    if client.format == "yaml":
        return _empty_yaml_section(client, _strip_yaml(client, text, name))

    values = _without_server(client, json.loads(text), name)
    return json.dumps(values, indent=2, ensure_ascii=False) + "\n"


def _checked(client, path, before, new_text, entry):
    """Comprueba antes de escribir que solo cambia nuestra entrada."""
    after = _parse(client, new_text)

    if _without_server(client, after) != _without_server(client, before) or (
        (after.get(client.key) or {}).get(SERVER_NAME) != entry
    ):
        raise ProvisionError(
            f"Editing {path} safely isn't possible with its current layout, so it was "
            f"not touched. Add the entry by hand with `connect --print {client.name}`."
        )

    return new_text


def _run_cli(argv, cwd=None):
    try:
        result = subprocess.run(
            argv,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=CLI_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ProvisionError(f"`{' '.join(argv)}` failed: {error}") from error

    if result.returncode != 0:
        raise ProvisionError(
            f"`{' '.join(argv)}` failed: {(result.stderr or result.stdout).strip()}"
        )


def _official_cli(client):
    return shutil.which(client.binary) if client.binary and client.add else None


def _skill_source():
    return config.data_path("skill")


def _install_skill(client, records):
    """Copia la skill; una carpeta que ya existe y no es propia no se toca."""
    if client.skills is None:
        return None

    target = client.skills() / SERVER_NAME

    if (target.exists() or target.is_symlink()) and not records.is_owned(target):
        print(f"Skill left as it is: {target} already exists.")
        return None

    records.claim_verified("skill", target)

    if target.exists():
        shutil.rmtree(target)

    shutil.copytree(_skill_source(), target, ignore=shutil.ignore_patterns("__pycache__"))
    print(f"Skill installed in {target}.")
    return str(target)


def _record(records, client, path, command, method):
    records.connections = [c for c in records.connections if c["client"] != client.name]
    records.connections.append(
        {"client": client.name, "path": str(path), "command": command, "method": method}
    )
    records.save()


def connect(client, command, skill=True, records=None):
    records = records or InstallManifest.load(config.INSTALL_MANIFEST)

    if client.path is None:
        print(snippet(client, command))
        print(client.note)
        return False

    path = client.path()
    text, values = _read_config(client, path)
    current = (values.get(client.key) or {}).get(SERVER_NAME)
    entry = client.entry(command)
    cli = _official_cli(client)
    method = "cli" if cli else "file"

    if isinstance(current, dict) and entry.items() <= current.items():
        print(f"{client.label} is already connected ({path}).")
    else:
        backup = _backup(path)

        if backup:
            print(f"Backup: {backup}")

        if cli:
            if current is not None:
                _run_cli(client.remove(cli))

            _run_cli(client.add(cli, command))
            _, values = _read_config(client, path)

            if _command_of((values.get(client.key) or {}).get(SERVER_NAME)) != [command]:
                raise ProvisionError(
                    f"`{client.binary}` reported success, but the entry is not in {path}. "
                    f"Add it by hand with `connect --print {client.name}`."
                )
        else:
            _write(path, _checked(client, path, values, _edit_text(client, text, entry), entry))

        print(f"Connected {client.label} ({path}). Restart it to load the tools.")

    _record(records, client, path, command, method)

    if skill:
        _install_skill(client, records)

    if client.level == UNTESTED:
        print(f"Note: {client.label} has been checked against its documentation only.")

    return True


def _remove_local(finding):
    """Quita `projects.<ruta>.mcpServers.<nombre>` de `~/.claude.json` y deja el resto."""
    text = finding.file.read_text(encoding="utf-8")
    values = json.loads(text)
    del values["projects"][finding.project]["mcpServers"][finding.name]
    _write(finding.file, json.dumps(values, indent=2, ensure_ascii=False) + "\n")


def _retire(finding):
    """Retira una entrada nuestra y editable. Con CLI oficial primero, con el archivo de reserva."""
    client = CLIENTS[finding.agent]
    backup = _backup(finding.file)

    if backup:
        print(f"Backup: {backup}")

    cli = _official_cli(client)

    if cli and client.remove and finding.scope in (agent_scan.USER, agent_scan.LOCAL, agent_scan.FILE):
        cwd = finding.project if finding.scope == agent_scan.LOCAL else None

        try:
            _run_cli(client.remove(cli, finding.name, finding.scope), cwd)
        except ProvisionError:
            pass

    if agent_scan.current_entry(finding) is not None:
        if finding.scope == agent_scan.LOCAL:
            _remove_local(finding)
        else:
            text, _ = _read_config(client, finding.file)
            _write(finding.file, _remove_text(client, text, finding.name))

    if agent_scan.current_entry(finding) is not None:
        raise ProvisionError(f"the entry {finding.name} is still in {finding.file}")


def _remove_skill_folder(skill, records):
    if skill.path.is_symlink():
        skill.path.unlink()
    else:
        shutil.rmtree(skill.path, ignore_errors=True)

    if records.entry(skill.path):
        records.forget(skill.path)
        records.save()


@dataclass
class Report:
    removed: list = field(default_factory=list)
    pending: list = field(default_factory=list)
    foreign: list = field(default_factory=list)
    project: list = field(default_factory=list)
    skills_removed: list = field(default_factory=list)
    skills_kept: list = field(default_factory=list)
    skills_legacy: list = field(default_factory=list)
    failures: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


def _confirm_unregistered(others, yes, interactive, report):
    """Las entradas que `connect` no registró: se retiran con --yes o tras preguntar."""
    if not others:
        return []

    if yes:
        return others

    if interactive:
        print("ImageHearth entries that connect did not register:")

        for finding in others:
            print(f"  {agent_scan.describe(finding)}")

        if menu.confirm("Remove them?"):
            return others

    report.pending = others
    return []


def _drop_connections(records, found_clients, blocked):
    dropped = [
        c
        for c in records.connections
        if c["client"] in found_clients and (c["client"], Path(c["path"])) not in blocked
    ]

    for connection in dropped:
        records.connections.remove(connection)

    if dropped:
        records.save()


def _disconnect(clients, records, yes, interactive):
    found = agent_scan.scan(records, clients)
    report = Report()
    recorded = {(c["client"], Path(c["path"])) for c in records.connections}

    for agent, path, message in found.errors:
        if (agent, path) in recorded:
            report.failures.append(f"{path}: {message}")
        else:
            report.warnings.append(message)

    report.foreign = [f for f in found.entries if not f.ours]
    report.project = [f for f in found.entries if f.ours and not f.editable]
    ours = [f for f in found.entries if f.ours and f.editable]
    registered = [f for f in ours if f.registered]
    chosen = registered + _confirm_unregistered(
        [f for f in ours if not f.registered], yes, interactive, report
    )
    blocked = {(f.agent, f.file) for f in report.pending}

    for finding in chosen:
        try:
            _retire(finding)
        except (OSError, ProvisionError, ValueError, KeyError) as error:
            report.failures.append(f"{finding.file}: {error}")
            blocked.add((finding.agent, finding.file))
        else:
            report.removed.append(finding)
            print(f"Removed ImageHearth from {agent_scan.describe(finding)}.")

    for skill in found.skills:
        if skill.state in (agent_scan.OWNED, agent_scan.IDENTICAL):
            _remove_skill_folder(skill, records)
            report.skills_removed.append(skill)
        elif skill.state == agent_scan.MODIFIED:
            (report.skills_legacy if skill.name != SERVER_NAME else report.skills_kept).append(
                skill
            )

    _drop_connections(records, {c.name for c in clients}, blocked | {(a, p) for a, p, _ in found.errors})
    return report


def print_report(report):
    """Lo que no se retiró y por qué, con la orden para hacerlo, y el aviso de reinicio."""
    for finding in report.foreign:
        print(
            f"Left as it is: {finding.name} in {finding.file} ({finding.agent}) runs "
            f"{finding.command_text}, which is not ImageHearth."
        )

    for finding in report.project:
        print(
            f"Not edited: {finding.file} is part of a project and may be versioned. "
            f"In {finding.project} run `claude mcp remove --scope project {finding.name}`."
        )

    for skill in report.skills_kept:
        print(f"Skill left as it is: {skill.path} was modified. Delete it yourself if you want.")

    for skill in report.skills_legacy:
        print(f"Old skill left as it is: {skill.path}. Delete it yourself if you want.")

    for message in report.warnings:
        print(f"Could not check: {message}")

    for agent in sorted({f.agent for f in report.pending}):
        entries = [f for f in report.pending if f.agent == agent]

        for finding in entries:
            print(f"Not removed (connect did not register it): {agent_scan.describe(finding)}.")

        print(f"  To remove them: imagehearth-mcp connect --remove {agent} --yes")

    if report.removed or report.skills_removed:
        print("Restart the agents you have open so they stop loading ImageHearth.")


def disconnect(client, records=None, yes=False, interactive=None):
    records = records or InstallManifest.load(config.INSTALL_MANIFEST)

    if client.path is None:
        print(client.note.replace("choose Add and paste the snippet", "and remove it there"))
        return None

    interactive = sys.stdin.isatty() if interactive is None else interactive
    report = _disconnect([client], records, yes, interactive)

    if not report.removed and not report.skills_removed and not report.pending:
        print(f"{client.label} had no ImageHearth entry.")

    print_report(report)

    for failure in report.failures:
        print(f"Could not remove: {failure}")

    return report


def disconnect_all(records, yes=False, interactive=False):
    """Para `uninstall`: todos los clientes, no solo lo que `connect` registró."""
    clients = [client for client in CLIENTS.values() if client.path is not None]
    return _disconnect(clients, records, yes, interactive)


def is_detected(client):
    if client.binary and shutil.which(client.binary):
        return True

    return client.path is not None and client.path().parent.exists()


def _ask_each(found):
    """Pregunta por cada cliente: 1 Sí, 2 No, 0 Atrás (al primero, sale). Devuelve la lista o BACK."""
    answers = {}
    index = 0

    while index < len(found):
        client = found[index]
        answer = menu.choose(
            f"Connect {client.label}?",
            [menu.Option("yes", "Yes"), menu.Option("no", "No")],
            default="yes",
            allow_back=True,
            back_label="Back" if index else "Exit without connecting anything",
        )

        if answer is menu.BACK:
            if index == 0:
                return menu.BACK

            index -= 1
            continue

        answers[client.name] = answer == "yes"
        index += 1

    return [client for client in found if answers.get(client.name)]


def _detect(args, command):
    found = [client for client in CLIENTS.values() if is_detected(client)]

    if not found:
        print("No known clients found. See `connect --list` and `connect --print`.")
        return 0

    records = InstallManifest.load(config.INSTALL_MANIFEST)
    interactive = sys.stdin.isatty()

    if args.yes or not interactive:
        for client in found:
            print(f"Found {client.label}.")

    if not args.yes and not interactive:
        raise ProvisionError("Nothing was changed. Non-interactive mode needs --yes.")

    if args.yes:
        chosen = found
    else:
        chosen = _ask_each(found)

        if chosen is menu.BACK:
            print("Nothing was changed.")
            return 0

    for client in chosen:
        connect(client, command, not args.no_skill, records)

    return 0


def run(args):
    if args.list_clients:
        for client in CLIENTS.values():
            print(f"{client.name:15} {client.label}")

        return 0

    command = server_command() if not args.remove else ""

    if args.detect:
        return _detect(args, command)

    if not args.agent:
        raise ProvisionError(
            "Say which client to connect, or use --detect. Known clients: "
            f"{', '.join(CLIENTS)}."
        )

    client = get_client(args.agent)

    if args.print_only:
        print(snippet(client, command), end="")

        if client.note:
            print(client.note)

        return 0

    if args.remove:
        disconnect(client, yes=args.yes)
        return 0

    connect(client, command, not args.no_skill)
    return 0
