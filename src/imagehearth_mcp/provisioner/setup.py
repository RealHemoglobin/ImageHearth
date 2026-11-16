"""Subcomando `setup`: lleva una máquina a un sistema que genera imágenes."""

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from imagehearth_mcp.engine import comfyui_manager, config
from imagehearth_mcp.platform import locks
from imagehearth_mcp.provisioner import (
    ProvisionError,
    comfyui,
    detect,
    locations,
    manifest,
    menu,
    models,
    preflight,
    quality,
    selection,
    settings,
    smoke,
)
from imagehearth_mcp.provisioner.install_manifest import InstallManifest
from imagehearth_mcp.provisioner.manifest import format_size

ATTACHED = "attached"
MANAGED = preflight.MANAGED
PROFILE_ORDER = (
    "fast",
    "quality",
    "full",
    "mac-fast",
    "mac-quality",
    "mac-full",
)
MAX_DRIVES = menu.MAX_SINGLE_KEY - 2
CAPABILITY_LABELS = {"fast": "fast", "high": "quality", "edit": "editing"}
UNTESTED_MACOS = (
    "macOS is prepared but has never been run on a real Mac: ComfyUI, ComfyUI-GGUF, "
    "FLUX and Kontext may not work on MPS."
)


def is_interactive(args):
    return not args.non_interactive and sys.stdin.isatty()


def propose_profile(detection, catalog):
    """El mayor perfil que caben en la memoria de la GPU y en el disco."""
    gpu = detection.primary_gpu
    vram = gpu.vram_mib if gpu else 0
    profiles = catalog.profiles_for(detection.system)
    proposed = next(iter(profiles), "fast")

    for name, profile in profiles.items():
        try:
            size = catalog.build_set(profile, catalog.recommended_set(profile, vram)).bytes
        except ProvisionError:
            size = 0

        if vram >= catalog.min_vram_mib(profile) and detection.disk_free_bytes > size:
            proposed = name

    return proposed


def choose_profile(args, detection, catalog, interactive, default=None, back_label="Back"):
    """El perfil base. En interactivo, un menú: devuelve el perfil o `menu.BACK`."""
    profiles = catalog.profiles_for(detection.system)
    names = ", ".join(profiles)

    if args.profile:
        if args.profile not in profiles:
            raise ProvisionError(
                f"The {args.profile} profile is not for {detection.system}. "
                f"Choose one of: {names}."
            )

        return profiles[args.profile]

    proposed = propose_profile(detection, catalog)

    if not interactive:
        raise ProvisionError(
            f"Non-interactive mode needs a profile: add --profile with one of {names} "
            f"(this machine suits {proposed})."
        )

    options = [
        menu.Option(
            name,
            f"{name:8} {('from ' if profile.quality else '') + format_size(profile.bytes):>13}  "
            f"{profile.description}",
            recommended=name == proposed,
        )
        for name, profile in profiles.items()
    ]
    answer = menu.choose(
        "Profiles:",
        options,
        default=default if default in profiles else proposed,
        back_label=back_label,
    )

    return answer if answer is menu.BACK else profiles[answer]


CAPABILITY_FLAGS = {"fast": "fast_models", "high": "quality_models", "edit": "edit_models"}
CAPABILITY_OPTIONS = {"fast": "--fast-models", "high": "--quality-models", "edit": "--edit-models"}
CAPABILITY_TITLES = {
    "fast": "Fast models (quick drafts)",
    "high": "Quality models (detailed images)",
    "edit": "Editing models",
}


def asked_models(args, capability):
    """The `name[:precision]` list passed for a capability, or None if it wasn't passed."""
    value = getattr(args, CAPABILITY_FLAGS[capability], None)

    if capability == "high" and not value:
        value = getattr(args, "quality_model", None)

    if not value:
        return None

    if isinstance(value, str):
        value = value.split(",")

    texts = [str(part).strip() for part in value if str(part).strip()]
    return texts or None


def _with_variant(catalog, capability, texts, variant):
    """`--variant`: the precision of the models that don't name one, where they have it."""
    if not variant:
        return texts

    found = []

    for text in texts:
        name = text.partition(":")[0].strip()
        model = catalog.catalog.get(name)

        if ":" not in text and model is not None:
            option = model.option(variant)

            if option is not None and option.workflow(capability):
                text = f"{name}:{option.precision}"

        found.append(text)

    return found


def requested_models(args, catalog, profile, vram, installed=None):
    """The models the arguments ask for, as a selection.Request. Errors come before any question.

    A model without a precision keeps the one it has if it is installed; otherwise it gets
    the one recommended for this GPU.
    """
    picks, defaults = {}, {}
    variant = getattr(args, "variant", None)

    for capability in manifest.CAPABILITIES:
        texts = asked_models(args, capability)

        if texts is None:
            continue

        if capability not in profile.capabilities:
            have = [
                name
                for name, other in catalog.profiles_for("linux").items()
                if capability in other.capabilities
            ]
            raise ProvisionError(
                f"The {profile.name} profile has no {capability} models: "
                f"{CAPABILITY_OPTIONS[capability]} only applies to {' and '.join(have)}."
            )

        chosen = catalog.parse_picks(capability, _with_variant(catalog, capability, texts, variant), vram)

        for index, text in enumerate(texts):
            have = installed.pick(capability, chosen[index].model) if installed else None

            if ":" not in text and have is not None and not variant:
                chosen[index] = have

        picks[capability] = tuple(chosen)
        defaults[capability] = chosen[0].model

    return selection.Request(picks, defaults)


def format_seconds(measure):
    if measure is None or measure.seconds is None:
        return "not measured"

    return f"{measure.seconds:.0f} s" if measure.seconds >= 10 else f"{measure.seconds:.1f} s"


