"""Modelo de `quality`: qué hay instalado, qué se propone y cómo se cambia de uno a otro."""

from dataclasses import dataclass

from imagehearth_mcp.engine import config
from imagehearth_mcp.platform import locks
from imagehearth_mcp.provisioner import ProvisionError, models

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
    from imagehearth_mcp.provisioner import selection

    base = catalog.profiles.get(records.profile or "")

    if base is None:
        return None

    model_set = selection.installed_set(catalog, records, models_dir)

    if model_set and all(model_set.of(cap) for cap in base.capabilities):
        profile = catalog.build_set(selection.profile_for(catalog, base, model_set), model_set)

        if selection.is_legacy(catalog, records, models_dir):
            profile = selection.keep_realvisxl(catalog, profile)

        return profile

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


def require_idle():
    """Un cambio de modelo no puede cruzarse con una generación."""
    from imagehearth_mcp.engine import state

    if locks.is_locked(config.LOCK_FILE) or state.read():
        raise ProvisionError(
            "An image is being generated, or a session needs `recover_engine`. Nothing "
            "was changed: wait for it to finish and run the command again."
        )


def delete_items(items, records):
    """Borra esos archivos y los olvida en el registro. Devuelve los fallos, uno por línea."""
    from imagehearth_mcp.provisioner import maintenance

    failures = []

    for item in items:
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
