import requests

from engine import comfyui_manager, config, ollama_manager, orchestrator, state


def _comfyui_status():
    try:
        response = requests.get(f"{config.COMFY_API}/system_stats", timeout=3)
        response.raise_for_status()

        return {
            "status": "running",
            "gpu_devices": response.json().get("devices", []),
        }

    except requests.RequestException as error:
        return {
            "status": "stopped",
            "error": str(error),
            "gpu_devices": [],
        }


def _ollama_status():
    try:
        response = requests.get(f"{config.OLLAMA_API}/api/version", timeout=3)
        response.raise_for_status()

        return {
            "status": "running",
            "version": response.json().get("version"),
            "loaded_models": ollama_manager.get_loaded_models(),
        }

    except requests.RequestException as error:
        return {
            "status": "stopped",
            "error": str(error),
            "loaded_models": [],
        }


def _status_route_issue():
    try:
        requests.get(
            f"{config.COMFY_API}/imageengine/status",
            timeout=3,
        ).raise_for_status()
    except requests.RequestException as error:
        return f"Falta el nodo imageengine_status en ComfyUI: {error}"

    return None


def get_status():
    comfy = _comfyui_status()
    ollama = _ollama_status()
    busy = orchestrator.is_busy()
    pending = state.read()
    issues = []

    if ollama["status"] != "running":
        issues.append("Ollama no responde.")

    if comfy["status"] == "running":
        route_issue = _status_route_issue()

        if route_issue:
            issues.append(route_issue)

    elif comfyui_manager.port_is_open() or comfyui_manager.find_processes():
        issues.append("ComfyUI tiene un proceso activo, pero no responde.")

    if busy:
        overall = "busy"
    elif pending:
        overall = "recovery_required"
    elif issues:
        overall = "degraded"
    else:
        overall = "ready"

    engine = {
        "status": overall,
        "gpu_free_mib": comfyui_manager.gpu_free_mib(),
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
    }
