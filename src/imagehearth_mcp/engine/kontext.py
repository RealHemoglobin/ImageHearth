import json
import random
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import requests
from PIL import Image

from imagehearth_mcp.engine import comfyui_client, config
from imagehearth_mcp.engine.log import get_logger
from imagehearth_mcp.engine.orchestrator import generation_session
from imagehearth_mcp.engine.result import ImageResult
from imagehearth_mcp.engine.validation import (
    fit_to_limits,
    resolve_edit_model,
    validate_dimensions,
    validate_prompt,
)
from imagehearth_mcp.engine.workflow_runner import (
    fill_markers,
    has_markers,
    loader_values,
    save_session_image,
)

log = get_logger("kontext")

DEFAULT_WORKFLOW = "flux_kontext_dev_basic"
LOADERS = {
    "model": ("UNETLoader", "UnetLoaderGGUF"),
    "clip": ("DualCLIPLoader", "DualCLIPLoaderGGUF"),
    "vae": ("VAELoader",),
}
# Entrada de una sola imagen de la plantilla: se sustituye por las referencias.
TEMPLATE_INPUT_NODES = {
    "LoadImage",
    "ImageStitch",
    "FluxKontextImageScale",
    "VAEEncode",
    "ReferenceLatent",
}


def normalize_image_paths(image_path=None, image_paths=None, limit=None):
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

    limit = limit or config.MAX_REFERENCES

    if len(unique) > limit:
        who = "Kontext" if limit == config.MAX_REFERENCES else "This model"
        raise ValueError(f"{who} accepts at most {limit} images.")

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


def find_node(workflow, *class_types, role=None):
    """Identificador del único nodo de esos tipos.

    `role` distingue por el título varios nodos del mismo tipo, como el
    `CLIPTextEncode` positivo.
    """
    found = [
        node_id
        for node_id, node in workflow.items()
        if isinstance(node, dict) and node.get("class_type") in class_types
    ]

    if role and len(found) > 1:
        found = [
            node_id
            for node_id in found
            if role in workflow[node_id].get("_meta", {}).get("title", "").lower()
        ]

    names = " or ".join(class_types)

    if not found:
        raise RuntimeError(f"Required node {names} is missing from the Kontext workflow.")

    if len(found) > 1:
        raise RuntimeError(
            f"The Kontext workflow has several {names} nodes: {', '.join(found)}."
        )

    return found[0]


def find_loaders(workflow):
    """Salidas del cargador, sea estándar o GGUF: lo único que cambia entre variantes."""
    return {
        role: [find_node(workflow, *class_types), 0]
        for role, class_types in LOADERS.items()
    }


def build_workflow(
    uploaded_images,
    prompt,
    width,
    height,
    filename,
    workflow_name=DEFAULT_WORKFLOW,
):
    workflow_file = config.WORKFLOWS_DIR / f"{workflow_name}.json"
    workflow = json.loads(workflow_file.read_text(encoding="utf-8"))

    # Eliminar el antiguo camino basado en ImageStitch y VAEEncode único.
    for node_id, node in list(workflow.items()):
        if node.get("class_type") in TEMPLATE_INPUT_NODES:
            del workflow[node_id]

    loaders = find_loaders(workflow)
    positive_id = find_node(workflow, "CLIPTextEncode", role="positive")
    guidance_id = find_node(workflow, "FluxGuidance")
    sampler_id = find_node(workflow, "KSampler")
    find_node(workflow, "ConditioningZeroOut")
    find_node(workflow, "VAEDecode")
    save_id = find_node(workflow, "SaveImage")

    workflow[positive_id]["inputs"]["text"] = prompt
    workflow[positive_id]["inputs"]["clip"] = loaders["clip"]
    workflow[sampler_id]["inputs"]["seed"] = random.randint(0, 2**64 - 1)
    workflow[sampler_id]["inputs"]["model"] = loaders["model"]

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

    workflow[sampler_id]["inputs"]["latent_image"] = [latent_id, 0]

    # Encadenar referencias mediante ReferenceLatent.
    previous_conditioning = positive_id

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
                "vae": loaders["vae"],
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
    workflow[guidance_id]["inputs"]["conditioning"] = [
        previous_conditioning,
        0,
    ]

    workflow[save_id]["inputs"]["filename_prefix"] = filename

    return workflow


