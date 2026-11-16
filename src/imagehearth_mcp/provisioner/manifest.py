"""Carga y valida `data/models.toml`."""

import dataclasses
import re
import tomllib
from dataclasses import dataclass, field
from importlib import resources

from imagehearth_mcp.provisioner import ProvisionError

_SHA256 = re.compile(r"[0-9a-f]{64}")
_LORA_NAME = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
MAX_LORA_WEIGHT = 2.0
_REVISION = re.compile(r"[0-9a-f]{40}")
DESKTOP_PLATFORMS = ("linux", "windows")


@dataclass(frozen=True)
class License:
    key: str
    name: str
    url: str
    summary: str
    commercial: bool = True


@dataclass(frozen=True)
class Model:
    name: str
    repo: str
    revision: str
    filename: str
    dest: str
    bytes: int
    sha256: str
    license: str
    workflows: tuple[str, ...] = ()
    # Models this one needs besides itself (text encoders, VAE, LoRA).
    requires: tuple[str, ...] = ()
    # Kept in the manifest only so an old installation keeps generating.
    legacy: bool = False


@dataclass(frozen=True)
class Lora:
    """A style LoRA for SDXL 1.0. It has the fields of `Model` the downloader needs."""

    name: str
    description: str
    category: str
    trigger_words: tuple[str, ...]
    # Recommended strength.
    weight: float
    base: str
    repo: str
    revision: str
    filename: str
    dest: str
    bytes: int
    sha256: str
    license: str
    # Same shape as `Model`, so `provisioner.models` handles both alike.
    workflows = ()
    requires = ()
    legacy = False

    @property
    def lora_name(self):
        """The name ComfyUI's LoraLoader knows it by: the path under `models/loras`."""
        return self.dest.removeprefix("loras/")


@dataclass(frozen=True)
class NodePin:
    """Nodo personalizado de ComfyUI, fijado por commit y SHA-256."""

    name: str
    folder: str
    url: str
    sha256: str
    license: str
    packages: tuple[str, ...]


@dataclass(frozen=True)
class Option:
    """A way to install something: one precision, with its models and the VRAM it needs."""

    precision: str
    min_vram_mib: int
    models: tuple[Model, ...]
    nodes: tuple[NodePin, ...] = ()
    workflow: str | None = None


@dataclass(frozen=True)
class QualityModel:
    name: str
    title: str
    license: str
    recommended_from_mib: int
    # From most to least VRAM.
    options: tuple[Option, ...]

    @property
    def min_vram_mib(self):
        return min(option.min_vram_mib for option in self.options)


CAPABILITIES = ("fast", "high", "edit")
TIERS = (8, 16, 24, 32)


def normalize_precision(text):
    """`Q4_K_M`, `q4-k-m` and `q4km` name the same precision."""
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


def tier_of(vram_mib):
    """The measured level (8, 16, 24 or 32+ GB) of a GPU memory. Unknown (0) is 16."""
    if not vram_mib:
        return 16

    if vram_mib < 14000:
        return 8

    if vram_mib < 22000:
        return 16

    if vram_mib < 30000:
        return 24

    return 32


@dataclass(frozen=True)
class Measure:
    """What was measured for an option at a level, on the RTX 4090 (phase 14)."""

    seconds: float | None = None
    vram_mib: int | None = None
    # Weights the GPU couldn't hold at that level and ComfyUI moved to RAM.
    offload_mib: int = 0


@dataclass(frozen=True)
class CatalogOption:
    """One precision of a catalog model: its weights, the workflow per capability and data."""

    precision: str
    min_vram_mib: int
    models: tuple[Model, ...]
    # capability -> workflow name
    workflows: dict = field(default_factory=dict)
    nodes: tuple[NodePin, ...] = ()
    # Role (unet, clip, vae...) -> weight name; fills the %UNET%, %CLIP%, %VAE% markers.
    loaders: dict = field(default_factory=dict)
    # capability -> {level in GB -> value}
    seconds: dict = field(default_factory=dict)
    vram_mib: dict = field(default_factory=dict)
    offload_mib: dict = field(default_factory=dict)

    def workflow(self, capability):
        return self.workflows.get(capability)

    def measure(self, capability, tier):
        """The data at `tier`, or at the nearest lower one measured; None if never measured."""
        seconds = self.seconds.get(capability, {})
        usable = [level for level in sorted(seconds) if level <= tier]

        if not usable:
            return None

        level = usable[-1]
        return Measure(
            seconds.get(level),
            self.vram_mib.get(capability, {}).get(level),
            self.offload_mib.get(capability, {}).get(level, 0),
        )


