"""Models by capability: what an installation has, what a run asks for and what changes.

An installation has, per capability (`fast`, `high`, `edit`), one or more catalog models
with one precision each and a default. This module reads that from the install record
(deducing it for records from before phase 15), merges it with what a run asks for and
plans the change: what to download, what to delete (only what ImageHearth installed and
nothing another model still uses) and how much space it needs.
"""

import dataclasses
from dataclasses import dataclass, field

from imagehearth_mcp.engine import config
from imagehearth_mcp.provisioner import ProvisionError, models
from imagehearth_mcp.provisioner.manifest import (
    CAPABILITIES,
    ModelSet,
    Pick,
    format_size,
)

CAPABILITY_LABELS = {"fast": "Fast", "high": "Quality", "edit": "Editing"}
LEGACY_MODEL = "RealVisXL"


def installed_set(catalog, records, models_dir):
    """The ModelSet an installation has, or None if nothing is installed.

    Records written since phase 15 list it. Older ones are read as: SDXL Turbo in `fast`,
    the model of `quality` (deduced from the files before phase 9) in `high` and Kontext
    in `edit`, each the default, with the precision recorded.
    """
    from imagehearth_mcp.provisioner import quality

    base = catalog.profiles.get(records.profile or "")

    if base is None:
        return None

    if records.models:
        picks = {}

        for capability in CAPABILITIES:
            found = []

            for item in records.models.get(capability, ()):
                model = catalog.catalog.get(item.get("model"))

                if model is not None and capability in model.capabilities:
                    option = model.option(item.get("precision", ""))

                    if option is not None:
                        found.append(Pick(model.name, option.precision))

            if found:
                picks[capability] = tuple(found)

        return ModelSet(picks, dict(records.defaults))

    picks = {}

    if base.fixed:
        return catalog.fixed_set(base)

    if "fast" in base.capabilities:
        picks["fast"] = (Pick("sdxl-turbo", "fp16"),)

    current = quality.current(catalog, records, models_dir)

    if current is not None and "high" in base.capabilities:
        model = catalog.catalog[current.name]
        option = model.option(records.precision or "") if records.precision else None
        precision = option.precision if option else model.options[0].precision
        picks["high"] = (Pick(model.name, precision),)

    if "edit" in base.capabilities:
        option = catalog.catalog["kontext"].option(records.edit_precision or "")
        picks["edit"] = (
            Pick("kontext", option.precision if option else catalog.catalog["kontext"].options[0].precision),
        )

    return ModelSet(picks, {cap: items[0].model for cap, items in picks.items()})


def keep_realvisxl(catalog, profile):
    """The profile with RealVisXL where SDXL 1.0 goes: an installation that still has it."""
    old = catalog.models["realvisxl"]
    swapped = tuple(old if m.name == "sdxl_base" else m for m in profile.models)
    return dataclasses.replace(profile, models=catalog.expand(swapped))


def is_legacy(catalog, records, models_dir):
    """True if the installation still has RealVisXL as its quality model."""
    from imagehearth_mcp.provisioner import quality

    if records.models:
        return bool(records.legacy_quality)

    current = quality.current(catalog, records, models_dir)
    return bool(current and current.legacy)


@dataclass(frozen=True)
class Request:
    """What a run asks for. A capability not in `picks` is left as it is."""

    picks: dict = field(default_factory=dict)
    defaults: dict = field(default_factory=dict)

    def asks(self, capability):
        return capability in self.picks


def target_set(catalog, profile, old, request, vram):
    """The set the installation ends up with after a run.

    Each capability of `profile` is: what the run asks for, else what is installed, else
    the model recommended for this GPU. Capabilities the profile doesn't have are dropped
    only if nothing is installed for them (a smaller profile never removes models).
    """
    picks, defaults = {}, {}
    old = old or ModelSet()

    for capability in CAPABILITIES:
        if request.asks(capability):
            picks[capability] = tuple(request.picks[capability])
            stated = request.defaults.get(capability) or picks[capability][0].model
            defaults[capability] = stated
        elif old.of(capability):
            picks[capability] = old.of(capability)
            defaults[capability] = old.default(capability).model
        elif capability in profile.capabilities:
            pick = catalog.recommended_pick(capability, vram)

            if pick is not None:
                picks[capability] = (pick,)
                defaults[capability] = pick.model

    return ModelSet(picks, defaults)


def profile_for(catalog, base, model_set):
    """The smallest profile that has every capability of the set, at least `base`."""
    order = ("fast", "quality", "full")

    if base.name not in order:
        return base

    needed = {cap for cap, picks in model_set.picks.items() if picks}
    chosen = base

    for name in order:
        profile = catalog.profiles.get(name)

        if profile is None or order.index(name) < order.index(base.name):
            continue

        chosen = profile

        if needed <= set(profile.capabilities):
            break

    return chosen


@dataclass
class Item:
    """One weight of a change, with the models that give it its reason."""

    state: object
    reason: str = ""


@dataclass
class SetChange:
    """The difference between what is installed and what a run leaves."""

    old: ModelSet | None
    new: ModelSet
    profile: object
    download: list = field(default_factory=list)
    delete: list = field(default_factory=list)
    reasons: dict = field(default_factory=dict)
    added: list = field(default_factory=list)
    removed: list = field(default_factory=list)
    # (capability, model, old precision, new precision)
    switched: list = field(default_factory=list)
    kept_attached: bool = False
    legacy: bool = False

    @property
    def changes_models(self):
        return bool(self.removed or self.switched or self.legacy)

    @property
    def download_bytes(self):
        return sum(item.model.bytes for item in self.download)

    @property
    def freed_bytes(self):
        return sum(item.path.stat().st_size for item in self.delete if item.path.exists())


