"""Modelo de `quality`: qué hay instalado, qué se propone y cómo se cambia de uno a otro."""

from dataclasses import dataclass, field

from imagehearth_mcp.engine import config
from imagehearth_mcp.platform import locks
from imagehearth_mcp.provisioner import ProvisionError, models
from imagehearth_mcp.provisioner.manifest import format_size

LEGACY = "RealVisXL"


@dataclass(frozen=True)
class Current:
    """El modelo de `quality` de una instalación. `legacy`: usa RealVisXL en vez de SDXL 1.0."""

    name: str
    legacy: bool = False


def current(catalog, records, models_dir):
    """El modelo de `quality` instalado, o None.

    Un registro anterior a la fase 9 no lo guarda: se deduce de los archivos.
    """
    base = catalog.profiles.get(records.profile or "")

    if base is None or not base.quality:
        return None

    if records.quality_model:
        return Current(records.quality_model)

    present = {
        item.model.name
        for item in models.inspect(
            [catalog.models[name] for name in ("flux_dev", "flux_dev_gguf", "realvisxl")],
            models_dir,
            models.extra_search_paths(config.COMFY_DIR),
        )
        if item.state == models.PRESENT
    }

    if present & {"flux_dev", "flux_dev_gguf"}:
        return Current("flux-dev")

    if "realvisxl" in present:
        return Current("sdxl", legacy=True)

    return None


def resolve_installed(catalog, records, models_dir, vram_mib=0):
    """El perfil registrado con sus modelos reales, o None si no hay instalación."""
    base = catalog.profiles.get(records.profile or "")

    if base is None:
        return None

    return resolve_for(
        catalog,
        base,
        current(catalog, records, models_dir),
        vram_mib,
        records.precision,
        records.edit_precision,
    )


def resolve_for(catalog, base, installed, vram_mib=0, forced=None, forced_edit=None):
    """`base` con el modelo `installed` (Current o None) y, si se puede, esas precisiones."""
    if installed is not None and installed.legacy:
        return _try(lambda *f: catalog.legacy_profile(base, vram_mib, *f), forced, forced_edit)

    name = installed.name if installed else None
    return _try(lambda *f: catalog.resolve(base, name, vram_mib, *f), forced, forced_edit)


def _try(resolve, forced, forced_edit):
    # Una precisión que el modelo no ofrece (p. ej. gguf con Schnell) se ignora.
    try:
        return resolve(forced, forced_edit)
    except ProvisionError:
        if forced is None and forced_edit is None:
            raise

        return resolve(None, None)


@dataclass
class Change:
    """Pasar de un modelo de `quality` a otro: qué se baja y qué se borra después."""

    old: Current
    new: str
    download: list = field(default_factory=list)
    delete: list = field(default_factory=list)
    kept_attached: bool = False

    @property
    def download_bytes(self):
        return sum(item.model.bytes for item in self.download)

    @property
    def freed_bytes(self):
        return sum(item.path.stat().st_size for item in self.delete if item.path.exists())


def plan_change(catalog, records, models_dir, old_profile, new_profile, keep_profile, old):
    """Lo que implica sustituir `old_profile` por `new_profile`.

    Solo se borra lo que instaló ImageHearth y que no usa ningún componente del
    perfil `keep_profile` (el mayor entre lo registrado y lo elegido). Los
    archivos preexistentes y los de un ComfyUI adjunto no son propios y nunca se tocan.
    """
    extra = models.extra_search_paths(config.COMFY_DIR)
    keep = {model.name for model in keep_profile.models} | {m.name for m in new_profile.models}
    leaving = [model for model in old_profile.models if model.name not in keep]
    change = Change(old, new_profile.quality_model)
    change.download = [
        item for item in models.inspect(new_profile.models, models_dir, extra) if item.state != models.PRESENT
    ]
    # A ComfyUI that isn't ours keeps every file it has, ours or not.
    change.kept_attached = records.mode == "attached"
    change.delete = (
        []
        if change.kept_attached
        else [
            item
            for item in models.inspect(leaving, models_dir)
            if item.state != models.MISSING and records.is_owned(item.path)
        ]
    )
    return change


def show_change(change, catalog):
    old = LEGACY if change.old.legacy else catalog.quality_model(change.old.name).title
    new = catalog.quality_model(change.new).title
    print(f"\nQuality model: {old} -> {new}")
    print(f"  To download: {format_size(change.download_bytes)}")

    for item in change.delete:
        print(f"  To delete afterwards: {item.path.name}")

    if change.kept_attached:
        print("  The old model stays in the ComfyUI you attached; delete it by hand if you want the space.")
    else:
        print(f"  Space freed: {format_size(change.freed_bytes)}")
    print("  The current model keeps working until the new one is downloaded and verified.")


def require_idle():
    """Un cambio de modelo no puede cruzarse con una generación."""
    from imagehearth_mcp.engine import state

    if locks.is_locked(config.LOCK_FILE) or state.read():
        raise ProvisionError(
            "An image is being generated, or a session needs `recover_engine`. Nothing "
            "was changed: wait for it to finish and run the command again."
        )


def delete_old(change, records):
    """Borra los archivos que dejó el modelo anterior. Se llama con el nuevo ya verificado."""
    from imagehearth_mcp.provisioner import maintenance

    failures = []

    for item in change.delete:
        try:
            maintenance._remove(item.path)
        except OSError as error:
            failures.append(f"{item.path}: {error}")
        else:
            records.forget(item.path)
            records.save()

    return failures


def restart_comfyui():
    """Si el ComfyUI gestionado estaba en marcha, se reinicia para que vea los modelos nuevos."""
    from imagehearth_mcp.engine import comfyui_manager

    if comfyui_manager.managed_pid() is None:
        return False

    print("Restarting ComfyUI so it sees the new model...")
    comfyui_manager.restart()
    return True


def choices(catalog, vram_mib, installed=None):
    """Una línea por modelo con lo que hace falta para elegir."""
    found = []

    for name in catalog.quality_models:
        info = catalog.describe_quality(name, vram_mib)
        info["installed"] = installed is not None and installed.name == name and not installed.legacy
        found.append(info)

    return found


def format_choice(info):
    flags = []

    if info["recommended"]:
        flags.append("recommended")

    if info["installed"]:
        flags.append("installed")

    commercial = "commercial use" if info["commercial_use"] else "non-commercial"
    line = (
        f"{info['name']:12} {format_size(info['download_bytes']):>8}  "
        f"{info['min_vram_mib'] / 1000:.0f} GB VRAM  {info['license'].name}, {commercial}"
    )
    line += f"  [{', '.join(flags)}]" if flags else ""

    if info["warning"]:
        line += f"\n{'':14}WARNING: {info['warning']}"

    return line
