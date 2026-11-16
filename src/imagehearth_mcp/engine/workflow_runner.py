import json
import random
import re
import struct
import uuid
import zlib
from dataclasses import dataclass, field
from pathlib import Path

from imagehearth_mcp.engine import catalog, comfyui_client, config
from imagehearth_mcp.engine import loras as lora_module
from imagehearth_mcp.engine.log import get_logger
from imagehearth_mcp.engine.orchestrator import generation_session
from imagehearth_mcp.engine.result import ImageResult
from imagehearth_mcp.engine.validation import (
    require_installed,
    validate_dimensions,
    validate_prompt,
)

log = get_logger("workflow")


def png_text_chunk(key, value):
    data = key.encode("latin-1") + b"\0" + value.encode("latin-1", "replace")
    body = b"tEXt" + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))


def model_label(workflow_name, model=None):
    """`name:precision` of the model a workflow ran with, or None if it isn't a catalog model."""
    if model is None:
        try:
            model = catalog.installed_for_workflow(workflow_name)
        except Exception:  # noqa: BLE001 - a stamp must never fail an image already made
            return None

    return model.label if model is not None else None


def stamp_png(path, workflow_name, loras=(), model=None):
    """Adds the workflow, model and LoRAs as PNG text, keeping what ComfyUI wrote."""
    if not workflow_name:
        return

    text = {"ImageHearth-Workflow": workflow_name}
    label = model_label(workflow_name, model)

    if label:
        text["ImageHearth-Model"] = label

    quality_model = catalog.quality_model_of(workflow_name)

    if quality_model:
        text["ImageHearth-Quality-Model"] = quality_model

    if loras:
        text["ImageHearth-LoRAs"] = lora_module.label(loras)

    data = Path(path).read_bytes()

    # IEND is the last chunk: 4 bytes of length, 4 of type, 0 of data and 4 of CRC.
    if not data.startswith(b"\x89PNG\r\n\x1a\n") or data[-8:-4] != b"IEND":
        return

    chunks = b"".join(png_text_chunk(key, value) for key, value in text.items())
    Path(path).write_bytes(data[:-12] + chunks + data[-12:])


def save_session_image(
    session, workflow, timeout, destination, workflow_name=None, loras=(), model=None
):
    """Ejecuta el workflow en la sesión y guarda su imagen verificada."""
    prompt_id = session.submit(workflow)
    log.info("Generation started: %s", prompt_id)

    image = comfyui_client.wait_for_image(
        prompt_id,
        timeout,
        on_poll=session.check_ollama,
    )
    session.prompt_finished()

    comfyui_client.download_image(image, destination)
    stamp_png(destination, workflow_name, loras, model)
    log.info("Image saved: %s", destination)

    try:
        comfyui_client.remove_output_copy(image)
    except OSError as error:
        session.warn(f"Could not delete the ComfyUI copy: {error}")

    return destination


# FLUX Schnell and SDXL 1.0 draw in a painterly or illustrated way when the prompt doesn't say
# "photo". For those workflows the "auto" style adds photographic cues, unless the prompt asks
# for another medium. FLUX Dev and SDXL Turbo are left as they are.
PHOTO_WORKFLOWS = ("flux_schnell", "sdxl_base", "sdxl_quality")
NEGATIVE_WORKFLOWS = ("sdxl_base", "sdxl_quality")
PHOTO_CUES = (
    "RAW photo, photorealistic, natural lighting, sharp focus, highly detailed, "
    "professional photography"
)
PHOTO_NEGATIVE = (
    "illustration, painting, drawing, cartoon, anime, 3d render, cgi, plastic skin, "
    "oversaturated, blurry, lowres, deformed"
)
OTHER_MEDIUM = re.compile(
    r"\b(paint\w*|watercolou?r\w*|oil|illustrat\w*|cartoon\w*|anime|manga|comic\w*|sketch\w*|"
    r"draw\w*|render\w*|3d|pixel\w*|vector|logo|icon|diagram|poster|pencil|ink|charcoal|"
    r"digital art|concept art|cel|low poly|isometric|collage|mosaic|stained glass|"
    r"photo\w*|cinematic still|film still)\b",
    re.IGNORECASE,
)
STYLES = ("auto", "photo", "none")