def model_option_label(info):
    """One line of the models menu: title, size and time of the recommended precision, license."""
    best = next((item for item in info["precisions"] if item["recommended"]), info["precisions"][0])
    commercial = "commercial use" if info["commercial_use"] else "non-commercial"
    seconds = "?" if best["seconds"] is None else (
        f"{best['seconds']:.0f} s" if best["seconds"] >= 10 else f"{best['seconds']:.1f} s"
    )
    return (
        f"{info['title']:22} {format_size(best['download_bytes']):>8}  {seconds:>5}  "
        f"{info['license'].name}, {commercial}"
    )


def model_options(catalog, capability, vram, installed_names=()):
    """The menu options of a capability: recommended and installed models are flagged."""
    options = []

    for info in catalog.describe_catalog(capability, vram):
        flags = []

        if info["name"] in installed_names:
            flags.append("installed")

        detail = ", ".join(
            f"{item['precision']} {format_size(item['download_bytes'])}"
            + ("" if item["fits"] else " (needs more GPU memory)")
            for item in info["precisions"]
        )

        if any(item["fits"] is False for item in info["precisions"]) and not any(
            item["fits"] for item in info["precisions"]
        ):
            detail += f"\nWARNING: needs at least {info['precisions'][0]['min_vram_mib']} MiB of GPU memory"

        label = model_option_label(info)
        label += f"  [{', '.join(flags)}]" if flags else ""
        options.append(menu.Option(info["name"], label, detail, recommended=info["recommended"]))

    return options


def choose_models(catalog, capability, vram, installed_names, default, back_label="Back"):
    """The models of a capability, by multiple selection. `menu.BACK` goes back."""
    options = model_options(catalog, capability, vram, installed_names)

    if default is None:
        default = list(installed_names) or [
            item.key for item in options if item.recommended
        ] or [options[0].key]

    while True:
        answer = menu.choose_many(
            f"{CAPABILITY_TITLES[capability]} (mark one or more):",
            options,
            back_label=back_label,
            default=default,
        )

        if answer is menu.BACK:
            return menu.BACK

        if answer:
            return tuple(answer)

        print("Choose at least one model.")
        default = [item.key for item in options if item.recommended] or [options[0].key]


def precision_options(catalog, capability, name, vram):
    info = next(item for item in catalog.describe_catalog(capability, vram) if item["name"] == name)
    options = []

    for item in info["precisions"]:
        seconds = "not measured" if item["seconds"] is None else f"{item['seconds']:g} s per image"
        vram_text = "" if item["vram_mib"] is None else f", {item['vram_mib'] / 1024:.1f} GB of GPU memory"
        spill = ""

        if item["offload_mib"]:
            spill = f", {item['offload_mib'] / 1024:.0f} GB moves to RAM"

        label = f"{item['precision']:8} {format_size(item['download_bytes']):>8}  {seconds}{vram_text}{spill}"
        detail = "" if item["fits"] else (
            f"WARNING: needs at least {item['min_vram_mib']} MiB of GPU memory"
        )
        options.append(menu.Option(item["precision"], label, detail, recommended=item["recommended"]))

    return options


def choose_precision(catalog, capability, name, vram, default=None, back_label="Back"):
    """The precision of one model. `menu.BACK` goes back."""
    options = precision_options(catalog, capability, name, vram)
    recommended = next((item.key for item in options if item.recommended), options[0].key)
    valid = {item.key for item in options}

    return menu.choose(
        f"{catalog.catalog[name].title} precision:",
        options,
        default=default if default in valid else recommended,
        back_label=back_label,
    )


def choose_default(catalog, capability, names, default=None, back_label="Back"):
    """Which of several models is the default of a capability. `menu.BACK` goes back."""
    options = [menu.Option(name, catalog.catalog[name].title) for name in names]
    return menu.choose(
        f"Default {CAPABILITY_LABELS[capability]} model (used when a request names none):",
        options,
        default=default if default in names else names[0],
        back_label=back_label,
    )


def parse_loras(text, catalog):
    """The names in `--loras` (`all`, `none` or a list), in catalog order; error if unknown."""
    text = (text or "").strip()

    if text == "all":
        return tuple(catalog.loras)

    names = [part.strip() for part in text.split(",") if part.strip()]

    if names == ["none"] or not names:
        return ()

    unknown = [name for name in names if name not in catalog.loras]

    if unknown:
        raise ProvisionError(
            f"Unknown LoRA {', '.join(map(repr, unknown))}. Choose from: "
            f"{', '.join(catalog.loras)}, or use all or none."
        )

    return tuple(name for name in catalog.loras if name in names)


def format_small(size):
    return f"{size / 1_000_000:.0f} MB" if size < 1_000_000_000 else format_size(size)


def lora_options(catalog):
    return [
        menu.Option(
            lora.name,
            f"{lora.name:18} {lora.category:13} {format_small(lora.bytes):>7}  "
            f"{catalog.licenses[lora.license].name}",
            lora.description,
        )
        for lora in catalog.loras.values()
    ]


def choose_loras(catalog, installed, default=None, back_label="Back"):
    """The LoRAs to have: those marked on the installation, or none. `menu.BACK` goes back."""
    marked = list(installed) if default is None else list(default)
    answer = menu.choose_many(
        "Style LoRAs for SDXL 1.0 (optional):",
        lora_options(catalog),
        back_label=back_label,
        default=marked,
    )
    return answer if answer is menu.BACK else tuple(answer)


