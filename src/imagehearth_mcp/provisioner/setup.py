"""Subcomando `setup`: lleva una máquina a un sistema que genera imágenes."""

import os
import sys
from dataclasses import dataclass
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
        size = catalog.resolve(profile, None, vram).bytes if _fits_resolve(catalog, profile, vram) else 0

        if vram >= catalog.min_vram_mib(profile) and detection.disk_free_bytes > size:
            proposed = name

    return proposed


def _fits_resolve(catalog, profile, vram):
    try:
        catalog.resolve(profile, None, vram)
    except ProvisionError:
        return False

    return True


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


@dataclass(frozen=True)
class Selection:
    """El modelo de `quality` elegido. `legacy`: se mantiene RealVisXL."""

    name: str | None = None
    legacy: bool = False


def choose_quality_model(
    args, catalog, profile, vram, installed, interactive, default=None, back_label="Back"
):
    """Qué modelo de `quality` se instala. Los perfiles sin `quality` no tienen."""
    asked = getattr(args, "quality_model", None)

    if not profile.quality:
        if asked:
            raise ProvisionError(
                f"The {profile.name} profile has no quality model: --quality-model "
                "only applies to quality and full."
            )

        return Selection()

    names = ", ".join(catalog.quality_models)

    if asked:
        if asked not in catalog.quality_models:
            raise ProvisionError(f"Unknown quality model {asked!r}. Choose one of: {names}.")

        return Selection(asked)

    if installed is not None and installed.legacy:
        # Nada destructivo sin que el usuario lo pida: RealVisXL sigue generando.
        sdxl = catalog.quality_models["sdxl"].title
        print(f"\nThis installation uses {quality.LEGACY}, which is no longer offered.")

        if interactive:
            switch = menu.confirm(
                f"Switch to {sdxl} and delete {quality.LEGACY}?", allow_back=True
            )

            if switch is menu.BACK:
                return menu.BACK

            if switch:
                return Selection("sdxl")

        print(f"Keeping {quality.LEGACY}. To switch: imagehearth-mcp setup --quality-model sdxl")
        return Selection("sdxl", legacy=True)

    if installed is not None and not interactive:
        return Selection(installed.name)

    recommended = catalog.recommend(vram)

    if not interactive:
        print(
            f"\nQuality model: {catalog.quality_model(recommended).title}, recommended for "
            f"{vram or 'unknown'} MiB of GPU memory. Choose another with --quality-model "
            f"({names})."
        )
        return Selection(recommended)

    if default not in catalog.quality_models:
        default = installed.name if installed and not installed.legacy else recommended

    options = []

    for info in quality.choices(catalog, vram, installed):
        first, _, rest = quality.format_choice(info).partition("\n")
        options.append(menu.Option(info["name"], first, rest.strip()))

    answer = menu.choose(
        "Quality models (only one is installed at a time):",
        options,
        default=default,
        back_label=back_label,
    )

    return answer if answer is menu.BACK else Selection(answer)


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

    if profile.quality_model:
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


def _plan_change(args, catalog, records, models_dir, base, profile, installed, selection, vram):
    """El cambio de modelo de `quality` que pide esta ejecución, sin confirmar; o None."""
    if not profile.quality or installed is None or selection.legacy:
        return None

    if not installed.legacy and installed.name == selection.name:
        return None

    effective = catalog.profiles[_higher_profile(records.profile, base.name)]
    old = quality.resolve_for(
        catalog, effective, installed, vram, records.precision, records.edit_precision
    )
    keep = catalog.resolve(effective, selection.name, vram, getattr(args, "variant", None))
    return quality.plan_change(catalog, records, models_dir, old, profile, keep, installed)