@dataclass(frozen=True)
class CatalogModel:
    """An image model of the catalog, with the capabilities it has and its precisions."""

    name: str
    title: str
    license: str
    capabilities: tuple[str, ...]
    # Best quality first.
    options: tuple[CatalogOption, ...]
    # Most reference images an editing model takes; None is the engine's general limit.
    max_references: int | None = None

    def option(self, precision):
        wanted = normalize_precision(precision)
        return next(
            (item for item in self.options if normalize_precision(item.precision) == wanted),
            None,
        )

    @property
    def min_vram_mib(self):
        return min(option.min_vram_mib for option in self.options)


@dataclass(frozen=True)
class Pick:
    """A model with the precision chosen for it."""

    model: str
    precision: str

    def __str__(self):
        return f"{self.model}:{self.precision}"


@dataclass
class ModelSet:
    """What an installation has: per capability, its models and which one is the default."""

    picks: dict = field(default_factory=dict)
    defaults: dict = field(default_factory=dict)

    def of(self, capability):
        return tuple(self.picks.get(capability, ()))

    def default(self, capability):
        """The default model of a capability: the stated one, else the first."""
        picks = self.of(capability)
        stated = self.defaults.get(capability)

        if stated and any(pick.model == stated for pick in picks):
            return next(pick for pick in picks if pick.model == stated)

        return picks[0] if picks else None

    def pick(self, capability, model):
        return next((item for item in self.of(capability) if item.model == model), None)

    def all(self):
        return [(cap, pick) for cap in CAPABILITIES for pick in self.of(cap)]

    def __bool__(self):
        return any(self.picks.values())


@dataclass(frozen=True)
class Profile:
    name: str
    description: str
    min_vram_mib: int
    models: tuple[Model, ...]
    platforms: tuple[str, ...] = DESKTOP_PLATFORMS
    nodes: tuple[NodePin, ...] = ()
    # A variant is the same profile with other models, for a range of VRAM.
    variant_of: str | None = None
    # `quality` and `edit` mark profiles whose quality model and editing model are chosen
    # by `Manifest.resolve`. A resolved profile also says which it ended up with.
    quality: bool = False
    edit: bool = False
    quality_model: str | None = None
    precision: str | None = None
    edit_precision: str | None = None
    # Capabilities the profile includes ("fast", "high", "edit"), chosen by model sets.
    capabilities: tuple[str, ...] = ()
    # Profiles whose models are fixed (macOS): capability -> ("name:precision", ...).
    fixed: tuple = ()
    # What a profile resolved by `build_set` ended up with.
    model_set: object = None

    @property
    def base(self):
        return self.variant_of or self.name

    @property
    def bytes(self):
        return sum(model.bytes for model in self.models)


@dataclass(frozen=True)
class ComfyPin:
    version: str
    url: str
    sha256: str
    license: str
    install_bytes: int


@dataclass(frozen=True)
class TorchPin:
    python: str
    index: str
    packages: tuple[str, ...]
    min_driver: int | None
    install_bytes: int | None = None