def choose_mode(args, detection, records, interactive, default=None, back_label="Back"):
    """Devuelve (modo, carpeta, puerto por defecto)."""
    default_dir = config.DATA_DIR / "comfyui"

    if args.attach:
        path = Path(args.attach).expanduser().resolve()
        known = {i.path: i for i in detection.comfy_installs}
        desktop = str(path) in known and known[str(path)].kind == "desktop"

        if not desktop and not detect.is_comfy_dir(path):
            raise ProvisionError(
                f"{path} does not look like a ComfyUI folder (it has no main.py). "
                "Check the path."
            )

        return ATTACHED, path, detect.DESKTOP_PORT if desktop else config.COMFY_PORT

    if args.managed:
        return MANAGED, default_dir, config.COMFY_PORT

    if records.mode:
        return records.mode, Path(records.comfy_dir), config.COMFY_PORT

    if not detection.comfy_installs:
        return MANAGED, default_dir, config.COMFY_PORT

    if not interactive:
        found = ", ".join(i.path for i in detection.comfy_installs)
        raise ProvisionError(
            f"Found an existing ComfyUI ({found}). Non-interactive mode needs a "
            "decision: add --attach PATH to use it or --managed to install another."
        )

    previous = None

    if default is not None:
        previous = "m" if default[0] == MANAGED else next(
            (n for n, i in enumerate(detection.comfy_installs) if Path(i.path) == default[1]),
            None,
        )

    options = [
        menu.Option(number, f"{install.path} ({install.kind})")
        for number, install in enumerate(detection.comfy_installs)
    ]
    options.append(menu.Option("m", "Install a separate ComfyUI managed by ImageHearth"))
    answer = menu.choose(
        "Found an existing ComfyUI. Using it avoids duplicating tens of GB:",
        options,
        default=previous if previous is not None else 0,
        back_label=back_label,
    )

    if answer is menu.BACK:
        return menu.BACK

    if answer == "m":
        return MANAGED, default_dir, config.COMFY_PORT

    install = detection.comfy_installs[answer]
    port = detect.DESKTOP_PORT if install.kind == "desktop" else config.COMFY_PORT
    return ATTACHED, Path(install.path), port


def show_summary(
    catalog, profile, mode, comfy_dir, models_dir, pending, torch=None, folder=None, notes=(),
    loras=None,
):
    print(f"\nProfile: {profile.name} ({profile.description})")

    if profile.model_set is not None:
        for line in selection.describe_set(catalog, profile.model_set):
            print(line)
    elif profile.quality_model:
        print(f"Quality model: {profile.quality_model} ({profile.precision})")

    if folder is not None:
        print(f"Install folder: {folder}")

    print(f"ComfyUI: {mode}, {comfy_dir}")
    print(f"Models:  {models_dir}")

    for note in notes:
        print(f"WARNING: {note}")

    print("\nDownloads:")

    if mode == MANAGED and not (Path(comfy_dir) / "venv").exists():
        print(
            f"  ComfyUI {catalog.comfyui.version} and Python environment  "
            f"{format_size(catalog.install_bytes(torch))}"
        )

    for node in profile.nodes:
        print(f"  {node.folder} (custom node)")

    for item in models.inspect(profile.models, models_dir):
        status = "" if item.state != models.PRESENT else "  (already present)"
        print(f"  {item.model.name:14} {format_size(item.model.bytes):>8}{status}")

    licenses = catalog.licenses_for(profile)

    if loras is not None:
        for item in loras.download:
            print(f"  {item.model.name:14} {format_small(item.model.bytes):>8}  (LoRA)")

        licenses += [
            entry
            for entry in catalog.lora_licenses(item.model for item in loras.download)
            if entry not in licenses
        ]

    print(f"  Models to download: {format_size(pending)}")

    if loras is not None:
        print(
            "\nLoRAs after this: "
            f"{', '.join(loras.names) if loras.names else 'none'}"
        )

        for item in loras.delete:
            print(f"  To delete: {item.path.name} ({format_small(item.model.bytes)})")

    print("\nLicenses you accept by downloading them:")

    for entry in licenses:
        print(f"  {entry.name}\n    {entry.url}\n    {entry.summary}")

    print()


def require_acceptance(args, interactive):
    if args.accept_licenses:
        return

    if not interactive:
        raise ProvisionError(
            "Nothing was downloaded. Non-interactive mode needs --accept-licenses to "
            "accept the licenses listed above."
        )

    if not menu.confirm("Accept these licenses and start downloading?"):
        raise ProvisionError("Nothing was downloaded: the licenses were not accepted.")


def run_preflight(detection, profile, torch, mode, comfy_dir, models_dir, port, pending, catalog):
    needs = {models_dir: pending}

    if mode == MANAGED:
        pending_install = 0

        if not (Path(comfy_dir) / "venv").exists():
            pending_install = catalog.install_bytes(torch)

        needs[comfy_dir] = pending_install

    own_instance = port == config.COMFY_PORT and comfyui_manager.managed_pid() is not None
    issues = [
        *preflight.check_gpu(detection, profile, torch, mode),
        *preflight.check_disk(needs),
        *preflight.check_port(port, mode, own_instance),
        *(preflight.check_uv() if mode == MANAGED else ()),
    ]

    for issue in issues:
        if issue.level == preflight.WARNING:
            print(f"WARNING: {issue.message}")

    errors = [issue.message for issue in issues if issue.level == preflight.ERROR]

    if errors:
        raise ProvisionError("\n".join(errors))


def require_experimental(args, detection):
    """macOS solo entra con permiso explícito, antes de preguntar o descargar nada."""
    if detection.system == "darwin" and not args.experimental:
        raise ProvisionError(
            f"{UNTESTED_MACOS} Nothing was downloaded. To try it anyway, run setup "
            "again with --experimental, and please report how it goes."
        )

    if detection.system == "darwin":
        print(f"WARNING: {UNTESTED_MACOS}")


