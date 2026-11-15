"""LoRAs de SDXL 1.0: qué hay en el catálogo, cuáles están instaladas y cómo se piden.

Se evalúa en cada llamada y solo mira metadatos de archivo, igual que `catalog`, para que
un `setup` posterior se note sin reiniciar el servidor. Nada de aquí toca la GPU.
"""

from dataclasses import dataclass

from imagehearth_mcp.engine import catalog

MAX_LORAS = 3
MAX_WEIGHT = 2.0
WORKFLOW = "sdxl_base"
# Categories whose LoRAs keep the photographic look: `style="auto"` may still add its cues.
PHOTO_CATEGORIES = ("photo", "detail", "lighting")


@dataclass(frozen=True)
class Selected:
    """A LoRA asked for in a request, with the strength to apply."""

    lora: object
    weight: float

    @property
    def name(self):
        return self.lora.name


def parse_one(item):
    """(name, weight or None) from "name" or {"name": ..., "weight": ...}."""
    if isinstance(item, str):
        name, weight = item, None
    elif isinstance(item, dict):
        unknown = sorted(set(item) - {"name", "weight"})

        if unknown:
            raise ValueError(
                f"unknown field(s) {', '.join(unknown)} in a LoRA. Use a name or "
                '{"name": ..., "weight": ...}.'
            )

        name, weight = item.get("name"), item.get("weight")
    else:
        raise ValueError('each LoRA must be a name or {"name": ..., "weight": ...}.')

    if not isinstance(name, str) or not name.strip():
        raise ValueError("a LoRA needs a name.")

    if weight is not None and (
        isinstance(weight, bool)
        or not isinstance(weight, (int, float))
        or not 0 <= weight <= MAX_WEIGHT
    ):
        raise ValueError(f"the weight of LoRA {name!r} must be a number from 0 to {MAX_WEIGHT:g}.")

    return name.strip(), weight


def normalize(loras):
    """The request's `loras` as a list of (name, weight or None). Only checks its shape."""
    if loras is None:
        return []

    if isinstance(loras, (str, dict)):
        loras = [loras]

    if not isinstance(loras, (list, tuple)):
        raise ValueError("loras must be a list of names or {name, weight} objects.")

    found = [parse_one(item) for item in loras]

    if len(found) > MAX_LORAS:
        raise ValueError(f"At most {MAX_LORAS} LoRAs per image are allowed, not {len(found)}.")

    names = [name for name, _ in found]
    repeated = sorted({name for name in names if names.count(name) > 1})

    if repeated:
        raise ValueError(f"LoRA {', '.join(repeated)} is repeated: list each one once.")

    return found


def catalog_loras():
    from imagehearth_mcp.provisioner import manifest

    return manifest.load().loras


def installed(loras=None):
    """The catalog LoRAs whose file is in the models folder, by name."""
    from imagehearth_mcp.provisioner import models

    loras = catalog_loras() if loras is None else loras
    states = models.inspect(
        list(loras.values()), catalog.models_dir(), models.extra_search_paths(_comfy_dir())
    )
    return {item.model.name: item.model for item in states if item.state == models.PRESENT}


def _comfy_dir():
    from imagehearth_mcp.engine import config

    return config.COMFY_DIR


def install_command(names):
    return f"imagehearth-mcp setup --loras {','.join(names)}"


def resolve(requested):
    """[(name, weight or None)] -> [Selected], or ValueError naming what to do.

    Every problem with a name is raised before anything touches the GPU.
    """
    if not requested:
        return []

    available = catalog_loras()
    present = installed(available)
    chosen = []

    for name, weight in requested:
        if name in present:
            lora = present[name]
            chosen.append(Selected(lora, lora.weight if weight is None else float(weight)))
            continue

        have = ", ".join(present) or "none"

        if name in available:
            command = install_command([*present, name])
            raise ValueError(
                f"LoRA {name!r} is not installed. Installed LoRAs: {have}. To install it, "
                f"tell the user to run `{command}` (it fixes the set of LoRAs)."
            )

        raise ValueError(
            f"Unknown LoRA {name!r}. Installed LoRAs: {have}. Use only names from "
            "list_workflows."
        )

    return chosen


def describe(lora):
    """What an agent needs to choose a LoRA: short fields, nothing nested but the words."""
    return {
        "name": lora.name,
        "description": lora.description,
        "category": lora.category,
        "trigger_words": list(lora.trigger_words),
        "weight": lora.weight,
    }


def describe_installed():
    return [describe(lora) for lora in installed().values()]


def is_photographic(selected):
    """True if none of the LoRAs asks for a medium other than a photograph."""
    return all(item.lora.category in PHOTO_CATEGORIES for item in selected)


def with_trigger_words(prompt, selected):
    """The prompt with the activation words it lacks at the start (case is ignored)."""
    lowered = prompt.lower()
    missing = []

    for item in selected:
        for word in item.lora.trigger_words:
            if word.lower() not in lowered and word not in missing:
                missing.append(word)

    if not missing:
        return prompt

    return f"{', '.join(missing)}, {prompt}"


def label(selected):
    """`name:weight` pairs for the PNG metadata."""
    return ",".join(f"{item.name}:{item.weight:g}" for item in selected)
