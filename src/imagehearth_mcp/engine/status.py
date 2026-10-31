import requests

from imagehearth_mcp.engine import (
    catalog,
    comfyui_client,
    comfyui_manager,
    config,
    gpu,
    memory,
    ollama_manager,
    orchestrator,
    state,
)


def _comfyui_status():
    try:
        response = requests.get(f"{config.COMFY_API}/system_stats", timeout=3)
        response.raise_for_status()

        return {
            "status": "running",
            "managed": comfyui_manager.managed_pid() is not None,
            "gpu_devices": response.json().get("devices", []),
        }

    except requests.RequestException as error:
        return {
            "status": "stopped",
            "error": str(error),
            "gpu_devices": [],
        }


def _ollama_status():
    if config.memory_mode() != "auto":
        return {"status": "disabled", "loaded_models": []}

    try:
        response = requests.get(f"{config.OLLAMA_API}/api/version", timeout=3)
        response.raise_for_status()

        return {
            "status": "running",
            "version": response.json().get("version"),
            "loaded_models": ollama_manager.get_loaded_models(),
        }

    except (requests.RequestException, memory.ProviderUnavailable) as error:
        return {
            "status": "stopped",
            "error": str(error),
            "loaded_models": [],
        }


def _status_node_issue():
    try:
        comfyui_client.status_node()
    except comfyui_client.StatusNodeMissing as error:
        return str(error)
    except requests.RequestException as error:
        return f"Could not query the {config.STATUS_NODE} node: {error}"

    return None


def get_status():
    comfy = _comfyui_status()
    ollama = _ollama_status()
    busy = orchestrator.is_busy()
    pending = state.read()
    issues = []

    # Ollama es opcional: que no responda no es un problema.
    if comfy["status"] == "running":
        route_issue = _status_node_issue()

        if route_issue:
            issues.append(route_issue)

    elif comfyui_manager.port_is_open() or comfyui_manager.find_processes():
        issues.append("ComfyUI has an active process, but it does not respond.")

    # ComfyUI en marcha basta: puede ser una instancia ajena.
    missing = None if comfy["status"] == "running" else catalog.missing_installation()

    if busy:
        overall = "busy"
    elif pending:
        overall = "recovery_required"
    elif missing:
        overall = "not_installed"
        issues.append(missing)
    elif issues:
        overall = "degraded"
    else:
        overall = "ready"

    engine = {
        "status": overall,
        "gpu_free_mib": gpu.free_mib(),
        "issues": issues,
    }

    if pending:
        engine["session"] = {
            "phase": pending.get("phase"),
            "reason": pending.get("reason"),
            "models": [model["name"] for model in pending.get("models", [])],
        }

    return {
        "imageengine": engine,
        "comfyui": comfy,
        "ollama": ollama,
        "memory": memory.describe(),
    }