def install_nodes(args, profile, comfy_dir, records, mode, interactive):
    """Los nodos que necesita el perfil. En un ComfyUI ajeno hace falta permiso."""
    for node in profile.nodes:
        allowed = mode == MANAGED or args.install_node

        if not allowed and interactive:
            allowed = menu.confirm(f"Install {node.folder}, which this profile needs, in {comfy_dir}?")

        if not comfyui.install_custom_node(node, comfy_dir, records, allowed):
            raise ProvisionError(
                f"The {profile.name} profile needs {node.folder}, which was not "
                "installed. Add --install-node to allow it."
            )


def install_attached(args, comfy_dir, records, interactive):
    allowed = args.install_node

    if not allowed and interactive and not comfyui.node_is_current(comfy_dir):
        allowed = menu.confirm(f"Install the ImageHearth status node in {comfy_dir}?")

    if not comfyui.install_node(comfy_dir, records, allowed):
        print(
            "WARNING: the status node was not installed. Generation works, but GPU "
            "memory is checked less reliably. Add --install-node to install it."
        )


def _normal(path):
    return os.path.normcase(os.path.abspath(path))


def _is_inside(path, folder):
    return _normal(path) == _normal(folder) or _normal(folder) + os.sep in _normal(path) + os.sep


def _claim_folder(records, folder):
    """Anota qué carpetas crea setup: `uninstall` solo borra lo que se anotó como propio."""
    top = locations.first_missing(folder)

    if top is not None:
        records.claim("install_dir", top)

    records.install_dir = str(folder)


def _higher_profile(current, new):
    if current not in PROFILE_ORDER:
        return new

    return max(current, new, key=PROFILE_ORDER.index)


def apply_config(args, mode, comfy_dir, port, records, models_dir=None):
    values = {}

    if mode == ATTACHED or Path(config.COMFY_DIR) != Path(comfy_dir):
        values["comfy_dir"] = str(comfy_dir)

    if models_dir is not None and Path(models_dir) != Path(comfy_dir) / "models":
        values["models_dir"] = str(models_dir)

    if mode == ATTACHED or args.port or port != config.COMFY_PORT:
        values["comfy_port"] = port

    batch_limit = getattr(args, "batch_limit", None)

    if batch_limit is not None:
        values["batch_limit"] = batch_limit

    settings.apply(config.CONFIG_FILE, values, records)

    if os.environ.get("IMAGEHEARTH_BATCH_LIMIT") and "batch_limit" in values:
        print(
            "WARNING: IMAGEHEARTH_BATCH_LIMIT is set and overrides the limit written "
            f"to {config.CONFIG_FILE}."
        )

    if os.environ.get("IMAGEHEARTH_COMFY_DIR") and "comfy_dir" in values:
        print(
            "WARNING: IMAGEHEARTH_COMFY_DIR is set and overrides the folder written "
            f"to {config.CONFIG_FILE}."
        )


@dataclass
class Answers:
    """Lo respondido hasta ahora. Se conserva al volver atrás."""

    mode: tuple | None = None
    base: object = None
    # capability -> names marked in its step; None until asked.
    picks: dict = field(default_factory=dict)
    # (capability, model) -> precision chosen; capability -> default model.
    precisions: dict = field(default_factory=dict)
    defaults: dict = field(default_factory=dict)
    # The profile the picks were made for: they are dropped if it changes.
    picks_for: str | None = None
    # LoRAs chosen in the step; None until asked.
    loras: tuple | None = None


@dataclass(frozen=True)
class LoraPlan:
    """The set of LoRAs this run leaves: what to download and what to delete."""

    names: tuple
    download: tuple = ()
    delete: tuple = ()

    @property
    def download_bytes(self):
        return sum(item.model.bytes for item in self.download)

    @property
    def changes(self):
        return bool(self.download or self.delete)


@dataclass(frozen=True)
class Plan:
    mode: str
    comfy_dir: Path
    port: int
    models_dir: Path
    models: object
    profile: object
    change: object
    pending: int
    torch: object
    folder: Path | None = None
    loras: LoraPlan | None = None
    # The installation keeps RealVisXL as its SDXL: nothing replaced it in this run.
    legacy_kept: bool = False


def choose_folder(run, back_label="Back"):
    """La carpeta de instalación. Devuelve una ruta, None (la de siempre) o `menu.BACK`."""
    default = locations.default_install_dir()
    # Con más de nueve opciones el menú deja de leer una sola tecla.
    drives = sorted(
        (drive for drive in locations.list_drives() if not drive.system),
        key=lambda drive: -drive.free,
    )[:MAX_DRIVES]
    needed = run.download_hint()
    options = [
        menu.Option(
            "default",
            f"{default}  (the usual place)",
            _free_text(locations.free_bytes(default), needed),
            recommended=True,
        )
    ]
    proposals = {}

    for drive in drives:
        proposal = locations.propose(drive)
        proposals[str(proposal)] = proposal
        kind = " ".join(
            tag
            for tag, on in (("network", drive.network), ("removable", drive.removable))
            if on
        )
        detail = _free_text(drive.free, needed) + (f" ({kind})" if kind else "")
        options.append(menu.Option(str(proposal), str(proposal), detail))

    options.append(menu.Option("type", "Type a path"))
    current = str(run.folder) if run.folder is not None else "default"
    previous = current if current in proposals or current == "default" else "type"

    while True:
        answer = menu.choose(
            "Install folder (ComfyUI and the models take tens of GB):",
            options,
            default=previous,
            back_label=back_label,
        )

        if answer is menu.BACK:
            return menu.BACK

        if answer == "default":
            return None

        if answer == "type":
            text = menu.ask_line("Folder (Enter to go back to the list): ")

            if not text:
                continue

            folder = locations.resolve(text)
        else:
            folder = proposals[answer]

        if folder == default:
            return None

        errors, warnings = locations.split(run.folder_issues(folder))

        for warning in warnings:
            print(f"WARNING: {warning}")

        if not errors:
            return folder

        for error in errors:
            print(f"Error: {error}")


