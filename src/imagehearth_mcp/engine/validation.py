import re

from imagehearth_mcp.engine import catalog, config


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
    """Workflows de generación con todos sus modelos instalados."""
    return sorted(
        name
        for name, entry in catalog.entries().items()
        if entry.installed and name not in config.INTERNAL_WORKFLOWS
    )


def not_installed_error(what, profile):
    return ValueError(
        f"{what} is not installed: its models are missing or incomplete. "
        f"Install them with `imagehearth-mcp setup --profile {profile}`."
    )


def require_installed(name, what=None):
    """Falla antes de abrir la sesión si faltan los modelos de un workflow."""
    entry = catalog.entries().get(name)

    if entry is None:
        raise ValueError(
            f"Workflow '{name}' is not available on this system. "
            f"Installed workflows: {available_workflows()}"
        )

    if not entry.installed:
        raise not_installed_error(what or f"Workflow '{name}'", entry.profile)


def resolve_edit_workflow():
    name = catalog.choose("edit")
    require_installed(name, "Image editing")
    return name


def resolve_workflow(workflow, quality):
    if workflow:
        if not isinstance(workflow, str):
            raise ValueError("workflow must be a workflow name.")

        if not re.fullmatch(r"[A-Za-z0-9_-]+", workflow):
            raise ValueError("Invalid workflow name.")

        selected = workflow
    else:
        selected = catalog.choose(quality)

    if selected in config.INTERNAL_WORKFLOWS:
        raise ValueError(
            f"Workflow '{selected}' is not available. "
            f"Installed workflows: {available_workflows()}"
        )

    require_installed(selected)
    return selected
