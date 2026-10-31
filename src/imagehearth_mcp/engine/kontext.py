import json
import random
import uuid
from pathlib import Path

import requests
from PIL import Image

from imagehearth_mcp.engine import comfyui_client, config
from imagehearth_mcp.engine.log import get_logger
from imagehearth_mcp.engine.orchestrator import generation_session
from imagehearth_mcp.engine.result import ImageResult
from imagehearth_mcp.engine.validation import (
    fit_to_limits,
    validate_dimensions,
    validate_prompt,
)
from imagehearth_mcp.engine.workflow_runner import save_session_image

log = get_logger("kontext")

WORKFLOW_FILE = config.WORKFLOWS_DIR / "flux_kontext_dev_basic.json"


def normalize_image_paths(image_path=None, image_paths=None):
    paths = []

    if image_path:
        paths.append(image_path)

    if image_paths:
        if isinstance(image_paths, (str, Path)):
            paths.append(image_paths)
        else:
            paths.extend(image_paths)

    unique = []
    seen = set()

    for path in paths:
        resolved = str(Path(path).expanduser().resolve())

        if resolved not in seen:
            seen.add(resolved)
            unique.append(Path(resolved))

    if not unique:
        raise ValueError("Provide at least one image.")

    if len(unique) > config.MAX_REFERENCES:
        raise ValueError(
            f"Kontext accepts at most {config.MAX_REFERENCES} images."
        )

    for path in unique:
        if not path.is_file():
            raise FileNotFoundError(path)

        try:
            with Image.open(path) as image:
                image.verify()
        except Exception as error:
            raise ValueError(f"Invalid image: {path}: {error}") from error

    return unique


def upload_image(image_path, index, run_id):
    """Sube la referencia a una carpeta exclusiva de esta ejecución."""
    image_path = Path(image_path)
    subfolder = comfyui_client.run_input_subfolder(run_id)
    name = f"reference_{index}{image_path.suffix.lower()}"

    with image_path.open("rb") as image:
        response = requests.post(
            f"{config.COMFY_API}/upload/image",
            files={"image": (name, image)},
            data={"subfolder": subfolder, "type": "input"},
            timeout=120,
        )

    response.raise_for_status()
    uploaded = response.json()
    return f"{uploaded['subfolder']}/{uploaded['name']}"


def output_dimensions(first_image, width=0, height=0):
    """Devuelve las dimensiones de salida y un aviso si se han reducido."""
    validate_dimensions(width, height, allow_zero=True)
    warning = None

    if not width or not height:
        with Image.open(first_image) as image:
            original_width, original_height = image.size

        inherited = (width or original_width, height or original_height)
        width, height = fit_to_limits(*inherited)

        if (width, height) != inherited:
            warning = (
                f"The {inherited[0]}x{inherited[1]} reference "
                f"was reduced to {width}x{height}."
            )

    # EmptySD3LatentImage requiere dimensiones múltiplos de 16.
    width = max(256, int(width / 16) * 16)
    height = max(256, int(height / 16) * 16)

    return width, height, warning


def build_workflow(uploaded_images, prompt, width, height, filename):
    workflow = json.loads(WORKFLOW_FILE.read_text(encoding="utf-8"))

    required_nodes = [
        "192:6",
        "192:35",
        "192:37",
        "192:38",
        "192:39",
        "192:135",
        "192:31",
        "192:8",
        "136",
    ]

    for node_id in required_nodes:
        if node_id not in workflow:
            raise RuntimeError(f"Required node {node_id} is missing from the Kontext workflow.")

    # Eliminar el antiguo camino basado en ImageStitch y VAEEncode único.
    for node_id in ("190", "192:146", "192:42", "192:124", "192:177"):
        workflow.pop(node_id, None)

    workflow["192:6"]["inputs"]["text"] = prompt
    workflow["192:31"]["inputs"]["seed"] = random.randint(0, 2**64 - 1)

    # Crear un latente de salida independiente de las referencias.
    latent_id = "IMAGEENGINE_EMPTY_LATENT"

    workflow[latent_id] = {
        "class_type": "EmptySD3LatentImage",
        "inputs": {
            "width": width,
            "height": height,
            "batch_size": 1,
        },
    }

    workflow["192:31"]["inputs"]["latent_image"] = [latent_id, 0]

    # Encadenar referencias mediante ReferenceLatent.
    previous_conditioning = "192:6"

    for index, uploaded_name in enumerate(uploaded_images, start=1):
        load_id = f"IMAGEENGINE_LOAD_{index}"
        scale_id = f"IMAGEENGINE_SCALE_{index}"
        encode_id = f"IMAGEENGINE_ENCODE_{index}"
        reference_id = f"IMAGEENGINE_REFERENCE_{index}"

        workflow[load_id] = {
            "class_type": "LoadImage",
            "inputs": {"image": uploaded_name},
        }

        workflow[scale_id] = {
            "class_type": "FluxKontextImageScale",
            "inputs": {
                "image": [load_id, 0],
            },
        }

        workflow[encode_id] = {
            "class_type": "VAEEncode",
            "inputs": {
                "pixels": [scale_id, 0],
                "vae": ["192:39", 0],
            },
        }

        workflow[reference_id] = {
            "class_type": "ReferenceLatent",
            "inputs": {
                "conditioning": [previous_conditioning, 0],
                "latent": [encode_id, 0],
            },
        }

        previous_conditioning = reference_id

    # El condicionamiento final contiene todas las referencias.
    workflow["192:35"]["inputs"]["conditioning"] = [
        previous_conditioning,
        0,
    ]

    workflow["136"]["inputs"]["filename_prefix"] = filename

    return workflow


def generate(
    prompt,
    image_path=None,
    timeout=config.KONTEXT_TIMEOUT,
    image_paths=None,
    width=0,
    height=0,
):
    validate_prompt(prompt)

    paths = normalize_image_paths(image_path, image_paths)
    width, height, warning = output_dimensions(paths[0], width, height)

    image_id = f"kontext_{uuid.uuid4().hex[:12]}"

    with generation_session() as session:
        uploaded_images = [
            upload_image(path, index, session.run_id)
            for index, path in enumerate(paths, start=1)
        ]

        workflow = build_workflow(
            uploaded_images=uploaded_images,
            prompt=prompt,
            width=width,
            height=height,
            filename=f"{config.COMFY_SUBFOLDER}/{image_id}",
        )

        log.info("Independent references: %s", len(paths))
        log.info("Output dimensions: %sx%s", width, height)

        destination = save_session_image(
            session,
            workflow,
            timeout,
            config.OUTPUT_DIR / f"{image_id}.png",
        )

    warnings = [warning] if warning else []
    return ImageResult(destination, warnings + session.warnings)