def _free_text(free, needed):
    text = f"{format_size(free)} free"

    if needed:
        text += f", ComfyUI and models need about {format_size(needed)}"

        if free < needed:
            text += " (not enough space)"

    return text


class _Run:
    """Lo fijo de una ejecución: argumentos, catálogo, registro y detección (una vez)."""

    def __init__(self, args, catalog, records, detection, interactive):
        self.args = args
        self.catalog = catalog
        self.records = records
        self.detection = detection
        self.interactive = interactive
        gpu = detection.primary_gpu
        self.vram = gpu.vram_mib if gpu else 0
        asked = getattr(args, "install_dir", None)
        # Carpeta pedida por argumento o elegida en el paso; None es la de siempre.
        self.folder_arg = locations.resolve(asked) if asked else None
        self.folder = self.folder_arg
        self.answers = None
        asked_loras = getattr(args, "loras", None)
        # None: not asked for, the LoRAs are left as they are.
        self.lora_arg = None if asked_loras is None else parse_loras(asked_loras, catalog)

    def models_dir(self, comfy_dir):
        args = self.args
        found = Path(args.models_dir).expanduser().resolve() if args.models_dir else None

        if (
            found is None
            and self.folder is not None
            and not self.records.mode
            and Path(comfy_dir) == self.folder / "comfyui"
        ):
            # Una carpeta nueva lleva sus modelos dentro, no los de una instalación borrada.
            return Path(comfy_dir) / "models"

        return found or models.resolve_dir(self.records, comfy_dir)

    def _models_in(self, comfy_dir):
        asked = self.args.models_dir
        return Path(asked).expanduser().resolve() if asked else Path(comfy_dir) / "models"

    def place(self, mode):
        """Aplica `--install-dir` o la carpeta elegida a (modo, carpeta de ComfyUI, puerto)."""
        kind, _, port = mode
        arg = self.folder_arg

        if arg is None:
            if kind == MANAGED and self.folder is not None and not self.records.mode:
                return kind, self.folder / "comfyui", port

            return mode

        if kind != MANAGED:
            raise ProvisionError(
                "--install-dir is for the ComfyUI that ImageHearth installs, and this "
                "installation uses an existing ComfyUI. Nothing was changed."
            )

        target = arg / "comfyui"

        if self.records.mode and _normal(self.records.comfy_dir) != _normal(target):
            raise ProvisionError(
                f"ImageHearth is already installed in {self.records.comfy_dir}. setup "
                f"doesn't move it: run `imagehearth-mcp update --move-to {arg}` instead."
            )

        return kind, target, port

    def asks_folder(self, answers):
        args = self.args

        if not self.interactive or self.folder_arg or args.attach or self.records.mode:
            return False

        if answers.mode is None:
            # El modo aún se pregunta: si es gestionado, este paso viene después.
            return self.asks_mode()

        return answers.mode[0] == MANAGED

    def _resolved_profile(self, answers):
        if answers.base is None or answers.mode is None:
            return None

        try:
            return self.resolve_models(answers)[1]
        except ProvisionError:
            return None

    def download_hint(self):
        """Lo que se descargará, si ya se sabe qué perfil: para mostrar junto al espacio libre."""
        profile = self._resolved_profile(self.answers)

        if profile is None:
            return 0

        torch = self.catalog.pytorch.get(self.detection.platform.index)
        return profile.bytes + self.catalog.install_bytes(torch)

    def folder_issues(self, folder, plan=None):
        """Errores y avisos de instalar en `folder` con lo que se sabe hasta ahora."""
        comfy_dir = folder / "comfyui"
        profile = plan.profile if plan else self._resolved_profile(self.answers)
        models_dir = plan.models_dir if plan else self._models_in(comfy_dir)
        sizes, install_bytes = [], 0

        if profile is not None:
            sizes = [
                item.model.bytes
                for item in models.inspect(profile.models, models_dir)
                if item.state != models.PRESENT
            ]

            if not (comfy_dir / "venv").exists():
                torch = plan.torch if plan else self.catalog.pytorch.get(self.detection.platform.index)
                install_bytes = self.catalog.install_bytes(torch)

        inside = _is_inside(models_dir, folder)
        issues = locations.check(folder, sizes if inside else (), install_bytes)

        if not inside and sizes:
            issues += locations.check(models_dir, sizes)

        return issues

    def installed(self, comfy_dir):
        """The ModelSet the installation has, or None if nothing is installed."""
        return selection.installed_set(self.catalog, self.records, self.models_dir(comfy_dir))

    def legacy(self, comfy_dir):
        """Whether the installation still has RealVisXL as its quality model."""
        return selection.is_legacy(self.catalog, self.records, self.models_dir(comfy_dir))

    def effective_base(self, base):
        """A run never lowers the profile: the higher of the recorded one and the chosen one."""
        return self.catalog.profiles[_higher_profile(self.records.profile, base.name)]

    def asks_mode(self):
        args = self.args
        return bool(
            self.interactive
            and not args.attach
            and not args.managed
            and not self.records.mode
            and self.detection.comfy_installs
        )

    def asks_profile(self):
        return self.interactive and not self.args.profile

    def asks_review(self, answers):
        """La confirmación final: licencias y, con un cambio de modelos, ese cambio."""
        args = self.args

        if not self.interactive:
            return False

        if not args.accept_licenses:
            return True

        if getattr(args, "yes", False):
            return False

        if answers.mode is None or answers.base is None:
            return False

        _, _, change = self.resolve_models(answers)
        loras = self.lora_plan(answers, change.new, self.models_dir(answers.mode[1]))
        return change.changes_models or bool(loras and loras.delete)

    def asks_models(self, capability, base):
        """Whether the step that marks the models of a capability is asked."""
        return bool(
            self.interactive
            and base is not None
            and not base.fixed
            and capability in base.capabilities
            and asked_models(self.args, capability) is None
        )

    def picked(self, answers, capability):
        """The names marked in a capability's step for the current profile, or None."""
        if answers.base is None or answers.picks_for != answers.base.name:
            return None

        return answers.picks.get(capability) or None

    def options_count(self, capability, name):
        model = self.catalog.catalog[name]
        return sum(1 for option in model.options if option.workflow(capability))

    def request(self, answers):
        """What the arguments and the answers ask for, as a selection.Request."""
        base = answers.base
        installed = self.installed(answers.mode[1]) if answers.mode else None
        found = requested_models(self.args, self.catalog, base, self.vram, installed)
        picks, defaults = dict(found.picks), dict(found.defaults)

        for capability in base.capabilities:
            names = self.picked(answers, capability)

            if capability in picks or not names:
                continue

            chosen = []

            for name in names:
                precision = answers.precisions.get((capability, name)) or self.default_precision(
                    capability, name, installed
                )
                chosen.append(manifest.Pick(name, precision))

            picks[capability] = tuple(chosen)
            stated = answers.defaults.get(capability)
            defaults[capability] = stated if stated in names else chosen[0].model

        return selection.Request(picks, defaults)

    def default_precision(self, capability, name, installed):
        """The precision a model has: the installed one, else the one recommended for this GPU."""
        have = installed.pick(capability, name) if installed else None

        if have is not None:
            return have.precision

        return self.catalog.recommended_precision(
            self.catalog.catalog[name], capability, self.vram
        ).precision

    def resolve_models(self, answers):
        """(target ModelSet, resolved profile, SetChange) for the answers so far."""
        _, comfy_dir, _ = answers.mode
        base = answers.base
        models_dir = self.models_dir(comfy_dir)
        old = self.installed(comfy_dir)
        legacy = self.legacy(comfy_dir)

        if base.fixed:
            asked = [c for c in manifest.CAPABILITIES if asked_models(self.args, c) is not None]

            if asked:
                raise ProvisionError(
                    f"The {base.name} profile has fixed models: the model options "
                    "don't apply to it."
                )

            target = self.catalog.fixed_set(base)
            request = selection.Request()
            profile = self.catalog.build_set(base, target)
        else:
            request = self.request(answers)
            effective = self.effective_base(base)
            target = selection.target_set(self.catalog, effective, old, request, self.vram)
            effective = selection.profile_for(self.catalog, effective, target)
            profile = self.catalog.build_set(effective, target)

        switching = legacy and request.asks("high")

        if legacy and not switching:
            profile = selection.keep_realvisxl(self.catalog, profile)

        change = selection.plan_set_change(
            self.catalog, self.records, models_dir, old, target, profile, legacy=switching
        )
        return target, profile, change

    def asks_loras(self, answers):
        """The LoRAs step: interactive, SDXL 1.0 among the quality models, no `--loras`."""
        if not self.interactive or self.lora_arg is not None or not self.catalog.loras:
            return False

        base = answers.base

        if base is None:
            profiles = self.catalog.profiles_for(self.detection.system)
            return any("high" in p.capabilities and not p.fixed for p in profiles.values())

        if base.fixed or "high" not in base.capabilities:
            return False

        asked = asked_models(self.args, "high")

        if asked is not None:
            return any(text.partition(":")[0] == "sdxl" for text in asked)

        names = self.picked(answers, "high")
        return True if names is None else "sdxl" in names

    def installed_loras(self, models_dir):
        """Catalog LoRAs whose file is there, and by name."""
        return {
            item.model.name: item
            for item in models.inspect(list(self.catalog.loras.values()), models_dir)
            if item.state != models.MISSING
        }

    def lora_plan(self, answers, target, models_dir):
        """What `--loras` or the step ask for, or None if the LoRAs are left alone."""
        sdxl = target.pick("high", "sdxl") is not None and not self.legacy(answers.mode[1])
        # An answer to the step is dropped if SDXL 1.0 was left out afterwards.
        names = self.lora_arg if self.lora_arg is not None else (answers.loras if sdxl else None)

        if names is None:
            return None

        if not sdxl:
            raise ProvisionError(
                "LoRAs only work with the SDXL 1.0 quality model: add sdxl to "
                "--quality-models (with a quality or full profile). Nothing was changed."
            )

        extra = models.extra_search_paths(config.COMFY_DIR)
        wanted = [self.catalog.loras[name] for name in names]
        download = tuple(
            item for item in models.inspect(wanted, models_dir, extra) if item.state != models.PRESENT
        )
        delete = tuple(
            item
            for name, item in self.installed_loras(models_dir).items()
            if name not in names and self.records.is_owned(item.path)
        )
        return LoraPlan(tuple(names), download, delete)

    def steps(self, answers):
        found = []

        if self.asks_mode():
            found.append("mode")

        if self.asks_folder(answers):
            found.append("folder")

        if self.asks_profile():
            found.append("profile")

        base = answers.base

        for capability in manifest.CAPABILITIES:
            if not self.asks_models(capability, base):
                continue

            found.append(("models", capability))
            names = self.picked(answers, capability)

            for name in names or ():
                if self.options_count(capability, name) > 1:
                    found.append(("precision", capability, name))

            if names and len(names) > 1:
                found.append(("default", capability))

        if self.asks_loras(answers):
            found.append("loras")

        if self.asks_review(answers):
            found.append("review")

        return found

    def resolve_fixed(self, answers):
        """Lo que ya deciden los argumentos o la detección. Los errores salen antes de preguntar."""
        self.answers = answers

        if answers.mode is None and not self.asks_mode():
            answers.mode = self.place(
                choose_mode(self.args, self.detection, self.records, self.interactive)
            )

        if answers.base is None and not self.asks_profile():
            answers.base = choose_profile(self.args, self.detection, self.catalog, self.interactive)

        if answers.base is not None and answers.mode is not None and not answers.base.fixed:
            # Names, precisions and capabilities that don't exist fail before any question.
            self.request(answers)

    def plan(self, answers):
        mode, comfy_dir, default_port = answers.mode
        models_dir = self.models_dir(comfy_dir)
        target, profile, change = self.resolve_models(answers)
        torch = self.catalog.pytorch.get(self.detection.platform.index)
        folder = self.folder if mode == MANAGED and (self.folder_arg or not self.records.mode) else None
        loras = self.lora_plan(answers, target, models_dir)
        pending = models.pending_bytes(profile.models, models_dir)
        pending += loras.download_bytes if loras else 0
        return Plan(
            mode, comfy_dir, self.args.port or default_port, models_dir, target, profile,
            change, pending, torch, folder, loras,
            self.legacy(comfy_dir) and not change.legacy,
        )