@dataclass
class Answers:
    """Lo respondido hasta ahora. Se conserva al volver atrás."""

    mode: tuple | None = None
    base: object = None
    quality: Selection | None = None
    quality_for: str | None = None
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
    selection: Selection
    profile: object
    change: object
    pending: int
    torch: object
    folder: Path | None = None
    loras: LoraPlan | None = None


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
        if answers.base is None:
            return None

        try:
            return self._profile(answers.base, self._selection(answers) or Selection())
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
        return quality.current(self.catalog, self.records, self.models_dir(comfy_dir))

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

    def asks_quality(self, base):
        return bool(
            self.interactive
            and base is not None
            and base.quality
            and not getattr(self.args, "quality_model", None)
        )

    def _may_ask_quality(self, base):
        """Antes de elegir perfil, se cuenta el paso del modelo si algún perfil lo tiene."""
        if base is not None or not self.asks_profile() or getattr(self.args, "quality_model", None):
            return False

        profiles = self.catalog.profiles_for(self.detection.system)
        return any(profile.quality for profile in profiles.values())

    def asks_review(self, answers):
        """La confirmación final: licencias y, con un cambio de modelo, ese cambio."""
        args = self.args

        if not self.interactive:
            return False

        if not args.accept_licenses:
            return True

        if getattr(args, "yes", False):
            return False

        if answers.mode is None or answers.base is None:
            return False

        selection = self._selection(answers)

        if selection is None:
            return False

        comfy_dir = answers.mode[1]
        installed = self.installed(comfy_dir)
        profile = self._profile(answers.base, selection)
        change = _plan_change(
            args, self.catalog, self.records, self.models_dir(comfy_dir), answers.base,
            profile, installed, selection, self.vram,
        )
        loras = self.lora_plan(answers, selection, self.models_dir(comfy_dir))
        return change is not None or bool(loras and loras.delete)

    def _quality_is_sdxl(self, answers, base):
        """Whether the quality model is (or can still end up being) SDXL 1.0."""
        asked = getattr(self.args, "quality_model", None)

        if asked:
            return asked == "sdxl"

        if answers.quality_for == base.name and answers.quality is not None:
            return answers.quality.name == "sdxl" and not answers.quality.legacy

        return True

    def asks_loras(self, answers):
        """The LoRAs step: interactive, SDXL 1.0 and no `--loras` already saying it."""
        if not self.interactive or self.lora_arg is not None or not self.catalog.loras:
            return False

        base = answers.base

        if base is None:
            asked = getattr(self.args, "quality_model", None)
            profiles = self.catalog.profiles_for(self.detection.system)
            return any(p.quality for p in profiles.values()) and (not asked or asked == "sdxl")

        return base.quality and self._quality_is_sdxl(answers, base)

    def installed_loras(self, models_dir):
        """Catalog LoRAs whose file is there, and by name."""
        return {
            item.model.name: item
            for item in models.inspect(list(self.catalog.loras.values()), models_dir)
            if item.state != models.MISSING
        }

    def lora_plan(self, answers, selection, models_dir):
        """What `--loras` or the step ask for, or None if the LoRAs are left alone."""
        sdxl = selection is not None and selection.name == "sdxl" and not selection.legacy
        # An answer to the step is dropped if the model was changed afterwards.
        names = self.lora_arg if self.lora_arg is not None else (answers.loras if sdxl else None)

        if names is None:
            return None

        if not sdxl:
            raise ProvisionError(
                "LoRAs only work with the SDXL 1.0 quality model: use --quality-model sdxl "
                "with a quality or full profile. Nothing was changed."
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

    def _selection(self, answers):
        if answers.base is None:
            return None

        if not answers.base.quality:
            return Selection()

        return answers.quality

    def _profile(self, base, selection):
        forced = getattr(self.args, "variant", None)

        if selection.legacy:
            return self.catalog.legacy_profile(base, self.vram, forced)

        return self.catalog.resolve(base, selection.name, self.vram, forced)

    def steps(self, answers):
        found = []

        if self.asks_mode():
            found.append("mode")

        if self.asks_folder(answers):
            found.append("folder")

        if self.asks_profile():
            found.append("profile")

        if self.asks_quality(answers.base) or self._may_ask_quality(answers.base):
            found.append("quality")

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

        base = answers.base

        if (
            base is not None
            and answers.mode is not None
            and not self.asks_quality(base)
            and answers.quality_for != base.name
        ):
            answers.quality = choose_quality_model(
                self.args, self.catalog, base, self.vram,
                self.installed(answers.mode[1]), self.interactive,
            )
            answers.quality_for = base.name

    def plan(self, answers):
        mode, comfy_dir, default_port = answers.mode
        selection = self._selection(answers)
        base = answers.base
        models_dir = self.models_dir(comfy_dir)
        installed = self.installed(comfy_dir)
        profile = self._profile(base, selection)
        change = _plan_change(
            self.args, self.catalog, self.records, models_dir, base, profile, installed,
            selection, self.vram,
        )
        torch = self.catalog.pytorch.get(self.detection.platform.index)
        folder = self.folder if mode == MANAGED and (self.folder_arg or not self.records.mode) else None
        loras = self.lora_plan(answers, selection, models_dir)
        pending = models.pending_bytes(profile.models, models_dir)
        pending += loras.download_bytes if loras else 0
        return Plan(
            mode, comfy_dir, self.args.port or default_port, models_dir, selection, profile,
            change, pending, torch, folder, loras,
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
            answers.quality_for = None

        return result

    if name == "folder":
        result = choose_folder(run, back_label)

        if result is not menu.BACK:
            run.folder = result
            kind, _, port = answers.mode
            answers.mode = (kind, (result or locations.default_install_dir()) / "comfyui", port)
            answers.quality_for = None

        return result

    if name == "profile":
        default = answers.base.name if answers.base else None
        result = choose_profile(
            args, run.detection, run.catalog, True, default=default, back_label=back_label
        )

        if result is not menu.BACK:
            answers.base = result

        return result

    if name == "quality":
        comfy_dir = answers.mode[1]
        default = answers.quality.name if answers.quality and not answers.quality.legacy else None
        result = choose_quality_model(
            args, run.catalog, answers.base, run.vram, run.installed(comfy_dir), True,
            default=default, back_label=back_label,
        )

        if result is not menu.BACK:
            answers.quality = result
            answers.quality_for = answers.base.name

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

    if plan.profile.variant_of:
        print(
            f"\nFor {run.vram} MiB of GPU memory the {plan.profile.variant_of} profile "
            "uses its gguf variant."
        )

    if plan.change is not None:
        quality.show_change(plan.change, run.catalog)

        if not ask and not getattr(run.args, "yes", False):
            raise ProvisionError(
                "Nothing was changed. Non-interactive mode needs --yes to switch the "
                "quality model."
            )

        quality.require_idle()

    show_summary(
        run.catalog, plan.profile, plan.mode, plan.comfy_dir, plan.models_dir, plan.pending,
        plan.torch, plan.folder, notes, plan.loras,
    )

    if not ask:
        require_acceptance(run.args, run.interactive)
        return plan

    options = [menu.Option(True, "Accept the licenses above and install")]

    if menu.choose("", options, default=True) is menu.BACK:
        return menu.BACK

    return plan


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
    models_dir, profile, selection = plan.models_dir, plan.profile, plan.selection
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

    if profile.quality and not selection.legacy:
        # Only now that the model is verified: until then the previous one is the record.
        records.quality_model = profile.quality_model
        records.precision = profile.precision
        records.edit_precision = profile.edit_precision

    records.save()

    if plan.loras is not None and plan.loras.delete:
        for failure in quality.delete_items(plan.loras.delete, records):
            print(f"WARNING: could not delete {failure}")

    if change is not None:
        for failure in quality.delete_old(change, records):
            print(f"WARNING: could not delete {failure}")

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