@dataclass(frozen=True)
class Manifest:
    comfyui: ComfyPin
    pytorch: dict[str, TorchPin]
    licenses: dict[str, License]
    models: dict[str, Model]
    profiles: dict[str, Profile]
    nodes: dict[str, NodePin] = field(default_factory=dict)
    quality_models: dict[str, QualityModel] = field(default_factory=dict)
    edit_options: tuple[Option, ...] = ()
    loras: dict[str, Lora] = field(default_factory=dict)
    catalog: dict[str, CatalogModel] = field(default_factory=dict)
    # capability -> {level in GB -> "model:precision"}
    recommended_models: dict = field(default_factory=dict)

    def lora_licenses(self, loras):
        """The licenses of those LoRAs, without repeats."""
        keys = []

        for item in loras:
            if item.license not in keys:
                keys.append(item.license)

        return [self.licenses[key] for key in keys]

    def licenses_for(self, profile):
        keys = [self.comfyui.license]

        for item in (*profile.nodes, *profile.models):
            if item.license not in keys:
                keys.append(item.license)

        return [self.licenses[key] for key in keys]

    def profiles_for(self, system):
        """Los perfiles de un sistema, de menor a mayor. Sin variantes."""
        return {
            name: profile
            for name, profile in self.profiles.items()
            if system in profile.platforms and profile.variant_of is None
        }

    def min_vram_mib(self, profile):
        """The least VRAM at which the profile works with any of its choices."""
        return profile.min_vram_mib

    def expand(self, models):
        """The models followed by what they require, without repeats."""
        found = {}
        pending = list(models)

        while pending:
            model = pending.pop(0)

            if model.name not in found:
                found[model.name] = model
                pending.extend(self.models[name] for name in model.requires)

        return tuple(found.values())

    def recommend(self, vram_mib):
        """The quality model that suits that GPU memory (0 = unknown: the first one)."""
        ranked = sorted(self.quality_models.values(), key=lambda item: -item.recommended_from_mib)

        if not vram_mib:
            return ranked[0].name

        return next(
            (item.name for item in ranked if vram_mib >= item.recommended_from_mib),
            ranked[-1].name,
        )

    def quality_model(self, name):
        try:
            return self.quality_models[name]
        except KeyError:
            raise ProvisionError(
                f"Unknown quality model {name!r}. Choose one of: "
                f"{', '.join(self.quality_models)}."
            ) from None

    def fits(self, name, vram_mib):
        return not vram_mib or vram_mib >= self.quality_model(name).min_vram_mib

    def warning(self, name, vram_mib):
        """What to tell the user when the model doesn't fit this GPU, or None."""
        if self.fits(name, vram_mib):
            return None

        model = self.quality_model(name)
        return (
            f"{model.title} needs at least {model.min_vram_mib} MiB of GPU memory and "
            f"this machine has {vram_mib} MiB. It can be installed, but generation may "
            "be slow or fail."
        )

    def describe_quality(self, name, vram_mib):
        """What the user needs to choose a quality model: size, VRAM, license and fit."""
        model = self.quality_model(name)
        option = self._pick(model.options, vram_mib, None, model.title)
        license = self.licenses[model.license]
        return {
            "name": name,
            "title": model.title,
            "precision": option.precision,
            "download_bytes": sum(item.bytes for item in self.expand(option.models)),
            "min_vram_mib": model.min_vram_mib,
            "license": license,
            "commercial_use": license.commercial,
            "recommended": name == self.recommend(vram_mib),
            "fits": self.fits(name, vram_mib),
            "warning": self.warning(name, vram_mib),
        }

    # ---- Catalog by capability (phase 15) -------------------------------------------

    def catalog_model(self, name, capability=None):
        try:
            model = self.catalog[name]
        except KeyError:
            raise ProvisionError(
                f"Unknown model {name!r}. Choose one of: "
                f"{', '.join(self.models_with(capability)) if capability else ', '.join(self.catalog)}."
            ) from None

        if capability and capability not in model.capabilities:
            raise ProvisionError(
                f"{model.title} ({name}) doesn't have the {capability} capability. "
                f"Choose one of: {', '.join(self.models_with(capability))}."
            )

        return model

    def models_with(self, capability):
        """Names of the catalog models that have `capability`, in catalog order."""
        return [name for name, model in self.catalog.items() if capability in model.capabilities]

    def parse_pick(self, capability, text, vram_mib=0):
        """`name` or `name:precision` as a Pick; the precision defaults to the recommended."""
        name, _, precision = str(text).strip().partition(":")
        model = self.catalog_model(name.strip(), capability)

        if not precision.strip():
            return Pick(name.strip(), self.recommended_precision(model, capability, vram_mib).precision)

        option = model.option(precision.strip())

        if option is None or option.workflow(capability) is None:
            raise ProvisionError(
                f"{model.title} has no {precision.strip()} precision. Choose one of: "
                f"{', '.join(item.precision for item in model.options)}."
            )

        return Pick(name.strip(), option.precision)

    def parse_picks(self, capability, texts, vram_mib=0):
        """A list of `name[:precision]`: Picks without repeats; the first is the default."""
        picks = []

        for text in texts:
            pick = self.parse_pick(capability, text, vram_mib)

            if any(item.model == pick.model for item in picks):
                raise ProvisionError(
                    f"{pick.model} is listed twice. Only one precision of a model is installed."
                )

            picks.append(pick)

        if not picks:
            raise ProvisionError(f"Choose at least one {capability} model.")

        return picks

    def recommended_precision(self, model, capability, vram_mib=0):
        """The option with the best quality that fits this GPU without going to RAM.

        If every option needs RAM at this level, the one that moves the least. Options
        without measurements are judged by their minimum VRAM.
        """
        options = [item for item in model.options if item.workflow(capability)]
        tier = tier_of(vram_mib)

        def spill(option):
            measure = option.measure(capability, tier)

            if measure is not None:
                return measure.offload_mib

            return 0 if not vram_mib or vram_mib >= option.min_vram_mib else 1

        clean = [item for item in options if spill(item) == 0]

        if clean:
            return clean[0]

        return min(options, key=spill)

    def recommended_pick(self, capability, vram_mib=0):
        """The model and precision this GPU level is recommended for `capability`."""
        table = self.recommended_models.get(capability, {})
        levels = sorted(table)
        tier = tier_of(vram_mib)
        chosen = next((table[level] for level in reversed(levels) if level <= tier), None)

        if chosen is None:
            names = self.models_with(capability)
            chosen = names[0] if names else None

        if chosen is None:
            return None

        return self.parse_pick(capability, chosen, vram_mib)

    def recommended_set(self, profile, vram_mib=0):
        """The set of models recommended for a GPU: one per capability of the profile."""
        if profile.fixed:
            return self.fixed_set(profile)

        picks = {}

        for capability in profile.capabilities:
            pick = self.recommended_pick(capability, vram_mib)

            if pick is not None:
                picks[capability] = (pick,)

        return ModelSet(picks, {cap: items[0].model for cap, items in picks.items()})

    def fixed_set(self, profile):
        picks = {
            capability: tuple(self.parse_pick(capability, text) for text in texts)
            for capability, texts in profile.fixed
        }
        return ModelSet(picks, {cap: items[0].model for cap, items in picks.items()})

    def uses_catalog(self, profile):
        return bool(profile.capabilities)

    def option_of(self, capability, pick):
        """The CatalogOption of a pick, or a ProvisionError."""
        model = self.catalog_model(pick.model, capability)
        option = model.option(pick.precision)

        if option is None or option.workflow(capability) is None:
            raise ProvisionError(
                f"{model.title} has no {pick.precision} precision. Choose one of: "
                f"{', '.join(item.precision for item in model.options)}."
            )

        return option

    def build_set(self, profile, model_set):
        """The profile resolved with exactly these models, one precision each."""
        if not profile.capabilities:
            raise ProvisionError(f"The {profile.name} profile has no models to choose.")

        for capability in CAPABILITIES:
            picks = model_set.of(capability)

            if capability in profile.capabilities and not picks:
                raise ProvisionError(
                    f"The {profile.name} profile needs at least one {capability} model."
                )

            if capability not in profile.capabilities and picks:
                raise ProvisionError(
                    f"The {profile.name} profile has no {capability} models: remove them or "
                    "choose a larger profile."
                )

        chosen = []
        nodes = []

        for capability, pick in model_set.all():
            option = self.option_of(capability, pick)
            chosen.extend(option.models)
            nodes.extend(node for node in option.nodes if node not in nodes)

        high = model_set.default("high")
        edit = model_set.default("edit")
        return dataclasses.replace(
            profile,
            min_vram_mib=max(
                profile.min_vram_mib,
                *(self.option_of(cap, pick).min_vram_mib for cap, pick in model_set.all()),
            ),
            models=self.expand(chosen),
            nodes=tuple(nodes),
            variant_of=None,
            quality_model=high.model if high else None,
            precision=high.precision if high else None,
            edit_precision=edit.precision if edit else None,
            model_set=model_set,
        )

    def describe_catalog(self, capability, vram_mib=0):
        """What the user needs to pick models of a capability: one entry per model."""
        tier = tier_of(vram_mib)
        recommended = self.recommended_pick(capability, vram_mib)
        found = []

        for name in self.models_with(capability):
            model = self.catalog[name]
            license = self.licenses[model.license]
            precisions = []
            best = self.recommended_precision(model, capability, vram_mib)

            for option in model.options:
                if option.workflow(capability) is None:
                    continue

                measure = option.measure(capability, tier)
                precisions.append(
                    {
                        "precision": option.precision,
                        "download_bytes": sum(item.bytes for item in self.expand(option.models)),
                        "min_vram_mib": option.min_vram_mib,
                        "seconds": measure.seconds if measure else None,
                        "vram_mib": measure.vram_mib if measure else None,
                        "offload_mib": measure.offload_mib if measure else None,
                        "fits": not vram_mib or vram_mib >= option.min_vram_mib,
                        "recommended": option is best,
                    }
                )

            licenses = {license.name}

            for option in model.options:
                for item in self.expand(option.models):
                    licenses.add(self.licenses[item.license].name)

            found.append(
                {
                    "name": name,
                    "title": model.title,
                    "license": license,
                    "commercial_use": all(
                        self.licenses[key].commercial
                        for key in {model.license, *(i.license for o in model.options for i in self.expand(o.models))}
                    ),
                    "recommended": recommended is not None and recommended.model == name,
                    "precisions": precisions,
                    "max_references": model.max_references,
                }
            )

        return found

    @staticmethod
    def _pick(options, vram_mib, forced, what):
        """The option that fits `vram_mib`; if none does, the one that needs the least."""
        if forced:
            match = next((item for item in options if item.precision == forced), None)

            if match is None:
                raise ProvisionError(
                    f"{what} has no {forced} variant. Choose one of: "
                    f"{', '.join(item.precision for item in options)}."
                )

            return match

        if not vram_mib:
            return options[0]

        return next((item for item in options if vram_mib >= item.min_vram_mib), options[-1])

    def _build(self, profile, model, option, edit):
        chosen = [option, *([edit] if edit else [])]
        gguf = any(item.precision == "gguf" for item in chosen)
        nodes = []

        for item in chosen:
            nodes.extend(node for node in item.nodes if node not in nodes)

        title = f"{profile.description} with {model.title}"
        return dataclasses.replace(
            profile,
            name=f"{profile.name}-gguf" if gguf else profile.name,
            description=title,
            min_vram_mib=max(item.min_vram_mib for item in chosen),
            models=self.expand([*profile.models, *(m for item in chosen for m in item.models)]),
            nodes=tuple(nodes),
            variant_of=profile.name if gguf else None,
            quality_model=model.name,
            precision=option.precision,
            edit_precision=edit.precision if edit else None,
        )

    def resolve(self, profile, quality_model=None, vram_mib=0, forced=None, forced_edit=None):
        """The profile with the quality model and precisions that fit `vram_mib`.

        `quality_model` None means the one recommended for that memory (0 = unknown).
        `forced` is a precision such as "fp8" or "gguf" for the quality model and
        `forced_edit` the one for image editing; if the latter is missing, `forced`
        is used when editing offers it. A model that doesn't fit is
        resolved anyway, to its leanest option: the caller warns. Only image editing,
        which has no leaner option, raises ProvisionError.
        """
        if not profile.quality:
            if forced not in (None, "fp8"):
                raise ProvisionError(f"The {profile.name} profile has no {forced} variant.")

            return profile

        model = self.quality_model(quality_model or self.recommend(vram_mib))
        option = self._pick(model.options, vram_mib, forced, model.title)
        edit = None

        if profile.edit:
            smallest = min(item.min_vram_mib for item in self.edit_options)

            if vram_mib and vram_mib < smallest:
                raise ProvisionError(
                    f"The {profile.name} profile needs at least {smallest} MiB of GPU "
                    f"memory for image editing and this machine has {vram_mib} MiB. Use "
                    "--profile quality instead. Image editing isn't available below that."
                )

            wanted = forced_edit or (
                forced if any(i.precision == forced for i in self.edit_options) else None
            )
            edit = self._pick(self.edit_options, vram_mib, wanted, "Image editing")

        return self._build(profile, model, option, edit)

    def combinations(self, system):
        """Every profile of the system with each quality model and precision, small first."""
        for profile in self.profiles_for(system).values():
            if not profile.quality:
                yield profile
                continue

            for model in self.quality_models.values():
                for option in reversed(model.options):
                    for edit in reversed(self.edit_options) if profile.edit else (None,):
                        yield self._build(profile, model, option, edit)

    def legacy_profile(self, profile, vram_mib=0, forced=None, forced_edit=None):
        """`profile` with RealVisXL instead of SDXL 1.0, for an installation that has it."""
        resolved = self.resolve(profile, "sdxl", vram_mib, forced, forced_edit)
        old = self.models["realvisxl"]
        swapped = tuple(old if m.name == "sdxl_base" else m for m in resolved.models)
        return dataclasses.replace(
            resolved, models=self.expand(swapped), description=f"{profile.description} with RealVisXL"
        )

    def install_bytes(self, torch):
        """Lo que ocupan ComfyUI y su entorno, que depende de PyTorch."""
        if torch is not None and torch.install_bytes:
            return torch.install_bytes

        return self.comfyui.install_bytes

    def models_for(self, workflow):
        return tuple(m for m in self.models.values() if workflow in m.workflows)

    def minimum_profile(self, workflow, system):
        """El menor perfil del sistema con todos los modelos del workflow."""
        required = set(self.models_for(workflow))

        if not required:
            return None

        for profile in self.combinations(system):
            if required <= set(profile.models):
                return profile

        # A workflow of a model that is no longer offered still belongs to its profile.
        if all(model.legacy or model.name in {"sdxl_offset_lora", "sdxl_turbo"} for model in required):
            base = next((p for p in self.profiles_for(system).values() if p.quality), None)
            return self.legacy_profile(base) if base else None

        return None

    def quality_workflows(self):
        """Workflow -> (quality model, precision) for each one the manifest offers."""
        return {
            option.workflow: (model.name, option.precision)
            for model in self.quality_models.values()
            for option in model.options
            if option.workflow
        }