def _ask_step(run, answers, name, back_label):
    """Pregunta un paso. Devuelve `menu.BACK` o None; la respuesta queda en `answers`."""
    args = run.args

    if name == "mode":
        result = choose_mode(
            args, run.detection, run.records, True, default=answers.mode, back_label=back_label
        )

        if result is not menu.BACK:
            answers.mode = run.place(result)

        return result

    if name == "folder":
        result = choose_folder(run, back_label)

        if result is not menu.BACK:
            run.folder = result
            kind, _, port = answers.mode
            answers.mode = (kind, (result or locations.default_install_dir()) / "comfyui", port)

        return result

    if name == "profile":
        default = answers.base.name if answers.base else None
        result = choose_profile(
            args, run.detection, run.catalog, True, default=default, back_label=back_label
        )

        if result is not menu.BACK:
            answers.base = result

        return result

    kind = name[0] if isinstance(name, tuple) else name
    base = answers.base

    if kind == "models":
        capability = name[1]
        installed = run.installed(answers.mode[1])
        have = [pick.model for pick in installed.of(capability)] if installed else []
        result = choose_models(
            run.catalog, capability, run.vram, have, run.picked(answers, capability), back_label
        )

        if result is not menu.BACK:
            answers.picks[capability] = result
            answers.picks_for = base.name

            for key in [k for k in answers.precisions if k[0] == capability and k[1] not in result]:
                del answers.precisions[key]

            if answers.defaults.get(capability) not in result:
                answers.defaults.pop(capability, None)

        return result

    if kind == "precision":
        _, capability, model = name
        installed = run.installed(answers.mode[1])
        default = answers.precisions.get((capability, model)) or (
            installed.pick(capability, model).precision
            if installed and installed.pick(capability, model)
            else None
        )
        result = choose_precision(run.catalog, capability, model, run.vram, default, back_label)

        if result is not menu.BACK:
            answers.precisions[(capability, model)] = result

        return result

    if kind == "default":
        capability = name[1]
        names = run.picked(answers, capability)
        installed = run.installed(answers.mode[1])
        default = answers.defaults.get(capability) or (
            installed.default(capability).model if installed and installed.default(capability) else None
        )
        result = choose_default(run.catalog, capability, names, default, back_label)

        if result is not menu.BACK:
            answers.defaults[capability] = result

        return result

    if name == "loras":
        models_dir = run.models_dir(answers.mode[1])
        installed = [
            lora_name
            for lora_name, item in run.installed_loras(models_dir).items()
            if item.state == models.PRESENT
        ]
        result = choose_loras(run.catalog, installed, answers.loras, back_label)

        if result is not menu.BACK:
            answers.loras = result

        return result

    return None


