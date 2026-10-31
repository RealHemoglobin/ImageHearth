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
from dataclasses import dataclass
from pathlib import Path

import yaml
from platformdirs import user_config_path

from imagehearth_mcp.engine import config
from imagehearth_mcp.platform import files
from imagehearth_mcp.provisioner import ProvisionError
from imagehearth_mcp.provisioner.install_manifest import InstallManifest
from imagehearth_mcp.provisioner.setup import ask

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
            lambda exe: [exe, "mcp", "remove", "--scope", "user", SERVER_NAME],
            lambda: Path.home() / ".claude" / "skills",
        ),
        Client(
            "claude-desktop",
            "Claude Desktop",
            UNTESTED,
            "json",
            "mcpServers",
            path=lambda: _editor_config("Claude", "claude_desktop_config.json"),
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
            lambda exe: [exe, "mcp", "remove", "--scope", "user", SERVER_NAME],
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
            lambda exe: [exe, "mcp", "remove", SERVER_NAME],
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


def _without_server(client, values):
    """Copia de los valores sin nuestra entrada, y sin su sección si queda vacía."""
    result = dict(values)
    section = dict(result.get(client.key, {}))
    section.pop(SERVER_NAME, None)
    result[client.key] = section

    if not section:
        result.pop(client.key)

    return result


def _strip_toml(client, text):
    header = re.compile(
        rf"^\s*\[+\s*{re.escape(client.key)}\.{SERVER_NAME}\s*[\].]", re.MULTILINE
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


def _strip_yaml(client, text):
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

        own_entry = re.match(rf"['\"]?{SERVER_NAME}['\"]?\s*:", stripped)

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


def _remove_text(client, text):
    if client.format == "toml":
        return _strip_toml(client, text)

    if client.format == "yaml":
        return _empty_yaml_section(client, _strip_yaml(client, text))

    values = _without_server(client, json.loads(text))
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


def _run_cli(argv):
    try:
        result = subprocess.run(
            argv,
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


def _remove_entry(client, path, command=None):
    """Retira nuestra entrada; si otro la cambió, ya no es nuestra y se deja."""
    text, values = _read_config(client, path)
    current = (values.get(client.key) or {}).get(SERVER_NAME)

    if current is None:
        return "absent"

    if command is not None and _command_of(current) != [command]:
        return "changed"

    backup = _backup(path)

    if backup:
        print(f"Backup: {backup}")

    cli = _official_cli(client)

    if cli and client.remove:
        _run_cli(client.remove(cli))
    else:
        _write(path, _remove_text(client, text))

    return "removed"


def _remove_skill(client, records):
    if client.skills is None:
        return

    target = client.skills() / SERVER_NAME

    if records.is_owned(target):
        shutil.rmtree(target, ignore_errors=True)
        records.forget(target)
        records.save()


def disconnect(client, records=None):
    records = records or InstallManifest.load(config.INSTALL_MANIFEST)

    if client.path is None:
        print(client.note.replace("choose Add and paste the snippet", "and remove it there"))
        return

    known = next((c for c in records.connections if c["client"] == client.name), None)
    outcome = _remove_entry(client, client.path())
    _remove_skill(client, records)

    if known:
        records.connections.remove(known)
        records.save()

    print(
        f"Removed ImageHearth from {client.label}."
        if outcome == "removed"
        else f"{client.label} had no ImageHearth entry."
    )


def disconnect_all(records):
    """Para `uninstall`: solo lo que `connect` registró. Devuelve los fallos."""
    failures = []

    for connection in list(records.connections):
        client = CLIENTS.get(connection["client"])

        if client is None:
            continue

        try:
            outcome = _remove_entry(client, Path(connection["path"]), connection["command"])
            _remove_skill(client, records)
        except (OSError, ProvisionError) as error:
            failures.append(f"{connection['path']}: {error}")
            continue

        if outcome == "changed":
            print(f"Left as it is: the entry in {connection['path']} was changed by someone else.")

        records.connections.remove(connection)
        records.save()

    return failures


def is_detected(client):
    if client.binary and shutil.which(client.binary):
        return True

    return client.path is not None and client.path().parent.exists()


def _detect(args, command):
    found = [client for client in CLIENTS.values() if is_detected(client)]

    if not found:
        print("No known clients found. See `connect --list` and `connect --print`.")
        return 0

    records = InstallManifest.load(config.INSTALL_MANIFEST)
    interactive = sys.stdin.isatty()

    for client in found:
        print(f"Found {client.label} ({client.level}).")

    if not args.yes and not interactive:
        raise ProvisionError("Nothing was changed. Non-interactive mode needs --yes.")

    for client in found:
        if args.yes or ask(f"Connect {client.label}?"):
            connect(client, command, not args.no_skill, records)

    return 0


def run(args):
    if args.list_clients:
        for client in CLIENTS.values():
            print(f"{client.name:15} {client.label} ({client.level})")

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
        disconnect(client)
        return 0

    connect(client, command, not args.no_skill)
    return 0