def build_marker_workflow(uploaded_images, prompt, filename, model, workflow_name):
    """An editing template with %NAME% markers (FLUX.2 Klein, Qwen-Image-Edit).

    The result takes the size of the reference, scaled by the workflow itself.
    """
    workflow = json.loads((config.WORKFLOWS_DIR / f"{workflow_name}.json").read_text(encoding="utf-8"))

    if len(uploaded_images) != 1:
        raise ValueError(f"{model.title} edits one image at a time.")

    values = {
        "PROMPT": prompt,
        "IMAGE": uploaded_images[0],
        "SEED": random.randint(0, 2**64 - 1),
        "PREFIX": filename,
        **loader_values(model),
    }
    return fill_markers(workflow, values)


@dataclass
class PreparedEdit:
    """A validated edit request, ready to run in a session."""

    workflow_name: str
    prompt: str
    paths: list
    width: int
    height: int
    image_id: str
    warnings: list[str] = field(default_factory=list)
    # The installed catalog model that edits.
    model: object = None


def _uses_markers(workflow_name):
    template = config.WORKFLOWS_DIR / f"{workflow_name}.json"
    return has_markers(json.loads(template.read_text(encoding="utf-8")))


def prepare_edit(
    prompt, image_path=None, image_paths=None, width=0, height=0, model=None, negative_prompt=""
):
    """Validate the request and its references. Touches neither GPU nor session.

    `model` is the installed editing model (`catalog.resolve_model("edit", ...)`); empty
    uses the default of the editing capability.
    """
    validate_prompt(prompt)
    model = model or resolve_edit_model()
    workflow_name = model.workflow
    limit = model.max_references

    paths = normalize_image_paths(image_path, image_paths, limit)
    asked_size = bool(width or height)
    width, height, warning = output_dimensions(paths[0], width, height)
    warnings = []

    if asked_size and _uses_markers(workflow_name):
        warnings.append(
            f"{model.title} keeps the size of the reference: width and height are ignored."
        )

    if negative_prompt:
        who = "FLUX Kontext" if model.name == "kontext" else model.title
        warnings.append(f"{who} ignores negative_prompt.")

    if warning:
        warnings.append(warning)

    return PreparedEdit(
        workflow_name=workflow_name,
        prompt=prompt,
        paths=paths,
        width=width,
        height=height,
        image_id=f"kontext_{uuid.uuid4().hex[:12]}",
        warnings=warnings,
        model=model,
    )


def run_in_session(session, prepared, timeout=config.KONTEXT_TIMEOUT):
    """Edit inside an open session. Only the request's own warnings are returned."""
    uploaded_images = [
        upload_image(path, index, session.run_id)
        for index, path in enumerate(prepared.paths, start=1)
    ]

    filename = f"{config.COMFY_SUBFOLDER}/{prepared.image_id}"

    if _uses_markers(prepared.workflow_name):
        workflow = build_marker_workflow(
            uploaded_images, prepared.prompt, filename, prepared.model, prepared.workflow_name
        )
    else:
        workflow = build_workflow(
            uploaded_images=uploaded_images,
            prompt=prepared.prompt,
            width=prepared.width,
            height=prepared.height,
            filename=filename,
            workflow_name=prepared.workflow_name,
        )

    log.info("Independent references: %s", len(prepared.paths))
    log.info("Output dimensions: %sx%s", prepared.width, prepared.height)

    destination = save_session_image(
        session,
        workflow,
        timeout,
        config.OUTPUT_DIR / f"{prepared.image_id}.png",
        prepared.workflow_name.removesuffix(".json"),
        model=prepared.model,
    )

    return ImageResult(destination, list(prepared.warnings))


def generate(
    prompt,
    image_path=None,
    timeout=config.KONTEXT_TIMEOUT,
    image_paths=None,
    width=0,
    height=0,
    model=None,
    negative_prompt="",
):
    prepared = prepare_edit(prompt, image_path, image_paths, width, height, model, negative_prompt)

    with generation_session(prepared.workflow_name) as session:
        result = run_in_session(session, prepared, timeout)

    result.warnings.extend(session.warnings)
    return result