def _review(run, answers, ask):
    """Resumen y confirmación. Con `ask`, devuelve `menu.BACK` si se vuelve atrás."""
    plan = run.plan(answers)
    notes = []

    if plan.folder is not None:
        errors, notes = locations.split(run.folder_issues(plan.folder, plan))

        if errors:
            raise ProvisionError(
                "\n".join(errors) + "\nNothing was changed: choose another folder or a "
                "smaller profile."
            )

    notes += _fit_notes(run, plan)

    if not run.interactive:
        _say_recommended(run, answers, plan)

    if plan.legacy_kept:
        print(
            f"\nThis installation uses {selection.LEGACY_MODEL}, which is no longer offered, "
            f"so it is kept. To switch: imagehearth-mcp setup --quality-models sdxl"
        )

    if plan.change.changes_models:
        selection.show_change(plan.change, run.catalog)

        if not ask and not getattr(run.args, "yes", False):
            raise ProvisionError(
                "Nothing was changed. Non-interactive mode needs --yes to replace or "
                "remove installed models."
            )

        quality.require_idle()

    show_summary(
        run.catalog, plan.profile, plan.mode, plan.comfy_dir, plan.models_dir, plan.pending,
        plan.torch, plan.folder, notes, plan.loras,
    )
    _check_space(run, plan)

    if not ask:
        require_acceptance(run.args, run.interactive)
        return plan

    options = [menu.Option(True, "Accept the licenses above and install")]

    if menu.choose("", options, default=True) is menu.BACK:
        return menu.BACK

    return plan


def _fit_notes(run, plan):
    """A warning for each chosen model that doesn't fit this GPU without moving weights to RAM."""
    notes = []

    for capability, pick in plan.models.all():
        option = run.catalog.option_of(capability, pick)

        if run.vram and run.vram < option.min_vram_mib:
            title = run.catalog.catalog[pick.model].title
            notes.append(
                f"{title} {pick.precision} needs {option.min_vram_mib} MiB of GPU memory "
                f"to run without moving weights to RAM and this machine has {run.vram} MiB: "
                "it can be installed, but generation will be slower or may fail."
            )

    return notes


