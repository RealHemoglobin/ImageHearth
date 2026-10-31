"""Instalación pedida desde un agente: `setup_status`, `setup_start` y su proceso.

`setup_start` lanza este módulo desacoplado, de modo que la instalación sobrevive
a la desconexión. El progreso queda en un archivo de estado.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

from imagehearth_mcp.engine import config
from imagehearth_mcp.platform import files, locks, processes, spawn
from imagehearth_mcp.provisioner import ProvisionError, detect, manifest, models
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
        "error": job.get("error"),
        "model_bytes": _downloaded_bytes(job, catalog, models_dir),
        "log": str(config.SETUP_JOB_LOG),
        "log_tail": _log_tail(),
    }


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

    for name, profile in catalog.profiles_for(detection.system).items():
        states = models.inspect(profile.models, models_dir, extra)
        pending = sum(s.model.bytes for s in states if s.state != models.PRESENT)
        profiles.append(
            {
                "name": name,
                "description": profile.description,
                "download_gb": round(profile.bytes / 1e9, 1),
                "pending_gb": round(pending / 1e9, 1),
                "installed": not pending,
                "min_vram_mib": profile.min_vram_mib,
                "suits_this_gpu": vram >= profile.min_vram_mib,
                "experimental": _is_experimental(name, detection.system),
                "licenses": [
                    {"name": entry.name, "url": entry.url, "summary": entry.summary}
                    for entry in catalog.licenses_for(profile)
                ],
            }
        )

    comfy_found = detect.is_comfy_dir(config.COMFY_DIR)

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
        "profiles": profiles,
        "installation": _job_status(catalog, models_dir),
        "next_step": (
            "Ask the user which profile to install, stating its size and licenses, "
            "then call setup_start."
            if not any(p["installed"] for p in profiles) or not comfy_found
            else "Installed. Use create_image."
        ),
    }


def _load_records():
    try:
        return InstallManifest.load(config.INSTALL_MANIFEST)
    except ProvisionError:
        return InstallManifest(config.INSTALL_MANIFEST)


def _validate(profile, accept_licenses, existing_comfyui):
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


def _spawn(profile, existing_comfyui):
    command = [sys.executable, "-m", "imagehearth_mcp.provisioner.agent_setup", profile]

    if existing_comfyui:
        command.append(str(Path(existing_comfyui).expanduser().resolve()))

    config.SETUP_JOB_LOG.parent.mkdir(parents=True, exist_ok=True)

    with open(config.SETUP_JOB_LOG, "w", encoding="utf-8") as log:
        return subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            **spawn.detached_options(),
        )


def start(profile, accept_licenses, existing_comfyui=""):
    _validate(profile, accept_licenses, existing_comfyui)

    try:
        lock = locks.acquire(config.SETUP_JOB_LOCK, 1)
    except TimeoutError:
        raise RuntimeError("Another setup_start is being launched.") from None

    try:
        if locks.is_locked(config.SETUP_LOCK) or _job_alive(_read_job()):
            raise RuntimeError(
                "An installation is already running. Follow it with setup_status."
            )

        process = _spawn(profile, existing_comfyui)
        _write_job(
            state=RUNNING,
            profile=profile,
            error=None,
            pid=process.pid,
            create_time=processes.create_time(process.pid),
            started_at=time.time(),
        )
    finally:
        lock.release()

    return {
        "state": RUNNING,
        "profile": profile,
        "pid": process.pid,
        "next_step": "Follow it with setup_status. It continues if you disconnect.",
    }


def _args(profile, existing_comfyui):
    from imagehearth_mcp.cli import _build_parser

    argv = ["setup", "--profile", profile, "--accept-licenses", "--non-interactive"]

    if existing_comfyui:
        argv += ["--attach", existing_comfyui, "--install-node"]
    elif not _load_records().mode:
        argv.append("--managed")

    return _build_parser().parse_args(argv)


def main(argv):
    from imagehearth_mcp.engine.errors import ConfigError
    from imagehearth_mcp.provisioner.setup import run

    profile, *rest = argv

    try:
        code = run(_args(profile, rest[0] if rest else ""))
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
