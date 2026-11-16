from dataclasses import dataclass, field

from imagehearth_mcp.engine import catalog, config, validation
from imagehearth_mcp.engine import loras as lora_module
from imagehearth_mcp.engine.kontext import generate as edit_with_kontext
from imagehearth_mcp.engine.validation import (
    require_installed,
    resolve_workflow,
    validate_dimensions,
    validate_prompt,
)
from imagehearth_mcp.engine.workflow_runner import STYLES, run_workflow

DEFAULT_WIDTH = 1024
DEFAULT_HEIGHT = 1024


@dataclass
class Request:
    """A request that passed the checks that need neither GPU nor installed models.

    For a generation, `workflow` is the template resolved for the quality.
    """

    mode: str
    prompt: str
    quality: str
    references: list = field(default_factory=list)
    workflow: str = ""
    width: int = 0
    height: int = 0
    negative_prompt: str = ""
    style: str = "auto"
    # Resolved `loras.Selected` items: installed, with their weight.
    loras: tuple = ()
    # The installed catalog model asked for with `model`, or None for the capability's default.
    model: object = None


def _plan_loras(loras, mode, quality):
    """The LoRAs of a generation, checked against everything but the GPU."""
    requested = lora_module.normalize(loras)

    if not requested:
        return ()

    if mode == "edit":
        raise ValueError("LoRAs only work when generating, not when editing images.")

    if quality != "high":
        raise ValueError(
            'LoRAs need quality="high" with the SDXL 1.0 quality model: "fast" '
            "(SDXL Turbo) doesn't take them."
        )

    return tuple(requested)


def _check_lora_model(workflow, model=None):
    """LoRAs only work with SDXL 1.0; say which model is in the way."""
    if workflow == lora_module.WORKFLOW:
        return

    installed = model if model is not None else catalog.installed_for_workflow(workflow)
    short = {"flux-dev": "FLUX Dev", "flux-schnell": "FLUX Schnell"}
    name = short.get(installed.name, installed.title) if installed is not None else workflow

    if workflow == "sdxl_quality":
        name = "RealVisXL"

    raise ValueError(
        f"LoRAs only work with the SDXL 1.0 quality model and this request uses {name}. "
        "SDXL 1.0 is installed with `imagehearth-mcp setup --quality-models sdxl`."
    )


def plan_request(
    prompt,
    mode="auto",
    quality="fast",
    image_paths=None,
    workflow="",
    width=0,
    height=0,
    negative_prompt="",
    style="auto",
    loras=None,
    model="",
):
    """Check one image request and resolve its mode. Shared by create_image and batches."""
    validate_prompt(prompt)

    if mode not in ("auto", "generate", "edit"):
        raise ValueError("mode must be auto, generate or edit.")

    if quality not in ("fast", "high"):
        raise ValueError("quality must be fast or high.")

    if style not in STYLES:
        raise ValueError("style must be auto, photo or none.")

    references = list(image_paths or [])

    if len(references) > config.MAX_REFERENCES:
        raise ValueError(
            f"At most {config.MAX_REFERENCES} references are allowed."
        )

    if mode == "auto":
        mode = "edit" if references else "generate"

    requested = _plan_loras(loras, mode, quality)

    if model not in (None, "") and workflow:
        raise ValueError(
            "model and workflow can't be combined: use model to choose an installed "
            "model, or leave both empty for the default."
        )

    if model is not None and not isinstance(model, str):
        raise ValueError("model must be a model name.")

    chosen = None

    if mode == "edit":
        if not references:
            raise ValueError("Edit mode needs reference images.")

        validate_dimensions(width, height, allow_zero=True)

        if model:
            chosen = validation.resolve_edit_model(model)
            _check_references(references, chosen)

        return Request(
            "edit", prompt, quality, references, "", width, height, negative_prompt,
            model=chosen,
        )

    if references:
        raise ValueError(
            "Generate mode does not accept reference images. "
            "Use mode=edit or mode=auto."
        )

    validate_dimensions(width or DEFAULT_WIDTH, height or DEFAULT_HEIGHT)
    selected = ()

    if model:
        chosen = catalog.resolve_model("high" if quality == "high" else "fast", model)
        resolved = chosen.workflow
        require_installed(resolved)
    else:
        resolved = resolve_workflow(workflow, quality)

    if requested:
        _check_lora_model(resolved, chosen)
        selected = tuple(lora_module.resolve(requested))

    return Request(
        "generate",
        prompt,
        quality,
        [],
        resolved,
        width or DEFAULT_WIDTH,
        height or DEFAULT_HEIGHT,
        negative_prompt,
        style,
        selected,
        chosen,
    )


def _check_references(references, model):
    limit = model.max_references or config.MAX_REFERENCES

    if len(references) > limit:
        raise ValueError(
            f"{model.title} takes at most {limit} reference image{'s' if limit != 1 else ''} "
            f"and this request has {len(references)}."
        )


def create_image(
    prompt: str,
    mode: str = "auto",
    quality: str = "fast",
    image_paths=None,
    workflow: str = "",
    width: int = 0,
    height: int = 0,
    negative_prompt: str = "",
    style: str = "auto",
    loras=None,
    model: str = "",
):
    """
    Central image generation and editing router.

    mode:
        auto: edit when references exist, otherwise generate.
        generate: generate a new image.
        edit: edit one or more references with the installed editing model.

    quality:
        fast: the default fast model (SDXL Turbo unless setup chose another).
        high: the default quality model.

    model:
        An installed model of the capability the request needs (fast, high or editing);
        empty uses that capability's default.

    Dimensions:
        Generation defaults to 1024x1024.
        Editing preserves the first reference dimensions when omitted.

    Returns the image path, followed by one warning per line if any.
    """

    request = plan_request(
        prompt, mode, quality, image_paths, workflow, width, height, negative_prompt, style,
        loras, model,
    )

    if request.mode == "edit":
        result = edit_with_kontext(
            prompt=request.prompt,
            image_paths=request.references,
            width=request.width,
            height=request.height,
            model=request.model,
            negative_prompt=request.negative_prompt,
        )
        return str(result)

    return str(
        run_workflow(
            workflow_name=f"{request.workflow}.json",
            prompt=request.prompt,
            width=request.width,
            height=request.height,
            negative_prompt=request.negative_prompt,
            style=request.style,
            loras=request.loras,
            model=request.model,
        )
    )
