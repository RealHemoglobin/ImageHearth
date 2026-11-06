"""Qué workflows ofrece esta máquina, según `models.toml` y lo que hay en disco.

Se evalúa en cada llamada y solo mira metadatos de archivo, para que un `setup`
posterior se note sin reiniciar el servidor.
"""

import sys
from dataclasses import dataclass

from imagehearth_mcp.engine import config, gpu

# Cada capacidad con sus variantes: se usa la que exista para el sistema.
VARIANTS = {
    "fast": ("sdxl_turbo",),
    # sdxl_quality (RealVisXL) is only for installations that predate SDXL 1.0.
    "high": ("flux_dev", "flux_dev_gguf", "flux_schnell", "sdxl_base", "sdxl_quality"),
    "edit": ("flux_kontext_dev_basic", "flux_kontext_dev_gguf"),
}


@dataclass(frozen=True)
class Entry:
    name: str
    profile: str
    installed: bool
    # Quality model the workflow belongs to ("flux-dev"...), for the high-quality ones.
    quality_model: str | None = None


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
            profile.base,
            all(item.state == models.PRESENT for item in states),
            quality_model_of(path.stem, catalog),
        )

    return result


def quality_model_of(workflow, catalog=None):
    """The quality model a workflow generates with, or None for the other workflows."""
    if workflow == "sdxl_quality":
        return "sdxl"

    from imagehearth_mcp.provisioner import manifest

    found = (catalog or manifest.load()).quality_workflows().get(workflow)
    return found[0] if found else None


def active_quality_model():
    """The quality model that `quality="high"` generates with, or None if none is installed.

    Comes from the installed files, like the catalog, so a `setup` shows at once.
    """
    from imagehearth_mcp.provisioner import manifest

    known = entries()
    name = next((w for w in VARIANTS["high"] if w in known and known[w].installed), None)

    if name is None:
        return None

    catalog = manifest.load()
    model = catalog.quality_model(known[name].quality_model)
    license = catalog.licenses[model.license]
    return {
        "name": model.name,
        "title": model.title,
        "workflow": name,
        "license": license.name,
        "commercial_use": license.commercial,
    }


def choose(capability, total_vram_mib=None):
    """The best variant of a capability that is installed and fits this GPU.

    If none is installed, the first one this system has: the error then says what to install.
    """
    variants = VARIANTS[capability]
    known = entries()
    candidates = [name for name in variants if name in known]

    if not candidates:
        return variants[0]

    total = total_vram_mib if total_vram_mib is not None else gpu.total_mib()
    installed = [name for name in candidates if known[name].installed]
    fitting = [
        name
        for name in installed
        if total is None or total >= minimum_vram_mib(name)
    ]

    return (fitting or installed or candidates)[0]


def minimum_vram_mib(workflow):
    """Least VRAM at which any profile with that workflow works; 0 if unknown."""
    from imagehearth_mcp.provisioner import manifest

    system = current_system()
    catalog = manifest.load()
    required = set(catalog.models_for(workflow))
    fits = [
        profile.min_vram_mib
        for profile in catalog.combinations(system)
        if required <= set(profile.models)
    ]
    return min(fits, default=0)


def required_vram_mib(workflow):
    """VRAM orientativa del menor perfil con ese workflow; 0 si no se conoce."""
    from imagehearth_mcp.provisioner import manifest

    profile = manifest.load().minimum_profile(workflow, current_system())
    return profile.min_vram_mib if profile else 0


def missing_installation():
    """Qué impide generar y con qué comando se arregla, o None si nada lo impide."""
    if not (
        (config.COMFY_DIR / "main.py").exists()
        or (config.COMFY_DIR / "custom_nodes").is_dir()
    ):
        return (
            f"ComfyUI is not installed in {config.COMFY_DIR}. Run "
            "`imagehearth-mcp setup`, or call setup_status to install it from here."
        )

    if not any(entry.installed for entry in entries().values()):
        return (
            "No image models are installed. Run `imagehearth-mcp setup --profile fast`, "
            "or call setup_status to install them from here."
        )

    return None
