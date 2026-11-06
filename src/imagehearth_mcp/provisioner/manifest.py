"""Carga y valida `data/models.toml`."""

import dataclasses
import re
import tomllib
from dataclasses import dataclass, field
from importlib import resources

from imagehearth_mcp.provisioner import ProvisionError

_SHA256 = re.compile(r"[0-9a-f]{64}")
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
    workflows: tuple[str, ...]
    # Models this one needs besides itself (text encoders, VAE, LoRA).
    requires: tuple[str, ...] = ()
    # Kept in the manifest only so an old installation keeps generating.
    legacy: bool = False


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
                tuple(entry["workflows"]),
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
        comfyui, pytorch, licenses, models, profiles, nodes, quality_models, edit_options
    )


def load():
    try:
        source = resources.files("imagehearth_mcp") / "data" / "models.toml"

        with source.open("rb") as file:
            return parse(tomllib.load(file))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ProvisionError(
            f"Can't read models.toml: {error}. Reinstall the package."
        ) from error


def format_size(size):
    return f"{size / 1_000_000_000:.1f} GB"
