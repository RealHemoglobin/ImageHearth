"""Edita `config.toml` conservando comentarios y claves del usuario."""

import json
import re
import tomllib

from imagehearth_mcp.platform import files
from imagehearth_mcp.provisioner import ProvisionError


def _read(path):
    try:
        text = path.read_text(encoding="utf-8")
        return text, tomllib.loads(text)
    except FileNotFoundError:
        return "", {}
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ProvisionError(
            f"Can't read {path}: {error}. Fix or remove that file and try again."
        ) from error


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(text, encoding="utf-8")
    files.replace(temporary, path)


def _pattern(key):
    return re.compile(rf"^{re.escape(key)}\s*=.*$", re.MULTILINE)


def _set(text, key, value):
    # Las cadenas de JSON son cadenas básicas válidas de TOML.
    line = f"{key} = {json.dumps(value)}"
    pattern = _pattern(key)

    if pattern.search(text):
        return pattern.sub(lambda _: line, text, count=1)

    # Al principio: lo que va tras una cabecera [tabla] no sería de primer nivel.
    return f"{line}\n{text}"


def apply(path, values, records):
    """Escribe `values` y anota el valor anterior para poder restaurarlo."""
    text, current = _read(path)

    if not path.exists():
        records.claim("settings_file", path)

    changed = False

    for key, value in values.items():
        if current.get(key) == value:
            continue

        records.record_setting(key, value, current.get(key))
        text = _set(text, key, value)
        changed = True

    if changed:
        _write(path, text)


def restore(path, records):
    """Deshace los cambios registrados, salvo los que el usuario haya cambiado."""
    text, current = _read(path)
    changed = False

    for setting in records.settings:
        key = setting["key"]

        if current.get(key) != setting["value"]:
            continue

        if setting["previous"] is None:
            text = _pattern(key).sub("", text, count=1).lstrip("\n")
        else:
            text = _set(text, key, setting["previous"])

        changed = True

    if changed:
        _write(path, text)

    records.settings = []
