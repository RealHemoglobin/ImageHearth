from dataclasses import dataclass, field

from imagehearth_mcp.engine import config
from imagehearth_mcp.engine.kontext import generate as edit_with_kontext
from imagehearth_mcp.engine.validation import (
    resolve_workflow,
    validate_dimensions,
    validate_prompt,
)
from imagehearth_mcp.engine.workflow_runner import run_workflow

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


def plan_request(
    prompt,
    mode="auto",
    quality="fast",
    image_paths=None,
    workflow="",
    width=0,
    height=0,
    negative_prompt="",
):
    """Check one image request and resolve its mode. Shared by create_image and batches."""
    validate_prompt(prompt)

    if mode not in ("auto", "generate", "edit"):
        raise ValueError("mode must be auto, generate or edit.")

    if quality not in ("fast", "high"):
        raise ValueError("quality must be fast or high.")

    references = list(image_paths or [])

    if len(references) > config.MAX_REFERENCES:
        raise ValueError(
            f"At most {config.MAX_REFERENCES} references are allowed."
        )

    if mode == "auto":
        mode = "edit" if references else "generate"

    if mode == "edit":
        if not references:
            raise ValueError("Edit mode needs reference images.")

        validate_dimensions(width, height, allow_zero=True)

        return Request(
            "edit", prompt, quality, references, "", width, height, negative_prompt
        )

    if references:
        raise ValueError(
            "Generate mode does not accept reference images. "
            "Use mode=edit or mode=auto."
        )

    validate_dimensions(width or DEFAULT_WIDTH, height or DEFAULT_HEIGHT)

    return Request(
        "generate",
        prompt,
        quality,
        [],
        resolve_workflow(workflow, quality),
        width or DEFAULT_WIDTH,
        height or DEFAULT_HEIGHT,
        negative_prompt,
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
):
    """
    Central image generation and editing router.

    mode:
        auto: edit when references exist, otherwise generate.
        generate: generate a new image.
        edit: edit one or more references using FLUX Kontext.

    quality:
        fast: SDXL Turbo.
        high: FLUX Dev.

    Dimensions:
        Generation defaults to 1024x1024.
        Editing preserves the first reference dimensions when omitted.

    Returns the image path, followed by one warning per line if any.
    """

    request = plan_request(
        prompt, mode, quality, image_paths, workflow, width, height, negative_prompt
    )

    if request.mode == "edit":
        result = edit_with_kontext(
            prompt=request.prompt,
            image_paths=request.references,
            width=request.width,
            height=request.height,
        )

        if request.negative_prompt:
            result.warnings.insert(0, "FLUX Kontext ignores negative_prompt.")

        return str(result)

    return str(
        run_workflow(
            workflow_name=f"{request.workflow}.json",
            prompt=request.prompt,
            width=request.width,
            height=request.height,
            negative_prompt=request.negative_prompt,
        )
    )
