import json
import random
import uuid

from imagehearth_mcp.engine import comfyui_client, config
from imagehearth_mcp.engine.log import get_logger
from imagehearth_mcp.engine.orchestrator import generation_session
from imagehearth_mcp.engine.result import ImageResult
from imagehearth_mcp.engine.validation import validate_dimensions, validate_prompt

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


def run_workflow(
    workflow_name: str,
    prompt: str,
    timeout: int = config.WORKFLOW_TIMEOUT,
    negative_prompt: str = "",
    width: int = 1024,
    height: int = 1024,
):
    validate_prompt(prompt)
    validate_dimensions(width, height)

    workflow_file = config.WORKFLOWS_DIR / workflow_name

    if not workflow_file.is_file():
        raise FileNotFoundError(workflow_file)

    workflow = json.loads(workflow_file.read_text(encoding="utf-8"))

    warnings = []

    if negative_prompt and not negative_prompt_applies(workflow):
        warnings.append(f"{workflow_file.stem} ignores negative_prompt.")

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

    image_id = uuid.uuid4().hex[:12]

    for node in workflow.values():
        if isinstance(node, dict) and node.get("class_type") == "SaveImage":
            node["inputs"]["filename_prefix"] = (
                f"{config.COMFY_SUBFOLDER}/{image_id}"
            )

    with generation_session() as session:
        destination = save_session_image(
            session,
            workflow,
            timeout,
            config.OUTPUT_DIR / f"{image_id}.png",
        )

    return ImageResult(destination, warnings + session.warnings)
