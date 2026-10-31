import asyncio
import io
from pathlib import Path

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.utilities.types import Image
from PIL import Image as PILImage

from imagehearth_mcp.engine import catalog, config, orchestrator, progress
from imagehearth_mcp.engine.image_router import create_image as route_image
from imagehearth_mcp.engine.status import get_status
from imagehearth_mcp.engine.validation import available_workflows

INSTRUCTIONS = """\
ImageHearth generates and edits images locally on this computer.

Use create_image for every image request. To edit, pass the existing files in \
image_paths. Don't call ComfyUI directly or unload language models yourself: \
ImageHearth frees the GPU and gives the memory back when it finishes. If you are a \
local model, this works while you are loaded, so calling it is safe.

After a tool returns:
- The first line is the path of the image. Always tell the user that path.
- Each following line starting with WARNING: means the image exists but something \
needs attention. Tell the user and don't generate it again because of a warning.
- Only say an image exists if the tool returned a path.

If a tool fails:
- If the error names an `imagehearth-mcp setup` command, tell the user. Never use a \
different model instead.
- Otherwise call get_engine_status. recovery_required: call recover_engine, then \
retry once. busy: another image is being made, so wait before retrying. stopped \
ComfyUI: call ensure_comfyui. If it still fails, report the actual error.
- memory_mode manual: ImageHearth does not touch the user's models, so the user \
must free GPU memory.

Installing: setup_status shows what is missing, sizes and licenses. setup_start \
downloads many GB. Before calling it you MUST tell the user the profile, download \
size and licenses, ask them, and wait for a clear yes. Never accept licenses on \
their behalf.
"""

mcp = FastMCP("imagehearth", instructions=INSTRUCTIONS)

HEARTBEAT_SECONDS = 5
# Lado máximo de la copia que viaja al modelo; el original sigue en la ruta devuelta.
PREVIEW_SIDE = 1568


async def _run_generation(ctx, function, **arguments):
    """Ejecuta en un hilo para no bloquear MCP, informando de la etapa en curso.

    Enviar progreso mantiene viva la petición en los clientes que reinician su plazo
    con él. Al cancelar, la sesión del hilo se detiene y termina su propia limpieza.
    """
    tracker = progress.Tracker()

    async def heartbeat():
        elapsed = 0

        while True:
            await asyncio.sleep(HEARTBEAT_SECONDS)
            elapsed += HEARTBEAT_SECONDS
            await ctx.report_progress(elapsed, message=f"{tracker.stage} ({elapsed}s)")

    def work():
        with progress.tracking(tracker):
            return function(**arguments)

    reporter = asyncio.create_task(heartbeat()) if ctx is not None else None

    try:
        return await asyncio.to_thread(work)
    except asyncio.CancelledError:
        tracker.cancelled.set()
        raise
    finally:
        if reporter is not None:
            reporter.cancel()


def _preview(path):
    with PILImage.open(path) as image:
        copy = image.convert("RGB")

    copy.thumbnail((PREVIEW_SIDE, PREVIEW_SIDE))
    buffer = io.BytesIO()
    copy.save(buffer, "JPEG", quality=85)
    return Image(data=buffer.getvalue(), format="jpeg")


