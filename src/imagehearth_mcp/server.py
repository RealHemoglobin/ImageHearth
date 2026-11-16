import asyncio
import io
from pathlib import Path

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.utilities.types import Image
from PIL import Image as PILImage

from imagehearth_mcp.engine import batch, catalog, config, orchestrator, progress
from imagehearth_mcp.engine import loras as loras_module
from imagehearth_mcp.engine.image_router import create_image as route_image
from imagehearth_mcp.engine.status import get_status

INSTRUCTIONS = """\
ImageHearth generates and edits images locally on this computer.

create_image is the only image tool. When the user wants more than one image, or \
you have several to make, make ONE create_image call with a list of prompts in \
prompt, e.g. prompt=["a fox", "an owl"]. Never call it once per image: the single \
call returns when all are done and is much faster. For one image, pass a string. To \
edit, pass the existing files in image_paths. Don't call ComfyUI directly or \
unload language models yourself: ImageHearth frees the GPU and gives the memory back when it finishes. If you are a \
local model, this works while you are loaded, so calling it is safe.

After a tool returns:
- For one prompt, the first line is the path of the image. Always tell the user \
that path.
- For a list of prompts, there is one line per prompt in the order you gave: \
"3: /path.png" or "3: ERROR: reason". An error on one line doesn't affect the \
others; retry only those. Tell the user every path.
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

Models: more than one model can be installed for each of fast, high-quality and \
editing. Without `model`, create_image uses the default of what the request needs. \
When the user asks for a specific model, or you want to know what is available (speed, \
license, what each is for), call list_workflows once and pass the "model" name of one \
of its items in create_image(model=...) (or in an item of a prompt list). The model \
must be installed and have the capability the request needs: fast or high-quality \
generation (quality) or editing (image_paths). Never invent a model name, and don't \
combine model with workflow.

Styles: when the user asks for a style (pixel art, watercolor, anime...), call \
list_workflows and, if the "sdxl" item has a "loras" entry that fits, pass its name in \
create_image(loras=[...]) with quality="high" and model="sdxl" (or SDXL 1.0 as the \
default). LoRAs only work with SDXL 1.0. Never invent a LoRA name: if none fits, don't \
use one.

Installing: setup_status shows what is missing, sizes and licenses. setup_start \
downloads many GB. Before calling it you MUST tell the user the profile, the models \
for each capability (fast_models, quality_models, edit_models: the user can pick \
several of each, with the size, measured speed and license that setup_status shows), \
the total download size, the licenses and any warning that a model doesn't fit their \
GPU, say which ones are recommended, ask them, and wait for a clear yes. Never accept \
licenses or choose models on their behalf. On an existing installation the lists fix \
the set of each capability you pass: what isn't listed is deleted, so list the \
installed ones to keep. ComfyUI and the \
models take tens of GB: before setup_start also ask whether they want another folder \
or disk (setup_status install_folder shows the usual one and the disks with free \
space) and pass it as install_dir. Don't choose it for them. If the user chooses \
SDXL 1.0 (sdxl), also ask whether they want style LoRAs and which ones (setup_status \
loras has each one's size and license) and pass their names in loras; ["all"] installs \
every one. On an existing installation, loras fixes the set: the ones not listed are \
deleted, so list the installed ones you want to keep. loras needs sdxl among the \
quality models.
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
    prompt: str | list[str | dict],
    mode: str = "auto",
    quality: str = "fast",
    image_paths: list[str] | None = None,
    workflow: str = "",
    width: int = 0,
    height: int = 0,
    negative_prompt: str = "",
    include_image: bool = False,
    style: str = "auto",
    loras: list[str | dict] | None = None,
    model: str = "",
    ctx: Context = None,
):
    """Create or edit images. If you need more than one image, make ONE call with
    a list of prompts in prompt: never one call per image. The call waits and
    returns when all are done, and it is much faster than separate calls.

    One image: create_image(prompt="a red fox")
    Several:   create_image(prompt=["a red fox", "a blue whale", "an owl"])

    To edit, put the existing files in image_paths.

    prompt: One image: a string, what to draw or the change to make.
      Several images: a list with one string per image (up to 20 unless the user
      changed it), generated together in a single session. A list item can also be
      an object {"prompt": ..., "quality": ..., "width": ..., "height": ...,
      "negative_prompt": ..., "style": ..., "loras": ..., "image_paths": ..., "model": ...}
      to differ from the common values below. Items are independent: none can use the result of another
      (editing a result is a later call), and a list is all new images or all
      edits, never both.
    quality: "fast" (seconds) for drafts, "high" (a slower quality model) when the user
      wants a detailed result. Which model each uses is the default of that capability
      unless you pass model. Ignored when editing.
    model: An installed model name from list_workflows, to use instead of the default of
      what the request needs (fast, high or editing). Empty uses the default. It must be
      installed and have that capability, and can't be combined with workflow. Applies
      to every item of a list that doesn't have its own "model".
    image_paths: Existing image files to edit (up to six; some editing models take
      one). Giving any makes this an edit with the installed editing model.
    width, height: Size in pixels, 64 to 4096. Default 1024x1024; editing keeps
      the size of the first image.
    mode: Leave as "auto". "generate" or "edit" force one of them.
    style: "auto" (default) adds photographic cues for the FLUX Schnell and SDXL 1.0
      quality models, which otherwise draw in a painterly way, unless the prompt asks
      for another medium (painting, anime, illustration...). "photo" always adds
      them; "none" sends the prompt as written. Other models are never changed. For
      realism, still describe the scene like a photograph: subject, light, lens.
    loras: Style LoRAs, only with quality="high" and the SDXL 1.0 model (model="sdxl",
      or when it is the default; never with fast, FLUX or other models, or editing). A list of names, or objects with a weight:
      loras=["pixel-art", {"name": "watercolor", "weight": 0.6}]. Use only the
      names listed in list_workflows (the "loras" of the "sdxl" item), as
      they are installed; a name alone uses its recommended weight. At most 3 per image,
      each once, weight 0 to 2. The activation words are added to the prompt for you.
      Choose one when the user asks for the style it gives (pixel art, watercolor,
      anime...). Empty or omitted: none.
    workflow: Leave empty. Only for a name returned by list_workflows.
    negative_prompt: What to avoid. SDXL, Chroma, Qwen-Image and HiDream apply it; the
      FLUX and Z-Image models and editing ignore it.
    include_image: true also returns the picture to you, for models with vision.
      It uses context, so leave it false unless you need to look at the result.
      Only for a single prompt.

    If the models are missing, the error names the setup command to run; another
    model is never used instead.
    Returns the image path on the first line. Tell the user that path. Later lines
    starting with WARNING mean the image exists but something needs attention.
    With a list of prompts, the whole list is checked first (nothing is made if an
    item is invalid) and the result has one line per prompt in order:
    "1: /path/image.png" or "1: ERROR: reason". A failing item doesn't stop the
    others. "| WARNING: ..." after a path is about that image; WARNING lines at the
    end are about the whole call.
    """
    if isinstance(prompt, list):
        if include_image:
            raise ValueError("include_image only works with a single prompt.")

        result = await _run_generation(
            ctx,
            batch.run,
            items=prompt,
            quality=quality,
            width=width,
            height=height,
            negative_prompt=negative_prompt,
            image_paths=image_paths,
            workflow=workflow,
            mode=mode,
            style=style,
            loras=loras,
            model=model,
        )
        return str(result)

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
        style=style,
        loras=loras,
        model=model,
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
    """List the installed models, one item per model. create_image doesn't need this.

    It is checked on every call, so a later setup shows up without a restart. Each item:
    model (the name to pass in create_image(model=...)), capability (fast, high or
    edit), precision, default (true if create_image uses it when you don't pass model),
    license, commercial_use, seconds (measured time per image for this GPU, when
    known) and workflow (an internal name; leave it alone). The SDXL 1.0 item (model
    "sdxl") also has "loras": the installed style LoRAs, each with name, description,
    category, trigger_words and the recommended weight, to pass to
    create_image(loras=[...]). The list is empty if none is installed. If nothing is
    installed the only item has a next_step saying what to do.
    """
    items = catalog.installed_models()

    if not items:
        return [{"next_step": catalog.missing_installation()}]

    found = []

    for item in items:
        entry = {
            "model": item.name,
            "capability": item.capability,
            "precision": item.precision,
            "default": item.default,
            "workflow": item.workflow,
            "license": item.license,
            "commercial_use": item.commercial_use,
        }

        if item.seconds is not None:
            entry["seconds"] = item.seconds

        if item.capability == "high" and item.workflow == loras_module.WORKFLOW:
            entry["loras"] = loras_module.describe_installed()

        found.append(entry)

    return found


@mcp.tool()
async def get_engine_status() -> dict:
    """Check why an image failed: ImageHearth, ComfyUI and local model servers.

    imageengine.status is one of:
    ready: working. busy: another image is being made, wait.
    not_installed: see imageengine.issues, or call setup_status.
    degraded: a problem, see imageengine.issues.
    recovery_required: call recover_engine.
    imageengine.quality_model is the model quality="high" generates with, its license
    and whether it allows commercial use (null if none is installed).
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
    hardware. models has, per capability (fast, high = quality, edit), every model of the
    catalog with its precisions: download size, measured seconds per image for this GPU
    level, GPU memory and RAM use, license, commercial use, whether it fits this GPU, which
    one is recommended, and which are installed (and the default). installed_models
    summarizes what is installed. loras lists the style LoRAs for SDXL 1.0 (name,
    description, category, size, license) and which are installed. install_folder has the
    usual install folder, the disks found with their free space and, if installed, the
    current folder. Nothing is changed or downloaded.
    """
    # Se importa al usarse: el arranque del servidor no carga el provisioner.
    from imagehearth_mcp.provisioner import agent_setup

    return await asyncio.to_thread(agent_setup.status)


@mcp.tool()
async def setup_start(
    profile: str,
    accept_licenses: bool,
    existing_comfyui: str = "",
    quality_model: str = "",
    install_dir: str = "",
    loras: list[str] | None = None,
    fast_models: list[str] | None = None,
    quality_models: list[str] | None = None,
    edit_models: list[str] | None = None,
) -> dict:
    """Install ComfyUI and models. Downloads many GB: ask the user first.

    Before calling this, tell the user the profile, models, size and licenses shown by
    setup_status and wait for their clear yes. Never decide for them.
    profile: A profile from setup_status. Experimental profiles are refused.
    accept_licenses: true only if the user accepted the licenses.
    existing_comfyui: Folder of a ComfyUI to reuse, if setup_status found one and
      the user wants it. Empty installs a separate one.
    fast_models, quality_models, edit_models: The models to have for each capability, as
      names from setup_status "models" with an optional precision ("klein-4b",
      "qwen-image:q4_k_m"). The first of each list is the default. quality_models and
      edit_models need a profile that has them (quality, full). Empty or omitted: that
      capability is left as it is (a new installation gets the model recommended for the
      GPU). On an existing installation a list fixes the set of that capability: missing
      models are downloaded and verified first, then the ones not listed (or with another
      precision) are deleted, so include the installed ones the user wants to keep.
    quality_model: One quality model name, from earlier versions. Same as
      quality_models=[name].
    install_dir: Absolute folder where ComfyUI and the models go (ComfyUI ends up in
      install_dir/comfyui), if the user chose one from setup_status's install_folder.
      Empty uses the usual place. It is checked first (space, permissions, file system)
      and refused with the reason if it doesn't suit. On an existing installation a
      different folder is refused: the user moves it with `imagehearth-mcp update --move-to`.
    loras: Only with sdxl among the quality models: the style LoRAs to install, by name
      from setup_status (or ["all"]), as the user chose. Ask them first: each one has a
      size and a license. On an existing installation it fixes the set (downloads the
      missing ones and deletes the others); an empty list or omitting it changes nothing.
    Returns at once, with the models used and a warning if one doesn't fit the GPU: tell
    the user. The installation continues even if you disconnect; follow it with
    setup_status.
    """
    from imagehearth_mcp.provisioner import agent_setup

    return await asyncio.to_thread(
        agent_setup.start,
        profile,
        accept_licenses,
        existing_comfyui,
        quality_model,
        install_dir,
        loras,
        fast_models,
        quality_models,
        edit_models,
    )