def _parse_loras(entries, licenses, models):
    loras = {}
    destinations = {model.dest for model in models.values()}

    for entry in entries:
        trigger_words = entry["trigger_words"]

        if not isinstance(trigger_words, (list, tuple)) or not all(
            isinstance(word, str) and word.strip() for word in trigger_words
        ):
            raise ValueError(f"{entry['name']}: trigger_words must be a list of words")

        weight = entry["weight"]
        lora = Lora(
            entry["name"],
            entry["description"],
            entry["category"],
            tuple(trigger_words),
            weight,
            entry["base"],
            entry["repo"],
            entry["revision"],
            entry["filename"],
            entry["dest"],
            entry["bytes"],
            entry["sha256"],
            entry["license"],
        )

        if not isinstance(lora.name, str) or not _LORA_NAME.fullmatch(lora.name):
            raise ValueError(f"{lora.name!r}: a LoRA name is lowercase words joined by hyphens")

        if lora.name in loras:
            raise ValueError(f"duplicated LoRA {lora.name}")

        if lora.base != "sdxl":
            raise ValueError(f"{lora.name}: base must be sdxl")

        parts = lora.dest.split("/")

        if (
            parts[0] != "loras"
            or len(parts) < 2
            or any(part in ("", ".", "..") for part in parts)
            or "\\" in lora.dest
        ):
            raise ValueError(f"{lora.name}: dest must be a path under loras/")

        if lora.dest in destinations:
            raise ValueError(f"{lora.name}: dest {lora.dest} is already used")

        destinations.add(lora.dest)

        if (
            isinstance(weight, bool)
            or not isinstance(weight, (int, float))
            or not 0 <= weight <= MAX_LORA_WEIGHT
        ):
            raise ValueError(f"{lora.name}: weight must be between 0 and {MAX_LORA_WEIGHT:g}")

        for key in ("description", "category", "repo", "filename"):
            if not isinstance(getattr(lora, key), str) or not getattr(lora, key).strip():
                raise ValueError(f"{lora.name}: {key} is empty")

        if not _SHA256.fullmatch(lora.sha256):
            raise ValueError(f"{lora.name}: invalid sha256")

        if not _REVISION.fullmatch(lora.revision):
            raise ValueError(f"{lora.name}: revision must be a full commit hash")

        if lora.license not in licenses:
            raise ValueError(f"{lora.name}: unknown license {lora.license}")

        if not licenses[lora.license].commercial:
            raise ValueError(f"{lora.name}: only licenses that allow commercial use")

        if not isinstance(lora.bytes, int) or lora.bytes <= 0:
            raise ValueError(f"{lora.name}: invalid size")

        loras[lora.name] = lora

    return loras


