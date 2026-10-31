"""ComfyUI gestionado (versión fijada, sin Git) y modo adjunto."""

import filecmp
import hashlib
import json
import shutil
import subprocess
import tarfile
from pathlib import Path

import requests

from imagehearth_mcp.engine import config
from imagehearth_mcp.platform import paths
from imagehearth_mcp.provisioner import ProvisionError

NODE_FILES = ("__init__.py", "LICENSE")
NODE_PIN_FILE = ".imagehearth-pin"
MODEL_FOLDERS = ("checkpoints", "diffusion_models", "text_encoders", "vae")
PARTIAL_SUFFIX = ".partial"
EXTRA_PATHS_FILE = "extra_model_paths.yaml"
# Lo que pertenece a la instalación y no a la versión de ComfyUI.
KEEP_ON_UPDATE = {
    "venv",
    "models",
    "custom_nodes",
    "user",
    "input",
    "output",
    EXTRA_PATHS_FILE,
}
DOWNLOAD_CHUNK = 1024 * 1024
DOWNLOAD_TIMEOUT = 60


def find_uv(which=shutil.which):
    uv = which("uv")

    if uv is None:
        raise ProvisionError(
            "uv was not found in PATH. Install it from "
            "https://docs.astral.sh/uv/getting-started/installation/ and run "
            "setup again."
        )

    return uv


def _run_uv(command, run):
    try:
        run(command, check=True)
    except (OSError, subprocess.CalledProcessError) as error:
        raise ProvisionError(
            f"This command failed: {' '.join(command)} ({error}). Check the output "
            "above, then run setup again."
        ) from error


def _download_archive(pin, destination):
    """Descarga el archivo fijado de ComfyUI o de un nodo y comprueba su SHA-256."""
    digest = hashlib.sha256()

    try:
        with requests.get(pin.url, stream=True, timeout=DOWNLOAD_TIMEOUT) as response:
            response.raise_for_status()

            with open(destination, "wb") as file:
                for chunk in response.iter_content(DOWNLOAD_CHUNK):
                    file.write(chunk)
                    digest.update(chunk)
    except requests.RequestException as error:
        raise ProvisionError(
            f"Can't download {pin.url}: {error}. Check your connection "
            "and run setup again."
        ) from error

    if digest.hexdigest() != pin.sha256:
        destination.unlink()
        raise ProvisionError(
            f"The archive from {pin.url} does not match the expected SHA-256. "
            "Run setup again; if it keeps failing, report it to ImageHearth."
        )


def _merge_missing(source, destination):
    """Copia a `destination` lo nuevo de `source` sin sobrescribir nada."""
    for item in source.rglob("*"):
        target = destination / item.relative_to(source)

        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)


def _apply_source(source, target):
    target.mkdir(parents=True, exist_ok=True)

    for item in target.iterdir():
        if item.name not in KEEP_ON_UPDATE:
            shutil.rmtree(item) if item.is_dir() else item.unlink()

    for item in source.iterdir():
        if item.name in KEEP_ON_UPDATE and item.is_dir():
            _merge_missing(item, target / item.name)
        elif item.name not in KEEP_ON_UPDATE:
            shutil.move(str(item), str(target / item.name))


def _install_source(pin, target, fetch, records):
    partial = target.with_name(target.name + PARTIAL_SUFFIX)
    shutil.rmtree(partial, ignore_errors=True)
    records.claim_verified("staging", partial)
    partial.mkdir(parents=True)

    try:
        archive = partial / "comfyui.tar.gz"
        fetch(pin, archive)
        extracted = partial / "source"

        with tarfile.open(archive) as tar:
            tar.extractall(extracted, filter="data")

        top = next(extracted.iterdir())
        _apply_source(top, target)
    except (OSError, tarfile.TarError, StopIteration) as error:
        raise ProvisionError(
            f"Can't install ComfyUI in {target}: {error}. Run setup again."
        ) from error
    finally:
        shutil.rmtree(partial, ignore_errors=True)
        records.forget(partial)
        records.save()


def install_environment(target, torch, run=subprocess.run, which=shutil.which):
    """Entorno con Python gestionado y el PyTorch del manifiesto. uv no repite nada."""
    uv = find_uv(which)
    venv = target / "venv"
    python = paths.venv_python(venv)

    if not python.exists():
        _run_uv(
            [uv, "venv", "--seed", "--managed-python", "--python", torch.python, str(venv)],
            run,
        )

    _run_uv(
        [
            uv,
            "pip",
            "install",
            "--python",
            str(python),
            "--default-index",
            torch.index,
            *torch.packages,
        ],
        run,
    )
    # Va aparte: el índice de PyTorch no tiene el resto de dependencias.
    _run_uv(
        [
            uv,
            "pip",
            "install",
            "--python",
            str(python),
            "-r",
            str(target / "requirements.txt"),
        ],
        run,
    )


def _node_destination(comfy_dir):
    return Path(comfy_dir) / "custom_nodes" / config.STATUS_NODE


