"""Qué workflows ofrece esta máquina, según `models.toml` y lo que hay en disco.

Se evalúa en cada llamada y solo mira metadatos de archivo, para que un `setup`
posterior se note sin reiniciar el servidor.
"""

import dataclasses
import sys
from dataclasses import dataclass, field
from pathlib import Path

from imagehearth_mcp.engine import config, gpu

# The workflows that existed before phase 15, in the order they were chosen in. The rest
# of each capability's variants come from the catalog.
LEGACY_VARIANTS = {
    "fast": ("sdxl_turbo",),
    # sdxl_quality (RealVisXL) is only for installations that predate SDXL 1.0.
    "high": ("flux_dev", "flux_dev_gguf", "flux_schnell", "sdxl_base", "sdxl_quality"),
    "edit": ("flux_kontext_dev_basic", "flux_kontext_dev_gguf"),
}


def variants():
    """Each capability with its workflows, derived from the catalog: the first installed one wins."""
    from imagehearth_mcp.provisioner import manifest

    catalog = manifest.load()
    found = {}

    for capability, legacy in LEGACY_VARIANTS.items():
        names = list(legacy)

        for model in catalog.catalog.values():
            if capability not in model.capabilities:
                continue

            for option in model.options:
                workflow = option.workflow(capability)

                if workflow and workflow not in names:
                    names.append(workflow)

        found[capability] = tuple(names)

    return found


def __getattr__(name):
    # `VARIANTS` is derived from the catalog on use, so importing this module loads nothing.
    if name == "VARIANTS":
        return variants()

    raise AttributeError(name)


