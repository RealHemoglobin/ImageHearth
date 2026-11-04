"""Subcomando `doctor`: comprueba cada capa y dice cómo arreglar lo que falle."""

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from importlib.metadata import PackageNotFoundError, version

import requests

SCHEMA = 1
OK = "ok"
WARN = "warn"
FAIL = "fail"
SKIP = "skip"
TORCH_TIMEOUT = 120
# Salida estable de --json: estas capas, siempre y en este orden.
LAYERS = (
    "package",
    "config",
    "path",
    "comfyui",
    "environment",
    "node",
    "custom_nodes",
    "models",
    "gpu",
    "port",
    "ollama",
    "memory",
)
RERUN_SETUP = "Run `imagehearth-mcp setup`."


@dataclass
class Check:
    layer: str
    status: str
    message: str
    fix: str = ""
    details: dict = field(default_factory=dict)


def check_package():
    from imagehearth_mcp.provisioner import ProvisionError, manifest

    try:
        package_version = version("imagehearth-mcp")
        catalog = manifest.load()
    except (PackageNotFoundError, ProvisionError) as error:
        return (
            Check(
                "package",
                FAIL,
                str(error),
                "Reinstall with `uv tool install --force imagehearth-mcp`.",
            ),
            None,
        )

    return Check("package", OK, f"imagehearth-mcp {package_version}"), catalog


def tool_bin_dir(run=subprocess.run):
    """Directory where uv puts the command, or None if uv can't say."""
    try:
        result = run(
            ["uv", "tool", "dir", "--bin"], capture_output=True, text=True, timeout=15
        )
    except (OSError, subprocess.SubprocessError):
        return None

    return result.stdout.strip() or None if result.returncode == 0 else None


def path_fix_command(bin_dir, system=sys.platform, shell=None):
    """The exact command that puts `bin_dir` in the PATH of new terminals."""
    if system == "win32":
        return (
            "[Environment]::SetEnvironmentVariable('Path', "
            f"\"$([Environment]::GetEnvironmentVariable('Path', 'User'));{bin_dir}\", 'User')"
        )

    name = os.path.basename(shell or os.environ.get("SHELL", ""))

    if name == "fish":
        return f'fish_add_path "{bin_dir}"'

    rc = "~/.zshenv" if name == "zsh" else "~/.profile"
    return f"echo 'export PATH=\"{bin_dir}:$PATH\"' >> {rc}"


def check_path(run=subprocess.run, which=shutil.which, system=sys.platform):
    """The command must be found by name from a new terminal, not only by absolute path."""
    found = which("imagehearth-mcp")

    if found:
        return Check("path", OK, f"imagehearth-mcp is in the PATH ({found}).")

    bin_dir = tool_bin_dir(run)

    if bin_dir is None:
        return Check(
            "path",
            WARN,
            "imagehearth-mcp is not in the PATH.",
            "Run `uv tool update-shell` and open a new terminal.",
        )

    return Check(
        "path",
        WARN,
        f"imagehearth-mcp is not in the PATH; {bin_dir} is missing. Agents are unaffected: "
        "they use the absolute path.",
        f"Run `uv tool update-shell` and open a new terminal, or: {path_fix_command(bin_dir, system)}",
        details={"bin_dir": bin_dir},
    )


def check_config():
    from imagehearth_mcp.engine.errors import ConfigError

    try:
        from imagehearth_mcp.engine import config
    except ConfigError as error:
        return (
            Check("config", FAIL, str(error), "Fix the value named in the message."),
            None,
        )

    return Check("config", OK, f"Using {config.CONFIG_FILE}"), config


def check_comfyui(config, records):
    from imagehearth_mcp.provisioner.detect import is_comfy_dir

    desktop = (config.COMFY_DIR / "custom_nodes").is_dir() and not (
        config.COMFY_DIR / "main.py"
    ).exists()

    if is_comfy_dir(config.COMFY_DIR) or desktop:
        details = {
            "path": str(config.COMFY_DIR),
            "mode": records.mode,
            "pinned_version": records.comfyui_version,
        }
        return Check("comfyui", OK, f"Found in {config.COMFY_DIR}", details=details)

    return Check(
        "comfyui",
        FAIL,
        f"ComfyUI not found in {config.COMFY_DIR}.",
        RERUN_SETUP,
    )


