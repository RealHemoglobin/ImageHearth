"""Carga y valida `data/models.toml`."""

import re
import tomllib
from dataclasses import dataclass
from importlib import resources

from imagehearth_mcp.provisioner import ProvisionError

_SHA256 = re.compile(r"[0-9a-f]{64}")
_REVISION = re.compile(r"[0-9a-f]{40}")


@dataclass(frozen=True)
class License:
    key: str
    name: str
    url: str
    summary: str


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


@dataclass(frozen=True)
class Profile:
    name: str
    description: str
    min_vram_mib: int
    models: tuple[Model, ...]

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


@dataclass(frozen=True)
class Manifest:
    comfyui: ComfyPin
    pytorch: dict[str, TorchPin]
    licenses: dict[str, License]
    models: dict[str, Model]
    profiles: dict[str, Profile]

    def licenses_for(self, profile):
        keys = [self.comfyui.license]

        for model in profile.models:
            if model.license not in keys:
                keys.append(model.license)

        return [self.licenses[key] for key in keys]


def parse(values):
    """Convierte y valida el contenido del manifiesto."""
    try:
        licenses = {
            key: License(key, entry["name"], entry["url"], entry["summary"])
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

        profiles = {
            name: Profile(
                name,
                entry["description"],
                entry["min_vram_mib"],
                tuple(models[item] for item in entry["models"]),
            )
            for name, entry in values["profiles"].items()
        }
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
            )
            for name, entry in values["pytorch"].items()
        }
    except (KeyError, TypeError, ValueError) as error:
        raise ProvisionError(f"Invalid models.toml: {error!r}") from error

    return Manifest(comfyui, pytorch, licenses, models, profiles)


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