def _say_recommended(run, answers, plan):
    """Non-interactive: tell which models were chosen for the user, and how to choose others."""
    request = run.request(answers) if not answers.base.fixed else selection.Request()
    old = run.installed(answers.mode[1])

    for capability in plan.models.picks:
        if request.asks(capability) or (old and old.of(capability)) or answers.base.fixed:
            continue

        pick = plan.models.default(capability)
        print(
            f"\n{CAPABILITY_TITLES[capability].split(' (')[0]}: "
            f"{run.catalog.catalog[pick.model].title} {pick.precision}, recommended for "
            f"{run.vram or 'unknown'} MiB of GPU memory. Choose others with "
            f"{CAPABILITY_OPTIONS[capability]} ({', '.join(run.catalog.models_with(capability))})."
        )


def _check_space(run, plan):
    """The space a run needs against what is free, before anything is confirmed."""
    needs = {plan.models_dir: plan.pending}

    if plan.mode == MANAGED and not (Path(plan.comfy_dir) / "venv").exists():
        needs[plan.comfy_dir] = run.catalog.install_bytes(plan.torch)

    issues = preflight.check_disk(needs)
    errors = [issue.message for issue in issues if issue.level == preflight.ERROR]

    if errors:
        raise ProvisionError("\n".join(errors) + "\nNothing was changed.")


def _collect(run):
    """Los pasos de `setup`, con 0 para volver. None si se sale sin cambiar nada."""
    answers = Answers()
    index = 0
    plan = None

    while True:
        run.resolve_fixed(answers)
        steps = run.steps(answers)

        if index >= len(steps):
            return answers, plan

        name = steps[index]
        print(f"\nStep {index + 1} of {len(steps)}")
        back_label = "Exit without changing anything" if index == 0 else "Back"

        if name == "review":
            result = _review(run, answers, True)

            if result is not menu.BACK:
                return answers, result
        else:
            result = _ask_step(run, answers, name, back_label)

        if result is menu.BACK:
            if index == 0:
                print("Nothing was changed.")
                return None, None

            index -= 1
            continue

        index += 1


def _setup(args):
    # Before anything is downloaded.
    if getattr(args, "batch_limit", None) is not None and args.batch_limit < 1:
        raise ProvisionError("--batch-limit must be 1 or more.")

    if getattr(args, "install_dir", None) and args.attach:
        raise ProvisionError(
            "--install-dir and --attach can't be combined: --attach uses a ComfyUI that "
            "is already installed, and --install-dir says where ImageHearth installs one."
        )

    interactive = is_interactive(args)
    catalog = manifest.load()
    records = InstallManifest.load(config.INSTALL_MANIFEST)
    detection = detect.detect(disk_path=config.DATA_DIR, extra_paths=[config.COMFY_DIR])

    # La carpeta propia de una instalación anterior no es un ComfyUI ajeno.
    detection.comfy_installs = [
        install
        for install in detection.comfy_installs
        if not records.is_owned(install.path)
    ]

    gpu = detection.primary_gpu
    print(
        f"System: {detection.system} {detection.machine}, "
        f"GPU: {gpu.name if gpu and gpu.name else 'none detected'}, "
        f"PyTorch: {detection.platform.index} (tier {detection.platform.tier})"
    )

    require_experimental(args, detection)

    run_state = _Run(args, catalog, records, detection, interactive)
    answers, plan = _collect(run_state)

    if answers is None:
        return 0

    if plan is None:
        plan = _review(run_state, answers, False)

    mode, comfy_dir, port = plan.mode, plan.comfy_dir, plan.port
    models_dir, profile = plan.models_dir, plan.profile
    change, pending, torch = plan.change, plan.pending, plan.torch

    run_preflight(detection, profile, torch, mode, comfy_dir, models_dir, port, pending, catalog)

    if plan.folder is not None:
        _claim_folder(records, plan.folder)

    records.mode = mode
    records.comfy_dir = str(comfy_dir)
    records.models_dir = str(models_dir)
    records.save()

    if mode == MANAGED:
        comfyui.install_managed(catalog.comfyui, torch, comfy_dir, records)
    else:
        install_attached(args, comfy_dir, records, interactive)

    install_nodes(args, profile, comfy_dir, records, mode, interactive)

    if args.models_dir:
        block = comfyui.write_extra_model_paths(comfy_dir, models_dir, records)

        if block:
            print(
                f"WARNING: add this to {Path(comfy_dir) / comfyui.EXTRA_PATHS_FILE} "
                f"so ComfyUI finds the models:\n{block}"
            )

    apply_config(args, mode, comfy_dir, port, records, models_dir)

    models.ensure_models(profile.models, models_dir, records)
    records.profile = _higher_profile(records.profile, profile.base)

    if plan.loras is not None:
        models.ensure_models(
            [catalog.loras[name] for name in plan.loras.names], models_dir, records
        )

    # Only now that the models are verified: until then the previous ones are the record.
    selection.record(records, profile, legacy=plan.legacy_kept)

    records.save()

    if plan.loras is not None and plan.loras.delete:
        for failure in quality.delete_items(plan.loras.delete, records):
            print(f"WARNING: could not delete {failure}")

    if change.delete:
        for failure in quality.delete_items(change.delete, records):
            print(f"WARNING: could not delete {failure}")

    if change.changes_models or change.delete:
        quality.restart_comfyui()

    if args.skip_smoke_test:
        print("\nDone. Test image skipped.")
    else:
        print(f"\nDone. Test image: {smoke.run_smoke()}")

    print("Check the installation at any time with `imagehearth-mcp doctor`.")
    return 0


def run(args):
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)

    try:
        with locks.held(config.SETUP_LOCK, timeout=1):
            return _setup(args)
    except TimeoutError:
        raise ProvisionError(
            "Another setup, update or uninstall is running. Wait for it to finish."
        ) from None