def _parse_catalog(entries, models, nodes, licenses):
    """The catalog by capability: models with capabilities, precisions and measured data."""
    catalog = {}

    for name, entry in entries.items():
        capabilities = tuple(entry["capabilities"])

        if not capabilities or any(item not in CAPABILITIES for item in capabilities):
            raise ValueError(f"{name}: capabilities must be some of {', '.join(CAPABILITIES)}")

        if len(set(capabilities)) != len(capabilities):
            raise ValueError(f"{name}: a capability is repeated")

        if entry["license"] not in licenses:
            raise ValueError(f"{name}: unknown license {entry['license']}")

        options = []

        for raw in entry.get("options", ()):
            weights = tuple(models[item] for item in raw["models"])
            workflows = dict(raw["workflow"])

            if set(workflows) != set(capabilities):
                raise ValueError(
                    f"{name} {raw['precision']}: needs a workflow for exactly "
                    f"{', '.join(capabilities)}"
                )

            for item in weights:
                if item.license not in licenses:
                    raise ValueError(f"{item.name}: unknown license {item.license}")

            loaders = dict(raw.get("loaders", {}))

            for weight in loaders.values():
                if weight not in models:
                    raise ValueError(f"{name} {raw['precision']}: unknown loader weight {weight}")

            options.append(
                CatalogOption(
                    raw["precision"],
                    raw["min_vram_mib"],
                    weights,
                    workflows,
                    tuple(nodes[item] for item in raw.get("nodes", ())),
                    loaders,
                    {cap: {int(k): v for k, v in table.items()} for cap, table in raw.get("seconds", {}).items()},
                    {cap: {int(k): v for k, v in table.items()} for cap, table in raw.get("vram_mib", {}).items()},
                    {cap: {int(k): v for k, v in table.items()} for cap, table in raw.get("offload_mib", {}).items()},
                )
            )

        if not options:
            raise ValueError(f"{name}: no options")

        precisions = [normalize_precision(item.precision) for item in options]

        if len(set(precisions)) != len(precisions):
            raise ValueError(f"{name}: a precision is repeated")

        catalog[name] = CatalogModel(
            name,
            entry["title"],
            entry["license"],
            capabilities,
            tuple(options),
            entry.get("max_references"),
        )

    return catalog


