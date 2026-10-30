import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.kontext import generate as generate_kontext
from engine.workflow_runner import run_workflow
from engine.image_router import (
    create_image as route_image,
    resolve_workflow,
)
from engine.ollama_manager import get_loaded_models

mcp = FastMCP("ImageEngine")


@mcp.tool()
def generate_image(
    prompt: str,
    workflow: str = "sdxl_turbo",
    width: int = 1024,
    height: int = 1024,
    negative_prompt: str = "",
) -> str:
    """Generate a new image using a specific available workflow.

    Available workflows include sdxl_turbo and flux_dev.
    """
    selected = resolve_workflow(workflow, "fast")

    return run_workflow(
        workflow_name=f"{selected}.json",
        prompt=prompt,
        width=width,
        height=height,
        negative_prompt=negative_prompt,
    )

@mcp.tool()
def edit_image(
    image_path: str,
    prompt: str,
    additional_images: list[str] | None = None,
    width: int = 0,
    height: int = 0,
) -> str:
    """Edit one or more images using FLUX Kontext.

    image_path: Primary reference image.
    additional_images: Up to five additional reference images.
    width and height: Optional output dimensions. Zero preserves
    the primary reference dimensions.
    """
    references = [image_path]

    if additional_images:
        references.extend(additional_images)

    return str(
        generate_kontext(
            prompt=prompt,
            image_paths=references,
            width=width,
            height=height,
        )
    )

@mcp.tool()
def create_image(
    prompt: str,
    mode: str = "auto",
    quality: str = "fast",
    image_paths: list[str] | None = None,
    workflow: str = "",
    width: int = 0,
    height: int = 0,
    negative_prompt: str = "",
) -> str:
    """Intelligently generate or edit an image.

    mode:
      auto: edit when reference images are supplied, otherwise generate.
      generate: generate a new image.
      edit: edit supplied reference images with FLUX Kontext.

    quality:
      fast: SDXL Turbo.
      high: FLUX Dev.

    image_paths: zero to six reference image paths.
    workflow: optionally override the automatic generation workflow.
    """
    return route_image(
        prompt=prompt,
        mode=mode,
        quality=quality,
        image_paths=image_paths,
        workflow=workflow,
        width=width,
        height=height,
        negative_prompt=negative_prompt,
    )


@mcp.tool()
def list_workflows() -> list:
    """List available ImageEngine workflows."""
    workflows_dir = ROOT / "workflows"

    return [
        {"name": path.stem, "file": path.name}
        for path in sorted(workflows_dir.glob("*.json"))
    ]



@mcp.tool()
def get_engine_status() -> dict:
    """Return the status of ImageEngine, ComfyUI and Ollama."""
    import requests

    # ComfyUI
    try:
        response = requests.get(
            "http://127.0.0.1:8188/system_stats",
            timeout=3,
        )
        response.raise_for_status()

        comfy = {
            "status": "running",
            "gpu_devices": response.json().get("devices", []),
        }

    except requests.RequestException as error:
        comfy = {
            "status": "stopped",
            "error": str(error),
            "gpu_devices": [],
        }

    # Ollama
    try:
        response = requests.get(
            "http://127.0.0.1:11434/api/version",
            timeout=3,
        )
        response.raise_for_status()

        models = get_loaded_models()

        ollama = {
            "status": "running",
            "version": response.json().get("version"),
            "loaded_models": models,
        }

    except requests.RequestException as error:
        ollama = {
            "status": "stopped",
            "error": str(error),
            "loaded_models": [],
        }

    return {
        "comfyui": comfy,
        "ollama": ollama,
    }

@mcp.tool()
def ensure_comfyui() -> str:
    """Start ComfyUI if it is not already running."""
    from engine.comfyui_manager import start

    start()
    return "ComfyUI is ready at http://127.0.0.1:8188"


if __name__ == "__main__":
    mcp.run(transport="stdio")
