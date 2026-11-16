"""Instalación pedida desde un agente: `setup_status`, `setup_start` y su proceso.

`setup_start` lanza este módulo desacoplado, de modo que la instalación sobrevive
a la desconexión. El progreso queda en un archivo de estado.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from imagehearth_mcp.engine import config
from imagehearth_mcp.platform import files, locks, processes, spawn
from imagehearth_mcp.provisioner import (
    ProvisionError,
    detect,
    locations,
    manifest,
    models,
    quality,
    selection,
)
from imagehearth_mcp.provisioner.install_manifest import InstallManifest

RUNNING = "running"
FINISHED = "finished"
FAILED = "failed"
INTERRUPTED = "interrupted"
LOG_TAIL_LINES = 8


def _write_job(**fields):
    config.SETUP_JOB_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = config.SETUP_JOB_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps({**_read_job(), **fields}), encoding="utf-8")
    files.replace(temporary, config.SETUP_JOB_FILE)


def _read_job():
    try:
        return json.loads(config.SETUP_JOB_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _job_alive(job):
    return bool(job.get("pid")) and processes.is_same_process(
        job["pid"], job.get("create_time")
    )


def _log_tail():
    try:
        lines = config.SETUP_JOB_LOG.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    # Las barras de descarga reescriben la línea con retornos de carro.
    lines = [line.rsplit("\r", 1)[-1] for line in lines.splitlines()]
    return [line for line in lines if line.strip()][-LOG_TAIL_LINES:]


def _downloaded_bytes(job, catalog, models_dir):
    """Lo ya descargado del perfil, contando los `.part` a medias."""
    profile = catalog.profiles.get(job.get("profile"))

    if profile is None:
        return None

    try:
        if job.get("models"):
            picks = {
                cap: tuple(catalog.parse_pick(cap, text) for text in texts)
                for cap, texts in job["models"].items()
            }
            wanted = manifest.ModelSet(picks, job.get("defaults") or {})
            profile = catalog.build_set(selection.profile_for(catalog, profile, wanted), wanted)
        else:
            profile = catalog.resolve(
                profile, job.get("quality_model") or None, job.get("vram_mib") or 0
            )
    except ProvisionError:
        return None

    done = 0

    for item in models.inspect(profile.models, models_dir):
        part = models_dir / models.STAGING_DIR / f"{item.model.name}.part"

        if item.state == models.PRESENT:
            done += item.model.bytes
        elif part.exists():
            done += part.stat().st_size

    return {"downloaded": done, "total": profile.bytes}


def _job_status(catalog, models_dir):
    job = _read_job()

    if not job:
        return {"state": "none"}

    if job.get("state") == RUNNING and not _job_alive(job):
        job["state"] = INTERRUPTED
        job["error"] = (
            "The installation process stopped. Call setup_start again to continue "
            "where it left off."
        )

    return {
        "state": job.get("state"),
        "profile": job.get("profile"),
        "quality_model": job.get("quality_model") or None,
        "models": job.get("models") or None,
        "error": job.get("error"),
        "model_bytes": _downloaded_bytes(job, catalog, models_dir),
        "log": str(config.SETUP_JOB_LOG),
        "log_tail": _log_tail(),
    }


def _lora_entries(catalog, models_dir, extra, records):
    """The LoRA catalog with the size and license of each and whether it is installed."""
    installed = {
        item.model.name
        for item in models.inspect(list(catalog.loras.values()), models_dir, extra)
        if item.state == models.PRESENT
    }
    entries = []

    for lora in catalog.loras.values():
        license = catalog.licenses[lora.license]
        entries.append(
            {
                "name": lora.name,
                "description": lora.description,
                "category": lora.category,
                "download_mb": round(lora.bytes / 1e6),
                "license": {"name": license.name, "url": license.url, "summary": license.summary},
                "commercial_use": license.commercial,
                "installed": lora.name in installed,
            }
        )

    return entries


def _is_experimental(name, system):
    return system == "darwin" or name.startswith("mac-")


def status():
    catalog = manifest.load()
    records = _load_records()
    detection = detect.detect(disk_path=config.DATA_DIR, extra_paths=[config.COMFY_DIR])
    models_dir = models.resolve_dir(records, config.COMFY_DIR)
    extra = models.extra_search_paths(config.COMFY_DIR)
    gpu = detection.primary_gpu
    vram = gpu.vram_mib if gpu else 0
    profiles = []

    installed = quality.current(catalog, records, models_dir)
    model_set = selection.installed_set(catalog, records, models_dir)

    for name, base in catalog.profiles_for(detection.system).items():
        # With the installed models, or the ones recommended for this GPU if none are.
        try:
            have = (
                manifest.ModelSet(
                    {c: p for c, p in model_set.picks.items() if c in base.capabilities},
                    model_set.defaults,
                )
                if model_set
                else None
            )
            profile = catalog.build_set(
                base,
                have
                if have and all(have.of(c) for c in base.capabilities)
                else catalog.recommended_set(base, vram),
            )
        except ProvisionError:
            profile = base

        states = models.inspect(profile.models, models_dir, extra)
        pending = sum(s.model.bytes for s in states if s.state != models.PRESENT)
        profiles.append(
            {
                "name": name,
                "description": base.description,
                "download_gb": round(profile.bytes / 1e9, 1),
                "pending_gb": round(pending / 1e9, 1),
                "installed": not pending,
                "min_vram_mib": catalog.min_vram_mib(base),
                "suits_this_gpu": vram >= catalog.min_vram_mib(base),
                "experimental": _is_experimental(name, detection.system),
                "has_quality_model": base.quality,
                "capabilities": list(base.capabilities),
                "licenses": [
                    {"name": entry.name, "url": entry.url, "summary": entry.summary}
                    for entry in catalog.licenses_for(profile)
                ],
            }
        )

    catalog_models = {
        cap: [
            _model_entry(info, cap, model_set, models_dir, extra, catalog, vram)
            for info in catalog.describe_catalog(cap, vram)
        ]
        for cap in manifest.CAPABILITIES
    }

    comfy_found = detect.is_comfy_dir(config.COMFY_DIR)
    job = _job_status(catalog, models_dir)
    install_folders = _install_folders(records)

    return {
        "comfyui": {
            "installed": comfy_found,
            "path": str(config.COMFY_DIR),
            "mode": records.mode,
            "other_installs_found": [
                install.path
                for install in detection.comfy_installs
                if Path(install.path) != config.COMFY_DIR.resolve()
                and not records.is_owned(install.path)
            ],
        },
        "gpu": {"name": gpu.name if gpu else None, "vram_mib": vram},
        "disk_free_gb": round(detection.disk_free_bytes / 1e9, 1),
        "install_folder": install_folders,
        "profiles": profiles,
        "models": catalog_models,
        "quality_models": catalog_models["high"],
        "installed_models": _installed_listing(model_set),
        "loras": {
            "only_with": "sdxl",
            "available": _lora_entries(catalog, models_dir, extra, records),
        },
        "installed_quality_model": (
            None
            if installed is None
            else {"name": installed.name, "legacy": installed.legacy}
        ),
        "installation": job,
        "next_step": _next_step(job, profiles, comfy_found),
    }


def _install_folders(records):
    """Dónde se puede instalar: la de siempre, las unidades con espacio y la actual."""
    default = locations.default_install_dir()
    drives = []

    for drive in locations.list_drives():
        if drive.system:
            continue

        drives.append(
            {
                "path": str(locations.propose(drive)),
                "free_gb": round(drive.free / 1e9, 1),
                "filesystem": drive.fstype or None,
                "network": drive.network,
                "removable": drive.removable,
            }
        )

    return {
        "default": str(default),
        "default_free_gb": round(locations.free_bytes(default) / 1e9, 1),
        "current": (
            str(records.install_dir or default) if records.mode == "managed" else None
        ),
        "drives": drives,
    }


def _next_step(job, profiles, comfy_found):
    state = job.get("state")

    if state == RUNNING:
        return (
            "An installation is in progress. Follow it with setup_status and do not "
            "call setup_start again until it finishes."
        )

    if state in (FAILED, INTERRUPTED):
        return (
            "The last installation did not finish: tell the user the error in "
            "installation.error, then call setup_start again with the same profile "
            "and quality model to continue where it left off."
        )

    if not any(p["installed"] for p in profiles) or not comfy_found:
        return (
            "Ask the user which profile to install and, for each capability the profile "
            "has (fast, high = quality, edit), which models: models has, per capability, "
            "each one's precisions with download size, measured seconds per image on this "
            "GPU level, license, commercial use, whether it fits this GPU and which one is "
            "recommended. They can pick several per capability and the first is the "
            "default. State sizes, licenses and warnings (HiDream also needs the Llama "
            "3.1 license). Also ask whether they want ComfyUI and the models in another "
            "folder or disk (install_folder has the usual one and the disks found, with "
            "free space): the models take tens of GB. If they choose sdxl, ask whether "
            "they want style LoRAs and which (loras has size and license of each). Then "
            "call setup_start with fast_models, quality_models and edit_models as "
            "name or name:precision, and install_dir and loras if they chose them. "
            "Some editing models, like FLUX Kontext, are non-commercial."
        )

    return "Installed. Use create_image."


def _installed_listing(model_set):
    return {
        cap: [
            {"model": pick.model, "precision": pick.precision, "default": pick == model_set.default(cap)}
            for pick in model_set.of(cap)
        ]
        for cap in manifest.CAPABILITIES
        if model_set and model_set.of(cap)
    }


def _model_entry(info, capability, model_set, models_dir, extra, catalog, vram=0):
    """One catalog model for an agent to show: size, measured speed, license and fit."""
    license = info["license"]
    have = model_set.pick(capability, info["name"]) if model_set else None
    precisions = []

    for item in info["precisions"]:
        option = catalog.catalog[info["name"]].option(item["precision"])
        states = models.inspect(catalog.expand(option.models), models_dir, extra)
        pending = sum(s.model.bytes for s in states if s.state != models.PRESENT)
        precisions.append(
            {
                "precision": item["precision"],
                "download_gb": round(item["download_bytes"] / 1e9, 1),
                "pending_gb": round(pending / 1e9, 1),
                "seconds_per_image": item["seconds"],
                "gpu_memory_gb": None if item["vram_mib"] is None else round(item["vram_mib"] / 1024, 1),
                "moves_to_ram_gb": round((item["offload_mib"] or 0) / 1024, 1),
                "min_vram_mib": item["min_vram_mib"],
                "fits_this_gpu": item["fits"],
                "recommended": item["recommended"],
            }
        )

    best = next((p for p in precisions if p["recommended"]), precisions[0])
    return {
        "name": info["name"],
        "title": info["title"],
        "download_gb": best["download_gb"],
        "pending_gb": best["pending_gb"],
        "min_vram_mib": min(p["min_vram_mib"] for p in precisions),
        "license": {"name": license.name, "url": license.url, "summary": license.summary},
        "commercial_use": info["commercial_use"],
        "recommended": info["recommended"],
        "fits_this_gpu": any(p["fits_this_gpu"] for p in precisions),
        "warning": None
        if any(p["fits_this_gpu"] for p in precisions)
        else f"{info['title']} needs at least {min(p['min_vram_mib'] for p in precisions)} MiB "
        f"of GPU memory and this machine has {vram} MiB. It can be installed, but generation "
        "may be slow or fail.",
        "installed": have is not None,
        "installed_precision": have.precision if have else None,
        "default": bool(have and model_set.default(capability) == have),
        "precisions": precisions,
    }


def _load_records():
    try:
        return InstallManifest.load(config.INSTALL_MANIFEST)
    except ProvisionError:
        return InstallManifest(config.INSTALL_MANIFEST)


def _lora_names(loras, catalog):
    """The names asked for (["all"] means every one), or ValueError. None means no change."""
    if not loras:
        return None

    if not isinstance(loras, (list, tuple)) or not all(isinstance(name, str) for name in loras):
        raise ValueError('loras must be a list of names from setup_status, or ["all"].')

    if "all" in loras:
        if len(loras) > 1:
            raise ValueError('Use ["all"] alone, or a list of names.')

        return list(catalog.loras)

    unknown = [name for name in loras if name not in catalog.loras]

    if unknown:
        raise ValueError(
            f"Unknown LoRA(s): {', '.join(unknown)}. Choose from: {', '.join(catalog.loras)}."
        )

    return list(dict.fromkeys(loras))


def _validate_loras(loras, catalog, target):
    names = _lora_names(loras, catalog)

    if names is None:
        return None

    if target is None or target.pick("high", "sdxl") is None:
        raise ValueError(
            "LoRAs only work with the sdxl quality model, and this installation would not "
            "have it. Nothing was started: ask the user to choose sdxl in quality_models, "
            "or leave loras empty."
        )

    return names


def _model_lists(fast_models, quality_models, edit_models, quality_model):
    """The lists as {capability: [name[:precision]]}; only the ones asked for."""
    lists = {"fast": fast_models, "high": quality_models, "edit": edit_models}

    if quality_model and not quality_models:
        lists["high"] = [quality_model]

    found = {}

    for capability, texts in lists.items():
        if texts is None:
            continue

        if isinstance(texts, str) or not all(isinstance(text, str) for text in texts):
            name = {"fast": "fast_models", "high": "quality_models", "edit": "edit_models"}[capability]
            raise ValueError(
                f"{name} must be a list of model names from setup_status, as name or "
                "name:precision."
            )

        if texts:
            found[capability] = [text.strip() for text in texts if text.strip()]

    return found


def _target(catalog, base, lists, records, vram):
    """(old set, target set, resolved profile) after this request, or ValueError."""
    from types import SimpleNamespace

    from imagehearth_mcp.provisioner import setup as setup_command

    models_dir = models.resolve_dir(records, config.COMFY_DIR)
    old = selection.installed_set(catalog, records, models_dir)
    args = SimpleNamespace(
        fast_models=lists.get("fast"),
        quality_models=lists.get("high"),
        edit_models=lists.get("edit"),
        quality_model=None,
        variant=None,
    )

    try:
        request = setup_command.requested_models(args, catalog, base, vram, old)
        effective = catalog.profiles[setup_command._higher_profile(records.profile, base.name)]
        target = selection.target_set(catalog, effective, old, request, vram)
        profile = catalog.build_set(selection.profile_for(catalog, effective, target), target)
    except ProvisionError as error:
        raise ValueError(f"Nothing was started: {error}") from error

    return old, request, target, profile


def _validate(profile, accept_licenses, existing_comfyui, install_dir=""):
    if accept_licenses is not True:
        raise ValueError(
            "Nothing was started: the user has not accepted the licenses. Show them "
            "the licenses from setup_status and ask."
        )

    system = sys.platform.replace("win32", "windows")
    available = manifest.load().profiles_for(system)

    if profile not in available:
        raise ValueError(
            f"Unknown profile {profile!r} on this system. "
            f"Choose one of: {', '.join(available)}."
        )

    if _is_experimental(profile, system):
        raise ValueError(
            f"The {profile} profile is experimental and can't be installed from an "
            "agent. The user can run `imagehearth-mcp setup --experimental` themselves."
        )

    if existing_comfyui and not detect.is_comfy_dir(Path(existing_comfyui).expanduser()):
        raise ValueError(f"{existing_comfyui} does not look like a ComfyUI folder.")

    if install_dir:
        _validate_install_dir(install_dir, existing_comfyui)


def _validate_install_dir(install_dir, existing_comfyui):
    if existing_comfyui:
        raise ValueError(
            "install_dir and existing_comfyui can't be combined: the first says where "
            "ImageHearth installs its own ComfyUI, the second reuses one already installed."
        )

    if not os.path.isabs(Path(install_dir).expanduser()):
        raise ValueError(f"install_dir must be an absolute path, not {install_dir!r}.")

    records = _load_records()
    folder = locations.resolve(install_dir)

    if records.mode == "attached":
        raise ValueError(
            "This installation uses an existing ComfyUI, so install_dir doesn't apply."
        )

    if records.mode and os.path.abspath(records.comfy_dir) != str(folder / "comfyui"):
        raise ValueError(
            f"ImageHearth is already installed in {records.comfy_dir}. install_dir can't "
            "move it: tell the user to run `imagehearth-mcp update --move-to "
            f"{folder}` themselves, or leave install_dir empty."
        )


def _folder_issues(install_dir, catalog, profile, detection):
    """(errores, avisos) de instalar en `install_dir` lo que pide `setup_start`."""
    folder = locations.resolve(install_dir)
    comfy_dir = folder / "comfyui"
    sizes = [
        item.model.bytes
        for item in models.inspect(profile.models, comfy_dir / "models")
        if item.state != models.PRESENT
    ]
    install_bytes = 0

    if not (comfy_dir / "venv").exists():
        install_bytes = catalog.install_bytes(catalog.pytorch.get(detection.platform.index))

    return locations.split(locations.check(folder, sizes, install_bytes))


def _spawn(
    profile, existing_comfyui, quality_models="", install_dir="", loras="", fast_models="",
    edit_models="",
):
    command = [
        sys.executable,
        "-m",
        "imagehearth_mcp.provisioner.agent_setup",
        profile,
        str(Path(existing_comfyui).expanduser().resolve()) if existing_comfyui else "",
        quality_models,
        install_dir,
        loras,
        fast_models,
        edit_models,
    ]

    config.SETUP_JOB_LOG.parent.mkdir(parents=True, exist_ok=True)

    with open(config.SETUP_JOB_LOG, "w", encoding="utf-8") as log:
        return subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            **spawn.detached_options(),
        )


def start(
    profile,
    accept_licenses,
    existing_comfyui="",
    quality_model="",
    install_dir="",
    loras=None,
    fast_models=None,
    quality_models=None,
    edit_models=None,
):
    _validate(profile, accept_licenses, existing_comfyui, install_dir)
    catalog = manifest.load()
    detection = detect.detect(disk_path=config.DATA_DIR, extra_paths=[config.COMFY_DIR])
    gpu = detection.primary_gpu
    vram = gpu.vram_mib if gpu else 0
    base = catalog.profiles[profile]
    records = _load_records()
    lists = _model_lists(fast_models, quality_models, edit_models, quality_model)

    for capability in lists:
        if capability not in base.capabilities:
            raise ValueError(
                f"The {profile} profile has no {capability} models: leave that list empty "
                "or choose a profile that has them."
            )

    old, request, target, resolved = _target(catalog, base, lists, records, vram)
    lora_names = _validate_loras(loras, catalog, target)
    warnings = []
    replaces = []

    for capability, pick in target.all():
        option = catalog.option_of(capability, pick)

        if vram and vram < option.min_vram_mib:
            warnings.append(
                f"{catalog.catalog[pick.model].title} {pick.precision} needs at least "
                f"{option.min_vram_mib} MiB of GPU memory to run without moving weights "
                f"to RAM and this machine has {vram} MiB. It can be installed, but "
                "generation will be slower or may fail."
            )

    if old is not None:
        change = selection.plan_set_change(
            catalog, records, models.resolve_dir(records, config.COMFY_DIR), old, target, resolved,
            legacy=selection.is_legacy(catalog, records, models.resolve_dir(records, config.COMFY_DIR))
            and request.asks("high"),
        )
        replaces = [
            f"{catalog.catalog[pick.model].title} {pick.precision} is removed"
            for _, pick in change.removed
        ] + [
            f"{catalog.catalog[name].title} changes from {before} to {after}"
            for _, name, before, after in change.switched
        ]

    folder_warnings = []

    if install_dir:
        errors, folder_warnings = _folder_issues(install_dir, catalog, resolved, detection)

        if errors:
            raise ValueError(
                "Nothing was started: " + " ".join(errors) + " Tell the user and ask "
                "for another folder, or leave install_dir empty for the usual one."
            )

        install_dir = str(locations.resolve(install_dir))

    try:
        lock = locks.acquire(config.SETUP_JOB_LOCK, 1)
    except TimeoutError:
        raise RuntimeError("Another setup_start is being launched.") from None

    default_high = target.default("high")

    try:
        if locks.is_locked(config.SETUP_LOCK) or _job_alive(_read_job()):
            raise RuntimeError(
                "An installation is already running. Follow it with setup_status."
            )

        arguments = [
            profile,
            existing_comfyui,
            ",".join(lists.get("high", ())),
            install_dir,
            ",".join(lora_names or ()),
            ",".join(lists.get("fast", ())),
            ",".join(lists.get("edit", ())),
        ]

        # Trailing empty values are left out: the process reads them back as empty.
        while len(arguments) > 3 and not arguments[-1]:
            arguments.pop()

        process = _spawn(*arguments)
        _write_job(
            state=RUNNING,
            profile=profile,
            quality_model=default_high.model if default_high else "",
            models={cap: [str(pick) for pick in target.of(cap)] for cap in manifest.CAPABILITIES if target.of(cap)},
            defaults={cap: target.default(cap).model for cap in manifest.CAPABILITIES if target.of(cap)},
            vram_mib=vram,
            error=None,
            pid=process.pid,
            create_time=processes.create_time(process.pid),
            started_at=time.time(),
        )
    finally:
        lock.release()

    result = {
        "state": RUNNING,
        "profile": profile,
        "quality_model": default_high.model if default_high else None,
        "models": {
            cap: [str(pick) for pick in target.of(cap)]
            for cap in manifest.CAPABILITIES
            if target.of(cap)
        },
        "defaults": {
            cap: target.default(cap).model for cap in manifest.CAPABILITIES if target.of(cap)
        },
        "pid": process.pid,
        "next_step": "Follow it with setup_status. It continues if you disconnect.",
    }

    if warnings:
        result["warning"] = " ".join(warnings)

    if install_dir:
        result["install_dir"] = install_dir

    if lora_names:
        result["loras"] = lora_names

    if folder_warnings:
        result["folder_warnings"] = folder_warnings

    if replaces:
        result["replaces"] = (
            "; ".join(replaces) + ". The new models are downloaded and verified first, "
            "then the old ones are deleted."
        )

    return result


def _args(
    profile, existing_comfyui, quality_models="", install_dir="", loras="", fast_models="",
    edit_models="",
):
    from imagehearth_mcp.cli import _build_parser

    argv = ["setup", "--profile", profile, "--accept-licenses", "--non-interactive"]
    given = False

    for flag, value in (
        ("--fast-models", fast_models),
        ("--quality-models", quality_models),
        ("--edit-models", edit_models),
    ):
        if value:
            argv += [flag, value]
            given = True

    if given:
        # The user chose them (and, if they replace others, confirmed that) through the agent.
        argv.append("--yes")

    if install_dir:
        argv += ["--install-dir", install_dir]

    if loras:
        argv += ["--loras", loras]

    if existing_comfyui:
        argv += ["--attach", existing_comfyui, "--install-node"]
    elif not _load_records().mode:
        argv.append("--managed")

    return _build_parser().parse_args(argv)


def main(argv):
    from imagehearth_mcp.engine.errors import ConfigError
    from imagehearth_mcp.provisioner.setup import run

    profile, existing, quality_models, install_dir, loras, fast_models, edit_models = (
        [*argv, "", "", "", "", "", ""]
    )[:7]

    try:
        code = run(
            _args(profile, existing, quality_models, install_dir, loras, fast_models, edit_models)
        )
    except (ProvisionError, ConfigError) as error:
        print(f"Error: {error}", flush=True)
        _write_job(state=FAILED, error=str(error))
        return 1
    except Exception as error:  # noqa: BLE001 - debe quedar constancia de cualquier fallo.
        print(f"Error: {error}", flush=True)
        _write_job(state=FAILED, error=str(error))
        return 1

    _write_job(state=FINISHED if code == 0 else FAILED, error=None)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
