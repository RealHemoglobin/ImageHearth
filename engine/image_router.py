from pathlib import Path
import re

from engine.kontext import generate as edit_with_kontext
from engine.workflow_runner import run_workflow


ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS_DIR = ROOT / "workflows"

DEFAULT_WIDTH = 1024
DEFAULT_HEIGHT = 1024
MAX_DIMENSION = 4096
MAX_REFERENCES = 6


def validate_prompt(prompt):
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("El prompt no puede estar vacío.")


def validate_dimensions(width, height, allow_zero=False):
    minimum = 0 if allow_zero else 64

    for name, value in (("width", width), ("height", height)):
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"{name} debe ser un número entero.")

        if value < minimum or value > MAX_DIMENSION:
            raise ValueError(
                f"{name} debe estar entre {minimum} y {MAX_DIMENSION}."
            )


def resolve_workflow(workflow, quality):
    if workflow:
        if not isinstance(workflow, str):
            raise ValueError("workflow debe ser un nombre de workflow.")

        if not re.fullmatch(r"[A-Za-z0-9_-]+", workflow):
            raise ValueError("Nombre de workflow no válido.")

        selected = workflow
    else:
        selected = "sdxl_turbo" if quality == "fast" else "flux_dev"

    workflow_file = WORKFLOWS_DIR / f"{selected}.json"

    if not workflow_file.is_file():
        available = sorted(
            path.stem for path in WORKFLOWS_DIR.glob("*.json")
        )
        raise ValueError(
            f"Workflow '{selected}' no disponible. "
            f"Workflows existentes: {available}"
        )

    return selected


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
    """

    validate_prompt(prompt)

    if mode not in ("auto", "generate", "edit"):
        raise ValueError("mode debe ser auto, generate o edit.")

    if quality not in ("fast", "high"):
        raise ValueError("quality debe ser fast o high.")

    references = list(image_paths or [])

    if len(references) > MAX_REFERENCES:
        raise ValueError(
            f"Se permiten como máximo {MAX_REFERENCES} referencias."
        )

    if mode == "auto":
        mode = "edit" if references else "generate"

    if mode == "edit":
        if not references:
            raise ValueError("El modo edit necesita referencias.")

        validate_dimensions(width, height, allow_zero=True)

        return str(
            edit_with_kontext(
                prompt=prompt,
                image_paths=references,
                width=width,
                height=height,
            )
        )

    if references:
        raise ValueError(
            "El modo generate no admite referencias. "
            "Utiliza mode=edit o mode=auto."
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
