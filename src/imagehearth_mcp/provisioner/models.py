"""Descarga y verificación de modelos."""

import hashlib
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from imagehearth_mcp.platform import files
from imagehearth_mcp.provisioner import ProvisionError
from imagehearth_mcp.provisioner.manifest import format_size

STAGING_DIR = ".imagehearth-downloads"
HASH_CHUNK = 1024 * 1024

EXTRA_PATHS_FILE = "extra_model_paths.yaml"
# Nombres antiguos que ComfyUI sigue aceptando en ese archivo.
LEGACY_FOLDERS = {"unet": "diffusion_models", "clip": "text_encoders"}

PRESENT = "present"
WRONG_SIZE = "wrong_size"
MISSING = "missing"


@dataclass(frozen=True)
class ModelState:
    model: object
    path: Path
    state: str


def resolve_dir(records, comfy_dir):
    """Carpeta de modelos: la registrada por setup o la de ComfyUI."""
    return Path(records.models_dir) if records.models_dir else Path(comfy_dir) / "models"


def extra_search_paths(comfy_dir):
    """Carpetas adicionales de `extra_model_paths.yaml`, por tipo de modelo.

    Un archivo ausente o dañado no impide nada: ComfyUI tampoco lo aplicaría.
    """
    import yaml

    path = Path(comfy_dir) / EXTRA_PATHS_FILE

    try:
        values = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError):
        return {}

    found = {}

    for section in values.values() if isinstance(values, dict) else ():
        if not isinstance(section, dict):
            continue

        base = section.get("base_path")
        base = Path(os.path.expandvars(str(base))).expanduser() if base else Path()
        base = path.parent / base

        for folder, value in section.items():
            if folder in ("base_path", "is_default") or not isinstance(value, str):
                continue

            folders = found.setdefault(LEGACY_FOLDERS.get(folder, folder), [])
            folders.extend(base / line.strip() for line in value.splitlines() if line.strip())

    return found


def _candidates(model, models_dir, extra_paths):
    folder, _, name = model.dest.partition("/")
    return [
        Path(models_dir) / model.dest,
        *(Path(extra) / name for extra in (extra_paths or {}).get(folder, ())),
    ]


def inspect(models, models_dir, extra_paths=None):
    """Estado de cada modelo solo por tamaño: rápido y sin leer los archivos."""
    states = []

    for model in models:
        candidates = _candidates(model, models_dir, extra_paths)
        found = None

        for path in candidates:
            try:
                size = path.stat().st_size
            except OSError:
                continue

            if size == model.bytes:
                found = ModelState(model, path, PRESENT)
                break

            found = found or ModelState(model, path, WRONG_SIZE)

        states.append(found or ModelState(model, candidates[0], MISSING))

    return states


def pending_bytes(models, models_dir):
    return sum(
        item.model.bytes
        for item in inspect(models, models_dir)
        if item.state != PRESENT
    )


def sha256(path):
    digest = hashlib.sha256()

    with open(path, "rb") as file:
        while chunk := file.read(HASH_CHUNK):
            digest.update(chunk)

    return digest.hexdigest()


def _translate(error, model):
    from huggingface_hub.errors import (
        GatedRepoError,
        HfHubHTTPError,
        RepositoryNotFoundError,
    )

    if isinstance(error, (GatedRepoError, RepositoryNotFoundError)):
        return ProvisionError(
            f"Access to {model.repo} is restricted. Request access at "
            f"https://huggingface.co/{model.repo}, set HF_TOKEN to a token with "
            "access and run the command again."
        )

    if isinstance(error, HfHubHTTPError):
        return ProvisionError(
            f"Downloading {model.name} from {model.repo} failed: {error}. "
            "Run the same command again to continue."
        )

    return None


def hf_download(model, local_dir):
    """Descarga a un `.part` propio y lo devuelve; repetirla continúa donde quedó.

    `hf_hub_download` no sirve: desde la versión 2 usa un temporal con nombre
    aleatorio y lo borra al interrumpirse, así que empezaría de cero.
    """
    from huggingface_hub import hf_hub_url
    from huggingface_hub.file_download import http_get
    from huggingface_hub.utils import build_hf_headers

    part = Path(local_dir) / f"{model.name}.part"
    size = part.stat().st_size if part.exists() else 0

    if size > model.bytes:
        part.unlink()
        size = 0

    if size == model.bytes:
        return part

    if size:
        print(f"Resuming {model.name} from {format_size(size)}.")

    try:
        # No en modo "a": http_get retrocede si el servidor ignora el Range.
        with open(part, "r+b" if size else "wb") as file:
            file.seek(size)
            http_get(
                hf_hub_url(model.repo, model.filename, revision=model.revision),
                file,
                resume_size=size,
                headers=build_hf_headers(token=os.environ.get("HF_TOKEN") or None),
                expected_size=model.bytes,
                displayed_filename=model.name,
            )
    except Exception as error:
        translated = _translate(error, model)

        if translated is not None:
            raise translated from error

        raise

    return part


def _verify_present(item, records, report):
    """True si el archivo es correcto. Uno corrupto solo se borra si es propio."""
    report(f"Verifying {item.path.name}...")

    if item.state == PRESENT and sha256(item.path) == item.model.sha256:
        records.note_preexisting("model", item.path)
        return True

    if not records.is_owned(item.path):
        raise ProvisionError(
            f"{item.path} is not the expected file and setup did not install it, "
            "so it won't be touched. Move or delete it and run the command again."
        )

    report(f"{item.path.name} is corrupt: downloading it again.")
    item.path.unlink()
    return False


def ensure_models(models, models_dir, records, download=hf_download, report=print):
    """Deja cada modelo en su sitio y verificado. Se puede repetir sin coste."""
    models_dir = Path(models_dir)
    staging = models_dir / STAGING_DIR

    for item in inspect(models, models_dir):
        if item.state != MISSING and _verify_present(item, records, report):
            continue

        model = item.model
        report(f"Downloading {model.name} ({format_size(model.bytes)})...")
        records.claim("staging", staging)
        staging.mkdir(parents=True, exist_ok=True)
        downloaded = download(model, staging)

        if sha256(downloaded) != model.sha256:
            downloaded.unlink()
            raise ProvisionError(
                f"The download of {model.name} is corrupt (SHA-256 mismatch). "
                "Run the same command again to download it again."
            )

        item.path.parent.mkdir(parents=True, exist_ok=True)
        records.claim("model", item.path)
        files.replace(downloaded, item.path)

    if staging.exists():
        shutil.rmtree(staging)
        records.forget(staging)
        records.save()
