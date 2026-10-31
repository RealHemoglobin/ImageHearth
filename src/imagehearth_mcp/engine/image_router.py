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

        result = edit_with_kontext(
            prompt=prompt,
            image_paths=references,
            width=width,
            height=height,
        )

        if negative_prompt:
            result.warnings.insert(0, "FLUX Kontext ignores negative_prompt.")

        return str(result)

    if references:
        raise ValueError(
            "Generate mode does not accept reference images. "
            "Use mode=edit or mode=auto."
        )

    validate_dimensions(width or DEFAULT_WIDTH, height or DEFAULT_HEIGHT)

    selected = resolve_workflow(workflow, quality)

    return str(
        run_workflow(
            workflow_name=f"{selected}.json",
            prompt=prompt,
            width=width or DEFAULT_WIDTH,
            height=height or DEFAULT_HEIGHT,
            negative_prompt=negative_prompt,
        )
    )
