"""Subcomando `setup`: lleva una máquina a un sistema que genera imágenes."""

import os
import sys
from pathlib import Path

from imagehearth_mcp.engine import comfyui_manager, config
from imagehearth_mcp.platform import locks
from imagehearth_mcp.provisioner import (
    ProvisionError,
    comfyui,
    detect,
    manifest,
    models,
    preflight,
    settings,
    smoke,
)
from imagehearth_mcp.provisioner.install_manifest import InstallManifest
from imagehearth_mcp.provisioner.manifest import format_size

ATTACHED = "attached"
MANAGED = preflight.MANAGED
PROFILE_ORDER = ("fast", "quality", "full", "mac-fast", "mac-quality", "mac-full")
UNTESTED_MACOS = (
    "macOS is prepared but has never been run on a real Mac: ComfyUI, ComfyUI-GGUF, "
    "FLUX and Kontext may not work on MPS."
)


def is_interactive(args):
    return not args.non_interactive and sys.stdin.isatty()


def ask(question):
    return input(f"{question} [y/N] ").strip().lower() in ("y", "yes")


def propose_profile(detection, catalog):
    """El mayor perfil que caben en la memoria de la GPU y en el disco."""
    gpu = detection.primary_gpu
    vram = gpu.vram_mib if gpu else 0
    profiles = catalog.profiles_for(detection.system)
    proposed = next(iter(profiles), "fast")

    for name, profile in profiles.items():
        if vram >= profile.min_vram_mib and detection.disk_free_bytes > profile.bytes:
            proposed = name

    return proposed


def choose_profile(args, detection, catalog, interactive):
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

    print("\nProfiles:")

    for name, profile in profiles.items():
        print(f"  {name:8} {format_size(profile.bytes):>8}  {profile.description}")

    answer = input(f"Profile [{proposed}]: ").strip().lower() or proposed

    if answer not in profiles:
        raise ProvisionError(f"Unknown profile {answer!r}.")

    return profiles[answer]


def choose_mode(args, detection, records, interactive):
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

    print("\nFound an existing ComfyUI. Using it avoids duplicating tens of GB:")

    for number, install in enumerate(detection.comfy_installs, start=1):
        print(f"  {number}. {install.path} ({install.kind})")

    print("  m. Install a separate ComfyUI managed by ImageHearth")
    answer = input("Choice [1]: ").strip().lower() or "1"

    if answer == "m":
        return MANAGED, default_dir, config.COMFY_PORT

    try:
        install = detection.comfy_installs[int(answer) - 1]
    except (ValueError, IndexError):
        raise ProvisionError(f"Invalid choice {answer!r}.") from None

    port = detect.DESKTOP_PORT if install.kind == "desktop" else config.COMFY_PORT
    return ATTACHED, Path(install.path), port


def show_summary(catalog, profile, mode, comfy_dir, models_dir, pending, torch=None):
    print(f"\nProfile: {profile.name} ({profile.description})")
    print(f"ComfyUI: {mode}, {comfy_dir}")
    print(f"Models:  {models_dir}")
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

    print(f"  Models to download: {format_size(pending)}")
    print("\nLicenses you accept by downloading them:")

    for entry in catalog.licenses_for(profile):
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

    if not ask("Accept these licenses and start downloading?"):
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
            allowed = ask(f"Install {node.folder}, which this profile needs, in {comfy_dir}?")

        if not comfyui.install_custom_node(node, comfy_dir, records, allowed):
            raise ProvisionError(
                f"The {profile.name} profile needs {node.folder}, which was not "
                "installed. Add --install-node to allow it."
            )


def install_attached(args, comfy_dir, records, interactive):
    allowed = args.install_node

    if not allowed and interactive and not comfyui.node_is_current(comfy_dir):
        allowed = ask(f"Install the ImageHearth status node in {comfy_dir}?")

    if not comfyui.install_node(comfy_dir, records, allowed):
        print(
            "WARNING: the status node was not installed. Generation works, but GPU "
            "memory is checked less reliably. Add --install-node to install it."
        )


def _higher_profile(current, new):
    if current not in PROFILE_ORDER:
        return new

    return max(current, new, key=PROFILE_ORDER.index)


def apply_config(args, mode, comfy_dir, port, records):
    values = {}

    if mode == ATTACHED or Path(config.COMFY_DIR) != Path(comfy_dir):
        values["comfy_dir"] = str(comfy_dir)

    if mode == ATTACHED or args.port or port != config.COMFY_PORT:
        values["comfy_port"] = port

    settings.apply(config.CONFIG_FILE, values, records)

    if os.environ.get("IMAGEHEARTH_COMFY_DIR") and "comfy_dir" in values:
        print(
            "WARNING: IMAGEHEARTH_COMFY_DIR is set and overrides the folder written "
            f"to {config.CONFIG_FILE}."
        )


def _setup(args):
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

    mode, comfy_dir, default_port = choose_mode(args, detection, records, interactive)
    profile = choose_profile(args, detection, catalog, interactive)
    port = args.port or default_port
    models_dir = Path(args.models_dir).expanduser().resolve() if args.models_dir else None
    models_dir = models_dir or models.resolve_dir(records, comfy_dir)
    pending = models.pending_bytes(profile.models, models_dir)
    torch = catalog.pytorch.get(detection.platform.index)

    show_summary(catalog, profile, mode, comfy_dir, models_dir, pending, torch)
    require_acceptance(args, interactive)

    run_preflight(detection, profile, torch, mode, comfy_dir, models_dir, port, pending, catalog)

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

    apply_config(args, mode, comfy_dir, port, records)

    models.ensure_models(profile.models, models_dir, records)
    records.profile = _higher_profile(records.profile, profile.name)
    records.save()

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
