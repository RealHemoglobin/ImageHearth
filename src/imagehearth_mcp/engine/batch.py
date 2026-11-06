"""Several independent images in one GPU session.

The whole batch is checked before the GPU is touched. Then a single
`generation_session` runs every image one after another: language models are
unloaded and restored once and ComfyUI starts once.
"""

from dataclasses import dataclass, field

import requests

from imagehearth_mcp.engine import comfyui_manager, config, kontext, progress
from imagehearth_mcp.engine.image_router import plan_request
from imagehearth_mcp.engine.log import get_logger
from imagehearth_mcp.engine.orchestrator import RecoveryRequired, generation_session
from imagehearth_mcp.engine.workflow_runner import prepare_generation
from imagehearth_mcp.engine.workflow_runner import run_in_session as run_generation

log = get_logger("batch")

ITEM_FIELDS = (
    "prompt",
    "quality",
    "width",
    "height",
    "negative_prompt",
    "image_paths",
    "workflow",
    "mode",
    "style",
)


@dataclass
class BatchResult:
    """One outcome per item, in the order requested: an ImageResult or an error text."""

    outcomes: list
    warnings: list[str] = field(default_factory=list)

    def __str__(self):
        lines = []

        for number, outcome in enumerate(self.outcomes, start=1):
            if isinstance(outcome, str):
                lines.append(f"{number}: ERROR: {outcome}")
                continue

            line = f"{number}: {outcome.path}"

            for warning in outcome.warnings:
                line += f" | WARNING: {warning}"

            lines.append(line)

        lines.extend(f"WARNING: {warning}" for warning in self.warnings)
        return "\n".join(lines)


def _numbers(indexes):
    return ", ".join(str(index + 1) for index in indexes)


def _reason(error):
    return str(error) or type(error).__name__


def _merge(item, common):
    """The batch values first, each item's own on top. None means not given."""
    merged = {key: value for key, value in common.items() if value is not None}
    merged.update({key: value for key, value in item.items() if value is not None})
    return merged


def validate(
    items,
    quality="fast",
    width=0,
    height=0,
    negative_prompt="",
    image_paths=None,
    workflow="",
    mode="auto",
    style="auto",
):
    """Check the whole batch and prepare every item, or raise with all the problems.

    Returns (kind, prepared) where kind is "generate" or "edit" and prepared holds
    one workflow request per item. Never touches the GPU or the orchestrator.
    """
    limit = config.BATCH_LIMIT

    if not isinstance(items, list) or not items:
        raise ValueError("The prompt list must have at least one prompt.")

    if len(items) > limit:
        raise ValueError(
            f"A batch can have at most {limit} items and this one has {len(items)}. "
            f"Split it, or raise the limit with `imagehearth-mcp setup --batch-limit N` "
            f"(or batch_limit in {config.CONFIG_FILE})."
        )

    common = {
        "quality": quality,
        "width": width,
        "height": height,
        "negative_prompt": negative_prompt,
        "image_paths": image_paths or None,
        "workflow": workflow,
        "mode": mode,
        "style": style,
    }
    errors = []
    requests_ = {}

    for index, item in enumerate(items):
        try:
            if isinstance(item, str):
                item = {"prompt": item}

            if not isinstance(item, dict):
                raise TypeError("each item must be a prompt or an object with at least a prompt.")

            unknown = sorted(set(item) - set(ITEM_FIELDS))

            if unknown:
                raise ValueError(
                    f"unknown field(s) {', '.join(unknown)}. "
                    f"Allowed: {', '.join(ITEM_FIELDS)}."
                )

            requests_[index] = plan_request(**_merge(item, common))
        except (ValueError, TypeError, FileNotFoundError) as error:
            errors.append((index, f"Item {index + 1}: {_reason(error)}"))

    kinds = {}

    for index, request in requests_.items():
        kinds.setdefault(request.mode, []).append(index)

    mixed = len(kinds) > 1

    if mixed:
        errors.append(
            (
                min(min(group) for group in kinds.values()),
                (
                    "A batch must be all generations or all edits, not both. "
                    f"Generations: items {_numbers(kinds['generate'])}. "
                    f"Edits: items {_numbers(kinds['edit'])}. Send them as two batches."
                ),
            )
        )

    prepared = {}

    if not mixed:
        for index, request in requests_.items():
            try:
                prepared[index] = _prepare(request)
            except (ValueError, TypeError, FileNotFoundError, RuntimeError) as error:
                errors.append((index, f"Item {index + 1}: {_reason(error)}"))

    if errors:
        errors.sort(key=lambda entry: entry[0])
        raise ValueError("\n".join(line for _, line in errors))

    kind = next(iter(kinds))
    return kind, [prepared[index] for index in range(len(items))]


def _prepare(request):
    if request.mode == "edit":
        prepared = kontext.prepare_edit(
            request.prompt,
            image_paths=request.references,
            width=request.width,
            height=request.height,
        )

        if request.negative_prompt:
            prepared.warnings.insert(0, "FLUX Kontext ignores negative_prompt.")

        return prepared

    return prepare_generation(
        f"{request.workflow}.json",
        request.prompt,
        request.negative_prompt,
        request.width,
        request.height,
        request.style,
    )


def _workflow_of(kind, prepared):
    return prepared.workflow_name if kind == "edit" else prepared.name


def _execution_order(kind, prepared):
    """Group images by workflow so ComfyUI swaps weights as little as possible.

    The order inside a group is the order requested.
    """
    groups = {}

    for index, item in enumerate(prepared):
        groups.setdefault(_workflow_of(kind, item), []).append(index)

    return [index for group in groups.values() for index in group]


def _engine_unusable(error):
    return (
        isinstance(error, (RecoveryRequired, requests.ConnectionError))
        or comfyui_manager.is_dead()
    )


def run(items, **common):
    """Validate the batch, then generate it in a single session.

    `common` holds the values every item inherits (quality, width, height,
    negative_prompt, image_paths, workflow, mode).
    """
    kind, prepared = validate(items, **common)
    total = len(prepared)
    order = _execution_order(kind, prepared)
    names = sorted({_workflow_of(kind, item) for item in prepared})
    run_item = kontext.run_in_session if kind == "edit" else run_generation

    outcomes = [None] * total
    notes = []
    stop = None

    with generation_session(workflows=names, batch_total=total) as session:
        for position, index in enumerate(order, start=1):
            try:
                progress.raise_if_cancelled()
                session.start_item(position, total)
                outcomes[index] = run_item(session, prepared[index])
            except progress.GenerationCancelled:
                stop = "cancelled"
                break
            except Exception as error:  # noqa: BLE001 - one item must not stop the batch
                log.warning("Item %s failed: %s", index + 1, error)
                outcomes[index] = _reason(error)

                if _engine_unusable(error):
                    stop = f"not attempted: the engine stopped after item {index + 1}"
                    break

        if stop == "cancelled":
            notes.append("The batch was cancelled; finished images are kept.")

    for index in order:
        if outcomes[index] is None:
            outcomes[index] = stop or "not attempted"

    return BatchResult(outcomes, notes + session.warnings)
