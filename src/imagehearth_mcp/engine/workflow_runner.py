import json
import random
import uuid
from dataclasses import dataclass, field

from imagehearth_mcp.engine import comfyui_client, config
from imagehearth_mcp.engine.log import get_logger
from imagehearth_mcp.engine.orchestrator import generation_session
from imagehearth_mcp.engine.result import ImageResult
from imagehearth_mcp.engine.validation import (
    require_installed,
    validate_dimensions,
    validate_prompt,
)

log = get_logger("workflow")


def save_session_image(session, workflow, timeout, destination):
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
    log.info("Image saved: %s", destination)

    try:
        comfyui_client.remove_output_copy(image)
    except OSError as error:
        session.warn(f"Could not delete the ComfyUI copy: {error}")

    return destination


def negative_prompt_applies(workflow):
    has_negative_node = False
    uses_cfg = False

    for node in workflow.values():
        if not isinstance(node, dict):
            continue

        if node.get("class_type") == "CLIPTextEncode":
            has_negative_node |= node.get("inputs", {}).get("text") == ""

        if node.get("class_type") == "KSampler":
            uses_cfg |= node.get("inputs", {}).get("cfg", 1) > 1

    return has_negative_node and uses_cfg


def prepare_workflow(workflow, prompt, negative_prompt, width, height, filename):
    """Rellena una plantilla ya cargada y la devuelve."""
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


@dataclass
class PreparedWorkflow:
    """A validated generation request, ready to run in a session."""

    name: str
    workflow: dict
    image_id: str
    warnings: list[str] = field(default_factory=list)


def prepare_generation(
    workflow_name: str,
    prompt: str,
    negative_prompt: str = "",
    width: int = 1024,
    height: int = 1024,
):
    """Validate the request and fill its template. Touches neither GPU nor session."""
    validate_prompt(prompt)
    validate_dimensions(width, height)

    workflow_file = config.WORKFLOWS_DIR / workflow_name

    if not workflow_file.is_file():
        raise FileNotFoundError(workflow_file)

    require_installed(workflow_file.stem)

    image_id = uuid.uuid4().hex[:12]
    workflow = json.loads(workflow_file.read_text(encoding="utf-8"))
    warnings = []

    # Antes de rellenarla: se reconoce el nodo negativo por su texto vacío.
    if negative_prompt and not negative_prompt_applies(workflow):
        warnings.append(f"{workflow_file.stem} ignores negative_prompt.")

    prepare_workflow(
        workflow,
        prompt,
        negative_prompt,
        width,
        height,
        f"{config.COMFY_SUBFOLDER}/{image_id}",
    )

    return PreparedWorkflow(workflow_file.stem, workflow, image_id, warnings)


def run_in_session(session, prepared, timeout=config.WORKFLOW_TIMEOUT):
    """Generate inside an open session. Only the request's own warnings are returned."""
    destination = save_session_image(
        session,
        prepared.workflow,
        timeout,
        config.OUTPUT_DIR / f"{prepared.image_id}.png",
    )
    return ImageResult(destination, list(prepared.warnings))


def run_workflow(
    workflow_name: str,
    prompt: str,
    timeout: int = config.WORKFLOW_TIMEOUT,
    negative_prompt: str = "",
    width: int = 1024,
    height: int = 1024,
):
    prepared = prepare_generation(workflow_name, prompt, negative_prompt, width, height)

    with generation_session(prepared.name) as session:
        result = run_in_session(session, prepared, timeout)

    result.warnings.extend(session.warnings)
    return result
