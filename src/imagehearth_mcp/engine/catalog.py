"""Qué workflows ofrece esta máquina, según `models.toml` y lo que hay en disco.

Se evalúa en cada llamada y solo mira metadatos de archivo, para que un `setup`
posterior se note sin reiniciar el servidor.
"""

import sys
from dataclasses import dataclass

from imagehearth_mcp.engine import config

# Cada capacidad con sus variantes: se usa la que exista para el sistema.
VARIANTS = {
    "fast": ("sdxl_turbo",),
    "high": ("flux_dev", "flux_dev_gguf"),
    "edit": ("flux_kontext_dev_basic", "flux_kontext_dev_gguf"),
}


@dataclass(frozen=True)
class Entry:
    name: str
    profile: str
    installed: bool


def current_system():
    return sys.platform.replace("win32", "windows")


def models_dir():
    # Se importa al usarse: el servidor MCP arranca sin cargar el provisioner.
    from imagehearth_mcp.provisioner import ProvisionError, models
    from imagehearth_mcp.provisioner.install_manifest import InstallManifest

    try:
        records = InstallManifest.load(config.INSTALL_MANIFEST)
    except ProvisionError:
        # Un registro dañado no impide generar; `doctor` ya lo señala.
        records = InstallManifest(config.INSTALL_MANIFEST)

    return models.resolve_dir(records, config.COMFY_DIR)


def entries():
    """Workflows de este sistema: en `data/workflows` y en el manifiesto a la vez."""
    from imagehearth_mcp.provisioner import manifest, models

    system = current_system()
    catalog = manifest.load()
    folder = models_dir()
    extra_paths = models.extra_search_paths(config.COMFY_DIR)
    result = {}

    for path in sorted(config.WORKFLOWS_DIR.glob("*.json")):
        profile = catalog.minimum_profile(path.stem, system)

        if profile is None:
            continue

        states = models.inspect(catalog.models_for(path.stem), folder, extra_paths)
        result[path.stem] = Entry(
            path.stem,
            profile.name,
            all(item.state == models.PRESENT for item in states),
        )

    return result


def choose(capability):
    """La variante de una capacidad que corresponde a este sistema."""
    variants = VARIANTS[capability]
    known = entries()
    return next((name for name in variants if name in known), variants[0])