def plan_set_change(catalog, records, models_dir, old, new, profile, legacy=False):
    """What moving from `old` to `new` downloads and deletes.

    Nothing is deleted that ImageHearth didn't install, that a ComfyUI of the user's keeps,
    or that a model of `new` still uses (the encoders and VAEs several models share).
    """
    extra = models.extra_search_paths(config.COMFY_DIR)
    change = SetChange(old, new, profile, legacy=legacy)
    change.kept_attached = records.mode == "attached"
    change.download = [
        item for item in models.inspect(profile.models, models_dir, extra) if item.state != models.PRESENT
    ]

    if old is None:
        return change

    for capability in CAPABILITIES:
        before = {pick.model: pick for pick in old.of(capability)}
        after = {pick.model: pick for pick in new.of(capability)}

        for name, pick in after.items():
            if name not in before:
                change.added.append((capability, pick))
            elif before[name].precision != pick.precision:
                change.switched.append((capability, name, before[name].precision, pick.precision))

        for name, pick in before.items():
            if name not in after:
                change.removed.append((capability, pick))

    keep = {weight.name for weight in profile.models}
    leaving = []

    try:
        old_profile = catalog.build_set(profile_for(catalog, catalog.profiles["fast"], old), old)
    except ProvisionError:
        old_profile = None

    if old_profile is not None:
        leaving = [weight for weight in old_profile.models if weight.name not in keep]

    if legacy and "realvisxl" not in keep:
        leaving.append(catalog.models["realvisxl"])

    # LoRAs are for SDXL 1.0 only: they leave with it.
    if any(pick.model == "sdxl" for _, pick in change.removed):
        leaving.extend(catalog.loras.values())

    if change.kept_attached:
        return change

    for item in models.inspect(leaving, models_dir):
        if item.state != models.MISSING and records.is_owned(item.path):
            change.delete.append(item)
            change.reasons[str(item.path)] = _reason(catalog, old, new, item.model)

    return change


def _reason(catalog, old, new, weight):
    """Why a weight is deleted: the models that used it and went away or changed precision."""
    if hasattr(weight, "trigger_words"):
        return "LoRA for SDXL 1.0, which is being removed"

    if weight.name == "realvisxl":
        return f"{LEGACY_MODEL}, replaced by SDXL 1.0"

    names = []

    for capability, pick in old.all() if old else ():
        try:
            option = catalog.option_of(capability, pick)
        except ProvisionError:
            continue

        if weight in catalog.expand(option.models):
            title = catalog.catalog[pick.model].title
            switched = new.pick(capability, pick.model)
            names.append(f"{title} {pick.precision}" + (f" -> {switched.precision}" if switched else " removed"))

    return "; ".join(dict.fromkeys(names)) or "no longer used"


def record(records, profile, legacy=False):
    """Write what the installation has into the install record (after it is verified)."""
    model_set = profile.model_set

    if model_set is None:
        return

    records.models = {
        capability: [{"model": pick.model, "precision": pick.precision} for pick in model_set.of(capability)]
        for capability in CAPABILITIES
        if model_set.of(capability)
    }
    records.legacy_quality = bool(legacy)
    records.defaults = {
        capability: model_set.default(capability).model
        for capability in CAPABILITIES
        if model_set.of(capability)
    }
    # The fields phase 9 wrote, kept so an older ImageHearth still reads the record.
    high = model_set.default("high")
    edit = model_set.default("edit")
    records.quality_model = high.model if high else None
    records.precision = high.precision if high else None
    records.edit_precision = edit.precision if edit else None


def describe_set(catalog, model_set):
    """One line per capability: `Fast: klein-4b (default), sdxl-turbo`."""
    lines = []

    for capability in CAPABILITIES:
        picks = model_set.of(capability)

        if not picks:
            continue

        default = model_set.default(capability)
        parts = [
            f"{pick.model}:{pick.precision}" + (" (default)" if pick == default and len(picks) > 1 else "")
            for pick in picks
        ]
        lines.append(f"{CAPABILITY_LABELS[capability]}: {', '.join(parts)}")

    return lines


def show_change(change, catalog):
    """Print the model changes of a run: what is added, replaced and removed."""
    print("\nModels after this:")

    for line in describe_set(catalog, change.new):
        print(f"  {line}")

    for capability, pick in change.added:
        print(f"  + {catalog.catalog[pick.model].title} {pick.precision} ({CAPABILITY_LABELS[capability].lower()})")

    for capability, name, before, after in change.switched:
        print(f"  ~ {catalog.catalog[name].title}: {before} -> {after} ({CAPABILITY_LABELS[capability].lower()})")

    for capability, pick in change.removed:
        print(f"  - {catalog.catalog[pick.model].title} {pick.precision} ({CAPABILITY_LABELS[capability].lower()})")

    if change.legacy:
        print(f"  - {LEGACY_MODEL} (replaced by SDXL 1.0)")

    print(f"  To download: {format_size(change.download_bytes)}")

    for item in change.delete:
        kind = " (LoRA)" if hasattr(item.model, "trigger_words") else ""
        reason = change.reasons.get(str(item.path), "")
        print(f"  To delete afterwards: {item.path.name}{kind}" + (f" - {reason}" if reason else ""))

    if change.kept_attached:
        print("  Old models stay in the ComfyUI you attached; delete them by hand if you want the space.")
    else:
        print(f"  Space freed: {format_size(change.freed_bytes)}")

    print("  The current models keep working until the new ones are downloaded and verified.")