def parse(values):
    """Convierte y valida el contenido del manifiesto."""
    try:
        licenses = {
            key: License(
                key, entry["name"], entry["url"], entry["summary"], entry.get("commercial", True)
            )
            for key, entry in values["licenses"].items()
        }
        models = {}

        for entry in values["models"]:
            model = Model(
                entry["name"],
                entry["repo"],
                entry["revision"],
                entry["filename"],
                entry["dest"],
                entry["bytes"],
                entry["sha256"],
                entry["license"],
                tuple(entry.get("workflows", ())),
                tuple(entry.get("requires", ())),
                entry.get("legacy", False),
            )

            if model.name in models:
                raise ValueError(f"duplicated model {model.name}")

            if not _SHA256.fullmatch(model.sha256):
                raise ValueError(f"{model.name}: invalid sha256")

            if not _REVISION.fullmatch(model.revision):
                raise ValueError(f"{model.name}: revision must be a full commit hash")

            if model.license not in licenses:
                raise ValueError(f"{model.name}: unknown license {model.license}")

            if not isinstance(model.bytes, int) or model.bytes <= 0:
                raise ValueError(f"{model.name}: invalid size")

            models[model.name] = model

        for model in models.values():
            for name in model.requires:
                if name not in models:
                    raise ValueError(f"{model.name}: unknown required model {name}")

        loras = _parse_loras(values.get("loras", ()), licenses, models)

        nodes = {
            name: NodePin(
                name,
                entry["folder"],
                entry["url"],
                entry["sha256"],
                entry["license"],
                tuple(entry["packages"]),
            )
            for name, entry in values.get("nodes", {}).items()
        }

        for node in nodes.values():
            if not _SHA256.fullmatch(node.sha256):
                raise ValueError(f"{node.name}: invalid sha256")

            if node.license not in licenses:
                raise ValueError(f"{node.name}: unknown license {node.license}")

        profiles = {
            name: Profile(
                name,
                entry["description"],
                entry["min_vram_mib"],
                tuple(models[item] for item in entry["models"]),
                tuple(entry["platforms"]),
                tuple(nodes[item] for item in entry.get("nodes", ())),
                entry.get("variant_of"),
                entry.get("quality", False),
                entry.get("edit", False),
                capabilities=tuple(entry.get("capabilities", ())),
                fixed=tuple(
                    (cap, tuple(texts)) for cap, texts in entry.get("fixed", {}).items()
                ),
            )
            for name, entry in values["profiles"].items()
        }

        def options(entries):
            found = tuple(
                Option(
                    entry["precision"],
                    entry["min_vram_mib"],
                    tuple(models[item] for item in entry["models"]),
                    tuple(nodes[item] for item in entry.get("nodes", ())),
                    entry.get("workflow"),
                )
                for entry in entries
            )
            return tuple(sorted(found, key=lambda item: -item.min_vram_mib))

        quality_models = {
            name: QualityModel(
                name,
                entry["title"],
                entry["license"],
                entry["recommended_from_mib"],
                options(entry["options"]),
            )
            for name, entry in values.get("quality_models", {}).items()
        }

        for model in quality_models.values():
            if model.license not in licenses:
                raise ValueError(f"{model.name}: unknown license {model.license}")

            if not model.options:
                raise ValueError(f"{model.name}: no options")

        edit_options = options(values.get("edit", {}).get("options", ()))

        for profile in profiles.values():
            if profile.quality and not quality_models:
                raise ValueError(f"{profile.name}: the manifest has no quality models")

            if profile.edit and not edit_options:
                raise ValueError(f"{profile.name}: the manifest has no editing model")
        for profile in profiles.values():
            if profile.variant_of is not None and profile.variant_of not in profiles:
                raise ValueError(f"{profile.name}: unknown base profile {profile.variant_of}")

        catalog = _parse_catalog(values.get("catalog", {}), models, nodes, licenses)
        recommended = {
            capability: {int(level): text for level, text in table.items()}
            for capability, table in values.get("recommended", {}).items()
        }

        for capability, table in recommended.items():
            if capability not in CAPABILITIES:
                raise ValueError(f"recommended: unknown capability {capability}")

            for text in table.values():
                name, _, precision = text.partition(":")

                if name not in catalog or capability not in catalog[name].capabilities:
                    raise ValueError(f"recommended.{capability}: {name} doesn't have it")

                if precision and catalog[name].option(precision) is None:
                    raise ValueError(f"recommended.{capability}: {text} has no such precision")

        for profile in profiles.values():
            for capability in profile.capabilities:
                if capability not in CAPABILITIES:
                    raise ValueError(f"{profile.name}: unknown capability {capability}")

            for capability, texts in profile.fixed:
                for text in texts:
                    name, _, precision = text.partition(":")

                    if name not in catalog or catalog[name].option(precision) is None:
                        raise ValueError(f"{profile.name}: unknown fixed model {text}")

        comfy = values["comfyui"]
        comfyui = ComfyPin(
            comfy["version"],
            comfy["url"],
            comfy["sha256"],
            comfy["license"],
            comfy["install_bytes"],
        )

        if not _SHA256.fullmatch(comfyui.sha256):
            raise ValueError("comfyui: invalid sha256")

        if comfyui.license not in licenses:
            raise ValueError(f"comfyui: unknown license {comfyui.license}")

        pytorch = {
            name: TorchPin(
                entry["python"],
                entry["index"],
                tuple(entry["packages"]),
                entry.get("min_driver"),
                entry.get("install_bytes"),
            )
            for name, entry in values["pytorch"].items()
        }
    except (KeyError, TypeError, ValueError) as error:
        raise ProvisionError(f"Invalid models.toml: {error!r}") from error

    return Manifest(
        comfyui,
        pytorch,
        licenses,
        models,
        profiles,
        nodes,
        quality_models,
        edit_options,
        loras,
        catalog,
        recommended,
    )


def _check_workflow_files(loaded):
    """Every workflow the catalog names must ship with the package."""
    folder = resources.files("imagehearth_mcp") / "data" / "workflows"

    for model in loaded.catalog.values():
        for option in model.options:
            for workflow in option.workflows.values():
                if not (folder / f"{workflow}.json").is_file():
                    raise ProvisionError(
                        f"Invalid models.toml: {model.name} {option.precision} names the "
                        f"workflow {workflow}, which is not in the package."
                    )


def load():
    try:
        source = resources.files("imagehearth_mcp") / "data" / "models.toml"

        with source.open("rb") as file:
            loaded = parse(tomllib.load(file))

        _check_workflow_files(loaded)
        return loaded
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ProvisionError(
            f"Can't read models.toml: {error}. Reinstall the package."
        ) from error


def format_size(size):
    return f"{size / 1_000_000_000:.1f} GB"