# Sin salida estructurada: la imagen opcional no cabe en un esquema de texto.
@mcp.tool(structured_output=False)
async def create_image(
    prompt: str,
    mode: str = "auto",
    quality: str = "fast",
    image_paths: list[str] | None = None,
    workflow: str = "",
    width: int = 0,
    height: int = 0,
    negative_prompt: str = "",
    include_image: bool = False,
    ctx: Context = None,
):
    """Create a new image or edit existing ones. Use this for every image request.

    Only prompt is required. To edit, put the existing files in image_paths.

    prompt: What to draw, or the change to make.
    quality: "fast" (SDXL Turbo, seconds) for drafts, "high" (FLUX Dev, slower)
      when the user wants a detailed result. Ignored when editing.
    image_paths: Up to six existing image files. Giving any makes this an edit
      with FLUX Kontext.
    width, height: Size in pixels, 64 to 4096. Default 1024x1024; editing keeps
      the size of the first image.
    mode: Leave as "auto". "generate" or "edit" force one of them.
    workflow: Leave empty. Only for a name returned by list_workflows.
    negative_prompt: What to avoid. Only SDXL Turbo applies it.
    include_image: true also returns the picture to you, for models with vision.
      It uses context, so leave it false unless you need to look at the result.

    If the models are missing, the error names the setup command to run; another
    model is never used instead.
    Returns the image path on the first line. Tell the user that path. Later lines
    starting with WARNING mean the image exists but something needs attention.
    """
    result = await _run_generation(
        ctx,
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

    if not include_image:
        return result

    path = Path(result.splitlines()[0])

    try:
        return [result, await asyncio.to_thread(_preview, path)]
    except OSError as error:
        return f"{result}\nWARNING: The image could not be attached: {error}"


@mcp.tool()
def list_workflows() -> list:
    """List the installed generation workflows. create_image doesn't need this.

    It is checked on every call, so a later setup shows up without a restart.
    If none is installed, the only item has a next_step saying what to do.
    """
    workflows = [
        {"name": name, "file": f"{name}.json"} for name in available_workflows()
    ]
    return workflows or [{"next_step": catalog.missing_installation()}]


@mcp.tool()
async def get_engine_status() -> dict:
    """Check why an image failed: ImageHearth, ComfyUI and local model servers.

    imageengine.status is one of:
    ready: working. busy: another image is being made, wait.
    not_installed: see imageengine.issues, or call setup_status.
    degraded: a problem, see imageengine.issues.
    recovery_required: call recover_engine.
    memory.mode says how local models are handled: auto, off or manual.
    """
    return await asyncio.to_thread(get_status)


@mcp.tool()
async def ensure_comfyui() -> str:
    """Start ComfyUI when get_engine_status says it is stopped.

    create_image starts it by itself, so this is rarely needed. If ComfyUI is not
    installed, the error names the command that installs it.
    """
    await asyncio.to_thread(orchestrator.ensure_comfyui)
    return f"ComfyUI is ready at {config.COMFY_API}"


@mcp.tool()
async def recover_engine() -> dict:
    """Fix an interrupted session. Only when get_engine_status says recovery_required.

    Releases ComfyUI and restores the language models that were unloaded.
    Never reloads them while ComfyUI may still hold the GPU memory.
    """
    return await asyncio.to_thread(orchestrator.recover)


@mcp.tool()
async def setup_status() -> dict:
    """Show what is installed, what is missing, and the progress of an installation.

    Lists each profile with its download size, licenses and whether it suits this
    hardware. Nothing is changed or downloaded.
    """
    # Se importa al usarse: el arranque del servidor no carga el provisioner.
    from imagehearth_mcp.provisioner import agent_setup

    return await asyncio.to_thread(agent_setup.status)


@mcp.tool()
async def setup_start(
    profile: str,
    accept_licenses: bool,
    existing_comfyui: str = "",
) -> dict:
    """Install ComfyUI and models. Downloads many GB: ask the user first.

    Before calling this, tell the user the profile, size and licenses shown by
    setup_status and wait for their clear yes. Never decide for them.
    profile: A profile from setup_status. Experimental profiles are refused.
    accept_licenses: true only if the user accepted the licenses.
    existing_comfyui: Folder of a ComfyUI to reuse, if setup_status found one and
      the user wants it. Empty installs a separate one.
    Returns at once. The installation continues even if you disconnect; follow it
    with setup_status.
    """
    from imagehearth_mcp.provisioner import agent_setup

    return await asyncio.to_thread(
        agent_setup.start, profile, accept_licenses, existing_comfyui
    )
