"""Esquemas de los archivos de estado y migraciones del registro de instalación.

Una migración es una función pura `values -> values` del esquema N al N+1. `update`
las aplica en orden y guarda antes una copia del registro anterior. Ninguna migración
descarga ni borra modelos: solo reescribe el registro.
"""

from imagehearth_mcp.provisioner import ProvisionError

# Esquema de `install.json`. Solo cambia en una versión menor o mayor (docs/versioning.md).
INSTALL_SCHEMA = 1
# Estado de un traslado a medias (`move.json`) y salida de `doctor --json`.
MOVE_SCHEMA = 1
REPORT_SCHEMA = 1

# {N: función que lleva un registro del esquema N al N+1}.
MIGRATIONS = {}


def package_version():
    """Versión instalada de ImageHearth, o None si no se puede saber (p. ej. en un árbol sin instalar)."""
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("imagehearth-mcp")
    except PackageNotFoundError:
        return None


def schema_of(values, path):
    """El esquema de un registro, o ProvisionError si no es un registro conocido."""
    schema = values.get("schema") if isinstance(values, dict) else None

    if isinstance(schema, bool) or not isinstance(schema, int) or schema < 1:
        raise ProvisionError(f"Unknown install record format in {path}. Nothing was changed.")

    if schema > INSTALL_SCHEMA:
        raise ProvisionError(
            f"The install record {path} was written by a newer ImageHearth (format {schema}; "
            f"this one understands up to {INSTALL_SCHEMA}). Update ImageHearth with "
            "`uv tool upgrade imagehearth-mcp`. Nothing was changed."
        )

    return schema


def migrate(values, path):
    """(valores migrados, esquema de origen). No modifica `values`."""
    schema = schema_of(values, path)
    origin = schema
    values = dict(values)

    while schema < INSTALL_SCHEMA:
        step = MIGRATIONS.get(schema)

        if step is None:
            raise ProvisionError(
                f"There is no migration from install record format {schema} in {path}. "
                "Nothing was changed."
            )

        values = dict(step(dict(values)))
        schema += 1
        values["schema"] = schema

    return values, origin