def check_environment(config, run):
    from imagehearth_mcp.platform import paths

    python = paths.find_venv_python(config.COMFY_DIR)

    if not python.exists():
        if not (config.COMFY_DIR / "main.py").exists():
            return Check(
                "environment", SKIP, "No Python environment to check (ComfyUI Desktop?)."
            )

        return Check(
            "environment", FAIL, f"Python not found: {python}", RERUN_SETUP
        )

    code = (
        "import torch; print(torch.__version__, torch.cuda.is_available(), "
        "torch.backends.mps.is_available())"
    )

    try:
        result = run(
            [str(python), "-c", code],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=TORCH_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return Check("environment", FAIL, f"Can't run {python}: {error}", RERUN_SETUP)

    if result.returncode != 0:
        return Check(
            "environment",
            FAIL,
            f"PyTorch can't be imported in {python}.",
            RERUN_SETUP,
        )

    torch_version, *flags = result.stdout.strip().split()
    return Check(
        "environment",
        OK,
        f"PyTorch {torch_version}",
        details={
            "torch": torch_version,
            "cuda_available": flags[:1] == ["True"],
            "mps_available": flags[1:2] == ["True"],
        },
    )


def check_node(config, session):
    init = config.COMFY_DIR / "custom_nodes" / config.STATUS_NODE / "__init__.py"
    fix = "Run `imagehearth-mcp setup --install-node`, then restart ComfyUI."

    try:
        match = re.search(
            r"^VERSION = (\d+)", init.read_text(encoding="utf-8"), re.MULTILINE
        )
    except OSError:
        return Check("node", FAIL, f"The status node is missing: {init}", fix)

    installed = int(match.group(1)) if match else None

    if installed != config.STATUS_NODE_VERSION:
        return Check(
            "node",
            FAIL,
            f"The status node has version {installed}, and this package expects "
            f"{config.STATUS_NODE_VERSION}.",
            fix,
        )

    try:
        response = session.get(f"{config.COMFY_API}{config.STATUS_ROUTE}", timeout=3)
    except requests.RequestException:
        return Check("node", OK, f"Installed, version {installed}.")

    if response.status_code != 200:
        return Check(
            "node",
            WARN,
            "The node is installed, but the running ComfyUI has not loaded it.",
            "Restart ComfyUI.",
        )

    return Check("node", OK, f"Installed and loaded, version {installed}.")


def check_custom_nodes(config, records, catalog):
    """Nodos que pide el perfil instalado, como ComfyUI-GGUF en los perfiles mac-*."""
    from imagehearth_mcp.provisioner import comfyui

    profile = catalog.profiles.get(records.profile)
    nodes = profile.nodes if profile else ()

    if not nodes:
        return Check("custom_nodes", SKIP, "The installed profile needs none.")

    missing = [
        node.folder
        for node in nodes
        if not (config.COMFY_DIR / "custom_nodes" / node.folder).is_dir()
    ]

    if missing:
        return Check(
            "custom_nodes",
            FAIL,
            f"Missing: {', '.join(missing)}.",
            f"Run `imagehearth-mcp setup --profile {profile.name} --install-node`.",
        )

    outdated = [
        node.folder
        for node in nodes
        if records.is_owned(config.COMFY_DIR / "custom_nodes" / node.folder)
        and not comfyui.custom_node_is_current(node, config.COMFY_DIR)
    ]

    if outdated:
        return Check(
            "custom_nodes",
            WARN,
            f"Not the pinned version: {', '.join(outdated)}.",
            "Run `imagehearth-mcp update`.",
        )

    return Check(
        "custom_nodes", OK, f"Installed: {', '.join(node.folder for node in nodes)}."
    )


def check_models(config, records, catalog, verify_hashes, system):
    from imagehearth_mcp.provisioner import models

    models_dir = models.resolve_dir(records, config.COMFY_DIR)
    profiles = catalog.profiles_for(system)
    extra_paths = models.extra_search_paths(config.COMFY_DIR)
    expected = records.profile or next(iter(profiles), "fast")
    problems = {}
    complete = {}

    for name, profile in profiles.items():
        states = models.inspect(profile.models, models_dir, extra_paths)
        bad = [item for item in states if item.state != models.PRESENT]

        if verify_hashes:
            bad += [
                item
                for item in states
                if item.state == models.PRESENT
                and models.sha256(item.path) != item.model.sha256
            ]

        complete[name] = not bad

        if name == expected:
            problems = {item.model.name: str(item.path) for item in bad}

    details = {"models_dir": str(models_dir), "profile": expected, "profiles": complete}

    if problems:
        return Check(
            "models",
            FAIL,
            f"Profile {expected}: missing or damaged: {', '.join(problems)}.",
            f"Run `imagehearth-mcp setup --profile {expected}`.",
            {**details, "problems": problems},
        )

    method = "SHA-256" if verify_hashes else "size"
    return Check(
        "models", OK, f"Profile {expected} complete (checked by {method}).", details=details
    )


def check_gpu(detection):
    gpu = detection.primary_gpu
    platform = detection.platform
    details = {"index": platform.index, "tier": platform.tier}

    if detection.driver_missing:
        return Check(
            "gpu",
            FAIL,
            "An NVIDIA GPU is present but nvidia-smi does not work.",
            "Install the current driver from https://www.nvidia.com/drivers and reboot.",
            details,
        )

    if not platform.supported:
        return Check("gpu", WARN, platform.note, details=details)

    if platform.tier > 1:
        return Check("gpu", WARN, platform.note, details=details)

    return Check(
        "gpu",
        OK,
        f"{gpu.name}, {gpu.vram_mib} MiB, driver {gpu.driver}",
        details=details,
    )


def comfy_arguments(config, detection):
    """The memory arguments ComfyUI starts with here: chosen for the hardware, then comfy_args."""
    from imagehearth_mcp.engine import comfy_args

    gpu = detection.primary_gpu
    return comfy_args.effective((detection.system, gpu.vram_mib if gpu else 0, detection.ram_mib))


def check_port(config, session):
    from imagehearth_mcp.provisioner.preflight import port_is_open

    port = config.COMFY_PORT

    if not port_is_open(port):
        return Check("port", OK, f"Port {port} is free; ComfyUI starts on demand.")

    try:
        running = session.get(f"{config.COMFY_API}/system_stats", timeout=3).ok
    except requests.RequestException:
        running = False

    if running:
        return Check("port", OK, f"ComfyUI is running on port {port}.")

    return Check(
        "port",
        FAIL,
        f"Port {port} is in use by something that is not ComfyUI.",
        f"Close it, or set another comfy_port in {config.CONFIG_FILE}.",
    )


def check_ollama(config, session):
    if config.memory_mode() != "auto":
        return Check("ollama", SKIP, f"Not touched: memory_mode = {config.memory_mode()}.")

    try:
        running = session.get(f"{config.OLLAMA_API}/api/version", timeout=3).ok
    except requests.RequestException:
        running = False

    if running:
        return Check("ollama", OK, f"Running at {config.OLLAMA_API}.")

    return Check("ollama", SKIP, "Not running. It is optional.")


def check_memory():
    """Modo de memoria y servidores detectados; ninguno de ellos es obligatorio."""
    from imagehearth_mcp.engine import memory

    state = memory.describe()
    running = [name for name, item in state["servers"].items() if item["status"] == "running"]
    found = f" Servers responding: {', '.join(running) or 'none'}." if state["mode"] == "auto" else ""
    return Check("memory", OK, f"memory_mode = {state['mode']}.{found}", details=state)


def collect(verify_hashes=False, session=requests, run=subprocess.run, detection=None):
    """Una comprobación por capa; una capa que depende de otra rota queda en skip."""
    checks = {}
    package, catalog = check_package()
    checks["package"] = package
    configuration, config = check_config()
    checks["config"] = configuration
    checks["path"] = check_path(run)

    if config is not None:
        from imagehearth_mcp.provisioner import ProvisionError, detect
        from imagehearth_mcp.provisioner.install_manifest import InstallManifest

        try:
            records = InstallManifest.load(config.INSTALL_MANIFEST)
        except ProvisionError as error:
            checks["config"] = Check(
                "config", FAIL, str(error), "Move that file away and run setup again."
            )
            records = InstallManifest(config.INSTALL_MANIFEST)

        checks["comfyui"] = check_comfyui(config, records)

        if checks["comfyui"].status == OK:
            checks["environment"] = check_environment(config, run)
            checks["node"] = check_node(config, session)

        detection = detection or detect.detect(extra_paths=[config.COMFY_DIR])

        if checks["comfyui"].status == OK and catalog is not None:
            checks["custom_nodes"] = check_custom_nodes(config, records, catalog)
            checks["models"] = check_models(
                config, records, catalog, verify_hashes, detection.system
            )

        checks["gpu"] = check_gpu(detection)
        checks["gpu"].details["comfy_args"] = comfy_arguments(config, detection)
        checks["port"] = check_port(config, session)
        checks["ollama"] = check_ollama(config, session)
        checks["memory"] = check_memory()

    return [
        checks.get(layer) or Check(layer, SKIP, "Skipped: a layer it needs failed.")
        for layer in LAYERS
    ]


def to_json(checks):
    return {
        "schema": SCHEMA,
        "ok": all(check.status != FAIL for check in checks),
        "checks": [asdict(check) for check in checks],
    }


def run(args):
    checks = collect(args.verify_hashes)

    if args.json:
        print(json.dumps(to_json(checks), indent=2))
    else:
        for check in checks:
            print(f"[{check.status.upper():4}] {check.layer:12} {check.message}")

            if check.fix:
                print(f"       fix: {check.fix}")

    return 0 if to_json(checks)["ok"] else 1
