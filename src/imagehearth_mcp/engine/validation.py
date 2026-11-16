import re

from imagehearth_mcp.engine import catalog, config, gpu


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


def not_installed_error(what, profile, quality_model=None):
    option = f" --quality-model {quality_model}" if quality_model else ""
    return ValueError(
        f"{what} is not installed: its models are missing or incomplete. "
        f"Install them with `imagehearth-mcp setup --profile {profile}{option}`."
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
        raise not_installed_error(
            what or f"Workflow '{name}'", entry.profile, entry.quality_model
        )


def resolve_edit_model(model=""):
    """The installed model an edit uses: `model` or the default of the editing capability."""
    total = gpu.total_mib()
    installed = catalog.installed_models("edit", total)

    if installed:
        from imagehearth_mcp.provisioner import manifest

        known = manifest.load().catalog
        smallest = min(known[item.name].min_vram_mib for item in installed)
    else:
        smallest = min(catalog.minimum_vram_mib(name) for name in catalog.variants()["edit"])

    if total is not None and total < smallest:
        raise ValueError(
            f"Image editing is not available: it needs at least {smallest} MiB of GPU "
            f"memory and this GPU has {total} MiB. Image generation still works."
        )

    if not model and not catalog.default_model("edit"):
        # Nothing installed for editing: the same error as ever, naming the profile.
        require_installed(catalog.choose("edit", total), "Image editing")

    return catalog.resolve_model("edit", model)


def resolve_edit_workflow():
    return resolve_edit_model().workflow


def resolve_workflow(workflow, quality):
    if workflow:
        if not isinstance(workflow, str):
            raise ValueError("workflow must be a workflow name.")

        if not re.fullmatch(r"[A-Za-z0-9_-]+", workflow):
            raise ValueError("Invalid workflow name.")

        selected = workflow
    else:
        capability = "high" if quality == "high" else "fast"
        default = catalog.default_model(capability)
        selected = default.workflow if default else catalog.choose(quality)

    if selected in config.INTERNAL_WORKFLOWS:
        raise ValueError(
            f"Workflow '{selected}' is not available. "
            f"Installed workflows: {available_workflows()}"
        )

    require_installed(selected)
    return selected