def node_is_current(comfy_dir):
    installed = _node_destination(comfy_dir) / "__init__.py"
    return installed.exists() and filecmp.cmp(
        config.data_path(config.STATUS_NODE, "__init__.py"), installed, shallow=False
    )


def install_node(comfy_dir, records, allowed=True):
    """Instala el nodo. Sin permiso, solo actualiza el que ya es propio.

    Devuelve False si el nodo correcto no ha quedado instalado.
    """
    source = config.data_path(config.STATUS_NODE)
    destination = _node_destination(comfy_dir)

    if node_is_current(comfy_dir):
        records.note_preexisting("node", destination)
        return True

    if not allowed and not records.is_owned(destination):
        return False

    records.claim("node", destination)
    destination.mkdir(parents=True, exist_ok=True)

    for name in NODE_FILES:
        shutil.copy2(source / name, destination / name)

    return True


def custom_node_is_current(pin, comfy_dir):
    marker = Path(comfy_dir) / "custom_nodes" / pin.folder / NODE_PIN_FILE

    try:
        return marker.read_text(encoding="utf-8").strip() == pin.sha256
    except OSError:
        return False


def install_custom_node(
    pin,
    comfy_dir,
    records,
    allowed=True,
    *,
    run=subprocess.run,
    fetch=_download_archive,
    which=shutil.which,
):
    """Instala un nodo fijado y sus dependencias. Uno ajeno nunca se sustituye.

    Devuelve False si el nodo no ha quedado disponible.
    """
    comfy_dir = Path(comfy_dir)
    destination = comfy_dir / "custom_nodes" / pin.folder
    owned = records.is_owned(destination)

    if destination.exists() and not owned:
        records.note_preexisting("node", destination)
        print(f"Using the {pin.folder} already in {destination}; it won't be changed.")
        return True

    if not allowed and not owned:
        return False

    python = paths.find_venv_python(comfy_dir)

    if not python.exists():
        print(f"WARNING: {pin.folder} needs a Python environment and {python} is missing.")
        return False

    if not custom_node_is_current(pin, comfy_dir):
        print(f"Installing {pin.folder}...")
        partial = destination.with_name(destination.name + PARTIAL_SUFFIX)
        shutil.rmtree(partial, ignore_errors=True)
        records.claim_verified("staging", partial)
        partial.mkdir(parents=True)

        try:
            archive = partial / "node.tar.gz"
            fetch(pin, archive)

            with tarfile.open(archive) as tar:
                tar.extractall(partial / "source", filter="data")

            top = next((partial / "source").iterdir())
            (top / NODE_PIN_FILE).write_text(pin.sha256, encoding="utf-8")
            records.claim("node", destination)
            shutil.rmtree(destination, ignore_errors=True)
            shutil.move(str(top), str(destination))
        except (OSError, tarfile.TarError, StopIteration) as error:
            raise ProvisionError(
                f"Can't install {pin.folder} in {destination}: {error}. Run setup again."
            ) from error
        finally:
            shutil.rmtree(partial, ignore_errors=True)
            records.forget(partial)
            records.save()

    _run_uv(
        [find_uv(which), "pip", "install", "--python", str(python), *pin.packages],
        run,
    )
    return True


def install_managed(pin, torch, target, records, *, run=subprocess.run, fetch=_download_archive, which=shutil.which):
    target = Path(target)

    # Un `uninstall` anterior puede haber conservado solo la carpeta de modelos.
    contents = {item.name for item in target.iterdir()} if target.exists() else set()

    if contents - {"models"} and not records.is_owned(target):
        raise ProvisionError(
            f"{target} has files that setup did not install, so it won't be changed. "
            f"If it is a ComfyUI, use it with --attach {target}."
        )

    find_uv(which)
    records.claim_verified("comfyui", target)

    if records.comfyui_version != pin.version or not (target / "main.py").exists():
        print(f"Installing ComfyUI {pin.version} in {target}...")
        _install_source(pin, target, fetch, records)
        records.comfyui_version = pin.version
        records.save()

    install_environment(target, torch, run, which)
    install_node(target, records)


def extra_paths_block(models_dir):
    folders = "\n".join(f"    {name}: {name}" for name in MODEL_FOLDERS)
    return (
        "imagehearth:\n"
        f"    base_path: {json.dumps(str(models_dir))}\n"
        f"{folders}\n"
    )


def write_extra_model_paths(comfy_dir, models_dir, records):
    """Comparte `models_dir` con ComfyUI. Un archivo ajeno nunca se modifica.

    Devuelve None si ya queda configurado, o el bloque que hay que añadir a mano.
    """
    path = Path(comfy_dir) / EXTRA_PATHS_FILE
    block = extra_paths_block(models_dir)

    if path.exists():
        if json.dumps(str(models_dir)) in path.read_text(encoding="utf-8"):
            return None

        return block

    records.claim("config", path)
    path.write_text(block, encoding="utf-8")
    return None
