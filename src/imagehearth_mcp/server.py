import asyncio

from mcp.server.fastmcp import FastMCP

from imagehearth_mcp.engine import config, orchestrator
from imagehearth_mcp.engine.image_router import create_image as route_image
from imagehearth_mcp.engine.status import get_status
from imagehearth_mcp.engine.validation import available_workflows

mcp = FastMCP("imagehearth")


# Las herramientas largas se ejecutan en un hilo para no bloquear el
# bucle de eventos de MCP. Una sesión cancelada termina su propia limpieza.
@mcp.tool()
async def generate_image(
    prompt: str,
    workflow: str = "sdxl_turbo",
    width: int = 1024,
    height: int = 1024,
    negative_prompt: str = "",
) -> str:
    """Generate a new image using a specific installed workflow.

    Which workflows exist depends on the installed profile: call list_workflows.
    If a workflow's models are missing, the error names the setup command that
    installs them.
    Returns the image path, followed by lines starting with WARNING
    if the image was created but something needs attention.
    """
    return await asyncio.to_thread(
        route_image,
        prompt=prompt,
        mode="generate",
        workflow=workflow,
        width=width,
        height=height,
        negative_prompt=negative_prompt,
    )


@mcp.tool()
async def edit_image(
    image_path: str,
    prompt: str,
    additional_images: list[str] | None = None,
    width: int = 0,
    height: int = 0,
) -> str:
    """Edit one or more images using FLUX Kontext.

    Needs the full profile; otherwise the error names the setup command to run.
    image_path: Primary reference image.
    additional_images: Up to five additional reference images.
    width and height: Optional output dimensions. Zero preserves
    the primary reference dimensions.
    Returns the image path, followed by lines starting with WARNING
    if the image was created but something needs attention.
    """
    references = [image_path]

    if additional_images:
        references.extend(additional_images)

    return await asyncio.to_thread(
        route_image,
        prompt=prompt,
        mode="edit",
        image_paths=references,
        width=width,
        height=height,
    )


@mcp.tool()
async def create_image(
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

    What works depends on the installed profile. If the models for the request
    are missing, the error names the setup command that installs them; another
    model is never used instead.
    image_paths: zero to six reference image paths.
    workflow: optionally override the automatic generation workflow.
    Returns the image path, followed by lines starting with WARNING
    if the image was created but something needs attention.
    """
    return await asyncio.to_thread(
        route_image,
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
    """List the generation workflows whose models are installed.

    It is checked on every call, so a later setup shows up without a restart.
    """
    return [
        {"name": name, "file": f"{name}.json"}
        for name in available_workflows()
    ]


@mcp.tool()
async def get_engine_status() -> dict:
    """Return the status of ImageHearth, ComfyUI and Ollama.

    Ollama is optional; its status is running, stopped or disabled.
    imageengine.status is ready, busy, degraded or recovery_required.
    """
    return await asyncio.to_thread(get_status)


@mcp.tool()
async def ensure_comfyui() -> str:
    """Start ComfyUI if it is not already running."""
    await asyncio.to_thread(orchestrator.ensure_comfyui)
    return f"ComfyUI is ready at {config.COMFY_API}"


@mcp.tool()
async def recover_engine() -> dict:
    """Resolve a pending session when the status is recovery_required.

    Releases ComfyUI and restores the interrupted Ollama models.
    Never loads Ollama while ComfyUI may still hold the GPU memory.
    """
    return await asyncio.to_thread(orchestrator.recover)