# The base profile each capability first appears in: what the setup command to install it names.
CAPABILITY_PROFILE = {"fast": "fast", "high": "quality", "edit": "full"}
# The order models were the default in before phase 15, for installations that don't record one.
LEGACY_DEFAULTS = {
    "fast": ("sdxl-turbo",),
    "high": ("flux-dev", "flux-schnell", "sdxl"),
    "edit": ("kontext",),
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


def records():
    """The install record, or an empty one if it is missing or damaged."""
    # Se importa al usarse: el servidor MCP arranca sin cargar el provisioner.
    from imagehearth_mcp.provisioner import ProvisionError
    from imagehearth_mcp.provisioner.install_manifest import InstallManifest

    try:
        return InstallManifest.load(config.INSTALL_MANIFEST)
    except ProvisionError:
        # Un registro dañado no impide generar; `doctor` ya lo señala.
        return InstallManifest(config.INSTALL_MANIFEST)


def models_dir():
    from imagehearth_mcp.provisioner import models

    return models.resolve_dir(records(), config.COMFY_DIR)


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

    # The workflows of the catalog models (phase 15): one workflow can serve several
    # precisions of a model, and it is installed if any of them is.
    new = _new_names(catalog)

    for name, model, capability, option in _catalog_workflows(catalog):
        # The older workflows come from the profiles above. macOS has fixed models only.
        if name not in new or system == "darwin":
            continue

        states = models.inspect(catalog.expand(option.models), folder, extra_paths)
        present = all(item.state == models.PRESENT for item in states)
        before = result.get(name)
        result[name] = Entry(
            name,
            CAPABILITY_PROFILE[capability],
            present or (before is not None and before.installed),
            model.name if capability == "high" else None,
        )

    return result


def _catalog_workflows(catalog):
    """(workflow, model, capability, option) of the catalog, for the workflows that ship."""
    for model in catalog.catalog.values():
        for option in model.options:
            for capability, workflow in option.workflows.items():
                if (config.WORKFLOWS_DIR / f"{workflow}.json").is_file():
                    yield workflow, model, capability, option


def _new_names(catalog):
    """Workflows only the catalog knows: the older ones are handled by the profiles."""
    return {
        workflow
        for model in catalog.catalog.values()
        if model.name not in LEGACY_MODELS
        for option in model.options
        for workflow in option.workflows.values()
    }


LEGACY_MODELS = ("sdxl-turbo", "sdxl", "flux-dev", "flux-schnell", "kontext")


def quality_model_of(workflow, catalog=None):
    """The quality model a workflow generates with, or None for the other workflows."""
    if workflow == "sdxl_quality":
        return "sdxl"

    from imagehearth_mcp.provisioner import manifest

    found = (catalog or manifest.load()).quality_workflows().get(workflow)

    if found:
        return found[0]

    for model in (catalog or manifest.load()).catalog.values():
        if "high" in model.capabilities and any(
            option.workflow("high") == workflow for option in model.options
        ):
            return model.name

    return None


def active_quality_model():
    """The quality model that `quality="high"` generates with, or None if none is installed.

    It is the default of the `high` capability, from the installed files like the rest of
    the catalog, so a `setup` shows at once.
    """
    item = default_model("high")

    if item is None:
        return None

    return {
        "name": item.name,
        "title": item.title,
        "workflow": item.workflow,
        "license": item.license,
        "commercial_use": item.commercial_use,
    }


def choose(capability, total_vram_mib=None):
    """The best variant of a capability that is installed and fits this GPU.

    If none is installed, the first one this system has: the error then says what to install.
    """
    variants = globals()["variants"]()[capability]
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

    if not fits:
        fits = [option.min_vram_mib for _, _, _, option in _options_of(catalog, workflow)]

    return min(fits, default=0)


def _options_of(catalog, workflow):
    return [item for item in _catalog_workflows(catalog) if item[0] == workflow]


def required_vram_mib(workflow):
    """VRAM orientativa del menor perfil con ese workflow; 0 si no se conoce."""
    from imagehearth_mcp.provisioner import manifest

    catalog = manifest.load()
    profile = catalog.minimum_profile(workflow, current_system())

    if profile:
        return profile.min_vram_mib

    return min((option.min_vram_mib for _, _, _, option in _options_of(catalog, workflow)), default=0)


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


# ---- Models by capability (phase 15) ----------------------------------------------------

SETUP_FLAGS = {"fast": "--fast-models", "high": "--quality-models", "edit": "--edit-models"}
CAPABILITY_NAMES = {"fast": "fast", "high": "high-quality", "edit": "editing"}


@dataclass(frozen=True)
class InstalledModel:
    """A catalog model that is installed for a capability, with the precision it has."""

    name: str
    title: str
    capability: str
    precision: str
    workflow: str
    default: bool
    license: str
    commercial_use: bool
    # Seconds per image measured for this GPU's level, or None if it wasn't measured.
    seconds: float | None = None
    # Role (unet, clip, vae...) -> file name, for the workflows with markers.
    loaders: dict = field(default_factory=dict)
    max_references: int | None = None
    # RealVisXL, kept for installations from before SDXL 1.0.
    legacy: bool = False

    @property
    def label(self):
        return f"{self.name}:{self.precision}"


def setup_command(capability, model=None):
    """The command that installs a model of a capability (or the capability in general)."""
    profile = CAPABILITY_PROFILE[capability]
    option = f" {SETUP_FLAGS[capability]} {model}" if model else ""
    return f"`imagehearth-mcp setup --profile {profile}{option}`"


def installed_models(capability=None, total_vram_mib=None):
    """Installed models, per capability in catalog order, with the default flagged.

    Comes from the files on disk (and the install record for the default and the
    precision), like the rest of the catalog, so a `setup` shows at once.
    """
    from imagehearth_mcp.provisioner import manifest, models

    catalog = manifest.load()
    folder = models_dir()
    extra_paths = models.extra_search_paths(config.COMFY_DIR)
    record = records()
    total = total_vram_mib if total_vram_mib is not None else gpu.total_mib()
    tier = manifest.tier_of(total or 0)
    wanted = [capability] if capability else list(manifest.CAPABILITIES)
    found = []

    for cap in wanted:
        recorded = {
            item["model"]: item["precision"]
            for item in (getattr(record, "models", None) or {}).get(cap, ())
        }
        present = []

        for model in catalog.catalog.values():
            if cap not in model.capabilities:
                continue

            options = [
                option
                for option in model.options
                if option.workflow(cap)
                and (config.WORKFLOWS_DIR / f"{option.workflow(cap)}.json").is_file()
                and all(
                    item.state == models.PRESENT
                    for item in models.inspect(catalog.expand(option.models), folder, extra_paths)
                )
            ]

            if not options:
                continue

            fitting = [o for o in options if not total or total >= o.min_vram_mib]
            chosen = next(
                (o for o in options if recorded.get(model.name) == o.precision),
                (fitting or options)[0],
            )
            licence = catalog.licenses[model.license]
            measure = chosen.measure(cap, tier)
            present.append(
                InstalledModel(
                    model.name,
                    model.title,
                    cap,
                    chosen.precision,
                    chosen.workflow(cap),
                    False,
                    licence.name,
                    all(
                        catalog.licenses[key].commercial
                        for key in {
                            model.license,
                            *(i.license for i in catalog.expand(chosen.models)),
                        }
                    ),
                    measure.seconds if measure else None,
                    {
                        role: Path(catalog.models[weight].dest).name
                        for role, weight in chosen.loaders.items()
                    },
                    model.max_references,
                )
            )

        present.extend(_legacy_realvisxl(cap, present, catalog))
        chosen_default = _default_of(cap, present, getattr(record, "defaults", None) or {})
        found.extend(
            dataclasses.replace(item, default=item.name == chosen_default) for item in present
        )

    return found


def _legacy_realvisxl(cap, present, catalog):
    """RealVisXL keeps generating as the `sdxl` quality model until `setup` replaces it."""
    if cap != "high" or any(item.name == "sdxl" for item in present):
        return []

    entry = entries().get("sdxl_quality")

    if entry is None or not entry.installed:
        return []

    model = catalog.catalog["sdxl"]
    licence = catalog.licenses["openrail-pp"]
    return [
        InstalledModel(
            "sdxl", model.title, cap, "fp16", "sdxl_quality", False, licence.name,
            licence.commercial, legacy=True,
        )
    ]


def _default_of(cap, present, recorded):
    """The model `create_image` uses without `model`: the recorded one, else the old order."""
    names = [item.name for item in present]

    if recorded.get(cap) in names:
        return recorded[cap]

    for name in LEGACY_DEFAULTS[cap]:
        if name in names:
            return name

    return names[0] if names else None


def default_model(capability):
    """The default installed model of a capability, or None if none is installed."""
    return next((item for item in installed_models(capability) if item.default), None)


def resolve_model(capability, model=""):
    """The installed model a request uses: `model`, or the capability's default.

    Raises ValueError with what is installed and the command to install what is missing.
    """
    from imagehearth_mcp.provisioner import manifest

    installed = installed_models(capability)
    what = CAPABILITY_NAMES[capability]

    if not model:
        found = next((item for item in installed if item.default), None)

        if found is None:
            raise ValueError(
                f"No {what} model is installed. Install one with {setup_command(capability)}, "
                "or call setup_status to install it from here."
            )

        return found

    if not isinstance(model, str) or not model.strip():
        raise ValueError("model must be a model name.")

    model = model.strip()
    found = next((item for item in installed if item.name == model), None)

    if found is not None:
        return found

    names = ", ".join(item.name for item in installed) or "none"
    catalog = manifest.load()
    entry = catalog.catalog.get(model)

    if entry is None:
        raise ValueError(
            f"Unknown model {model!r}. Installed {what} models: {names}. "
            "list_workflows shows them."
        )

    if capability not in entry.capabilities:
        has = ", ".join(CAPABILITY_NAMES[c] for c in entry.capabilities)
        raise ValueError(
            f"{entry.title} ({model}) is a {has} model and this request needs a {what} one. "
            f"Installed {what} models: {names}."
        )

    raise ValueError(
        f"{entry.title} ({model}) is not installed for {what}. Installed {what} models: "
        f"{names}. Install it with {setup_command(capability, model)}."
    )


def installed_for_workflow(workflow):
    """The installed model that a workflow name belongs to, or None."""
    for item in installed_models():
        if item.workflow == workflow:
            return item

    return None