def apply_style(workflow_name, prompt, negative_prompt, style="auto", other_medium=False):
    """The prompt and negative prompt with photographic cues, when the style asks for them.

    `other_medium`: a LoRA already asks for a medium that isn't a photograph, so "auto"
    adds no cues.
    """
    if style not in STYLES:
        raise ValueError("style must be auto, photo or none.")

    name = workflow_name.removesuffix(".json")

    if style == "none" or name not in PHOTO_WORKFLOWS:
        return prompt, negative_prompt

    if style == "auto" and (other_medium or OTHER_MEDIUM.search(prompt)):
        return prompt, negative_prompt

    prompt = f"{prompt.rstrip().rstrip(',.')}, {PHOTO_CUES}"

    if name in NEGATIVE_WORKFLOWS:
        negative_prompt = ", ".join(part for part in (negative_prompt.strip(), PHOTO_NEGATIVE) if part)

    return prompt, negative_prompt


def negative_prompt_applies(workflow):
    has_negative_node = False
    uses_cfg = False

    for node in workflow.values():
        if not isinstance(node, dict):
            continue

        if node.get("class_type") == "CLIPTextEncode":
            has_negative_node |= node.get("inputs", {}).get("text") in ("", "%NEGATIVE%")

        if node.get("class_type") in ("KSampler", "CFGGuider"):
            uses_cfg |= node.get("inputs", {}).get("cfg", 1) > 1

    return has_negative_node and uses_cfg


MARKER = re.compile(r"%[A-Z0-9]+%")


def has_markers(workflow):
    """Whether the template uses %NAME% markers (the workflows of the newer models)."""
    return any(
        isinstance(value, str) and MARKER.fullmatch(value)
        for node in workflow.values()
        if isinstance(node, dict)
        for value in node.get("inputs", {}).values()
    )


def fill_markers(workflow, values):
    """Replace every %NAME% marker by its value. An unknown marker is an error."""

    def fill(item):
        if isinstance(item, dict):
            return {key: fill(value) for key, value in item.items()}

        if isinstance(item, list):
            return [fill(value) for value in item]

        if isinstance(item, str) and MARKER.fullmatch(item):
            key = item.strip("%")

            if key not in values:
                raise ValueError(f"The workflow has a {item} marker that nothing fills.")

            return values[key]

        return item

    return fill(workflow)


def loader_values(model):
    """The %UNET%, %CLIP%, %VAE%... markers of a model's workflows, from its installed files."""
    return {role.upper(): name for role, name in (model.loaders if model else {}).items()}


def prepare_marker_workflow(workflow, prompt, negative_prompt, width, height, filename, model):
    """Fill a template with markers: prompt, negative prompt, size, seed, prefix and files."""
    # An empty text is the negative prompt, as in the older templates.
    for node in workflow.values():
        if (
            isinstance(node, dict)
            and node.get("class_type") == "CLIPTextEncode"
            and node.get("inputs", {}).get("text") == ""
        ):
            node["inputs"]["text"] = negative_prompt

    values = {
        "PROMPT": prompt,
        "NEGATIVE": negative_prompt,
        "WIDTH": max(16, round(width / 16) * 16),
        "HEIGHT": max(16, round(height / 16) * 16),
        "SEED": random.randint(0, 2**64 - 1),
        "PREFIX": filename,
        **loader_values(model),
    }
    return fill_markers(workflow, values)


def prepare_workflow(workflow, prompt, negative_prompt, width, height, filename, model=None):
    """Rellena una plantilla ya cargada y la devuelve."""
    if has_markers(workflow):
        return prepare_marker_workflow(
            workflow, prompt, negative_prompt, width, height, filename, model
        )

    # Sustituir prompts.
    for node in workflow.values():
        if not isinstance(node, dict):
            continue

        if node.get("class_type") != "CLIPTextEncode":
            continue

        current_text = node.get("inputs", {}).get("text", "")
        node["inputs"]["text"] = negative_prompt if current_text == "" else prompt

    # Ajustar dimensiones para SDXL y FLUX.
    for node in workflow.values():
        if not isinstance(node, dict):
            continue

        class_type = node.get("class_type")
        inputs = node.get("inputs", {})

        if class_type in ("EmptyLatentImage", "EmptySD3LatentImage"):
            multiple = 16 if class_type == "EmptySD3LatentImage" else 8

            inputs["width"] = max(multiple, round(width / multiple) * multiple)
            inputs["height"] = max(multiple, round(height / multiple) * multiple)

        if class_type == "KSampler":
            inputs["seed"] = random.randint(0, 2**64 - 1)

    for node in workflow.values():
        if isinstance(node, dict) and node.get("class_type") == "SaveImage":
            node["inputs"]["filename_prefix"] = filename

    return workflow


LORA_NODE = "2"
FIRST_LORA_NODE = 100


