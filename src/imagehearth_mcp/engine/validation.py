import re

from imagehearth_mcp.engine import config


def validate_prompt(prompt):
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("The prompt cannot be empty.")


def validate_dimensions(width, height, allow_zero=False):
    for name, value in (("width", width), ("height", height)):
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"{name} must be an integer.")

        if allow_zero and value == 0:
            continue

        if value < config.MIN_DIMENSION or value > config.MAX_DIMENSION:
            raise ValueError(
                f"{name} must be between {config.MIN_DIMENSION} "
                f"and {config.MAX_DIMENSION}."
            )

    if width * height > config.MAX_PIXELS:
        raise ValueError(
            f"{width}x{height} exceeds the maximum of {config.MAX_PIXELS} pixels."
        )


def fit_to_limits(width, height):
    """Reduce unas dimensiones heredadas manteniendo la proporción."""
    scale = min(
        1.0,
        config.MAX_DIMENSION / max(width, height),
        (config.MAX_PIXELS / (width * height)) ** 0.5,
    )
    return int(width * scale), int(height * scale)


def available_workflows():
    return sorted(
        path.stem
        for path in config.WORKFLOWS_DIR.glob("*.json")
        if path.stem not in config.INTERNAL_WORKFLOWS
    )


def resolve_workflow(workflow, quality):
    if workflow:
        if not isinstance(workflow, str):
            raise ValueError("workflow must be a workflow name.")

        if not re.fullmatch(r"[A-Za-z0-9_-]+", workflow):
            raise ValueError("Invalid workflow name.")

        selected = workflow
    else:
        selected = "sdxl_turbo" if quality == "fast" else "flux_dev"

    if selected not in available_workflows():
        raise ValueError(
            f"Workflow '{selected}' is not available. "
            f"Existing workflows: {available_workflows()}"
        )

    return selected