def apply_loras(workflow, selected):
    """Chain a LoraLoader per LoRA behind the fixed detail LoRA (node "2").

    The text encoders and the sampler are rewired to the last one. Without LoRAs the
    workflow is left exactly as it is.
    """
    if not selected:
        return workflow

    base = workflow.get(LORA_NODE)

    if not isinstance(base, dict) or base.get("class_type") != "LoraLoader":
        raise ValueError("This workflow can't take LoRAs.")

    last = LORA_NODE

    for offset, item in enumerate(selected):
        node_id = str(FIRST_LORA_NODE + offset)
        workflow[node_id] = {
            "class_type": "LoraLoader",
            "inputs": {
                "lora_name": item.lora.lora_name,
                "strength_model": item.weight,
                "strength_clip": item.weight,
                "model": [last, 0],
                "clip": [last, 1],
            },
        }
        last = node_id

    for node in workflow.values():
        if not isinstance(node, dict):
            continue

        for key, value in node.get("inputs", {}).items():
            if node.get("class_type") == "LoraLoader" and key in ("model", "clip"):
                continue

            if isinstance(value, list) and len(value) == 2 and value[0] == LORA_NODE:
                node["inputs"][key] = [last, value[1]]

    return workflow


@dataclass
class PreparedWorkflow:
    """A validated generation request, ready to run in a session."""

    name: str
    workflow: dict
    image_id: str
    warnings: list[str] = field(default_factory=list)
    loras: tuple = ()
    # The installed catalog model it generates with, if it is one.
    model: object = None


def prepare_generation(
    workflow_name: str,
    prompt: str,
    negative_prompt: str = "",
    width: int = 1024,
    height: int = 1024,
    style: str = "auto",
    loras=(),
    model=None,
):
    """Validate the request and fill its template. Touches neither GPU nor session.

    `loras` are already-resolved `loras.Selected` items. `model` is the installed catalog
    model (from `catalog.resolve_model`); without it the workflow's own model is looked up.
    """
    validate_prompt(prompt)
    validate_dimensions(width, height)

    workflow_file = config.WORKFLOWS_DIR / workflow_name

    if not workflow_file.is_file():
        raise FileNotFoundError(workflow_file)

    require_installed(workflow_file.stem)

    image_id = uuid.uuid4().hex[:12]
    workflow = json.loads(workflow_file.read_text(encoding="utf-8"))
    warnings = []

    if model is None or model.workflow != workflow_file.stem:
        model = catalog.installed_for_workflow(workflow_file.stem)

    if has_markers(workflow) and model is None:
        raise ValueError(
            f"{workflow_file.stem} is not installed: its models are missing or incomplete."
        )

    # Antes de rellenarla: se reconoce el nodo negativo por su texto vacío.
    if negative_prompt and not negative_prompt_applies(workflow):
        warnings.append(f"{workflow_file.stem} ignores negative_prompt.")

    loras = tuple(loras)
    prompt, negative_prompt = apply_style(
        workflow_file.stem,
        prompt,
        negative_prompt,
        style,
        other_medium=bool(loras) and not lora_module.is_photographic(loras),
    )
    prompt = lora_module.with_trigger_words(prompt, loras)
    apply_loras(workflow, loras)

    workflow = prepare_workflow(
        workflow,
        prompt,
        negative_prompt,
        width,
        height,
        f"{config.COMFY_SUBFOLDER}/{image_id}",
        model,
    )

    return PreparedWorkflow(workflow_file.stem, workflow, image_id, warnings, loras, model)


def run_in_session(session, prepared, timeout=config.WORKFLOW_TIMEOUT):
    """Generate inside an open session. Only the request's own warnings are returned."""
    destination = save_session_image(
        session,
        prepared.workflow,
        timeout,
        config.OUTPUT_DIR / f"{prepared.image_id}.png",
        prepared.name,
        prepared.loras,
        prepared.model,
    )
    return ImageResult(destination, list(prepared.warnings))


def run_workflow(
    workflow_name: str,
    prompt: str,
    timeout: int = config.WORKFLOW_TIMEOUT,
    negative_prompt: str = "",
    width: int = 1024,
    height: int = 1024,
    style: str = "auto",
    loras=(),
    model=None,
):
    prepared = prepare_generation(
        workflow_name, prompt, negative_prompt, width, height, style, loras, model
    )

    with generation_session(prepared.name) as session:
        result = run_in_session(session, prepared, timeout)

    result.warnings.extend(session.warnings)
    return result
