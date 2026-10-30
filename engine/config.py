import os
from pathlib import Path


def _int_env(name, default):
    return int(os.environ.get(name, default))


ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS_DIR = ROOT / "workflows"
OUTPUT_DIR = ROOT / "output"
LOG_DIR = ROOT / "logs"
LOCK_FILE = ROOT / "engine.lock"
STATE_FILE = ROOT / "state" / "session.json"
COMFY_LOG_FILE = LOG_DIR / "comfyui.log"
ENGINE_LOG_FILE = LOG_DIR / "imageengine.log"

COMFY_DIR = Path.home() / "AI" / "ComfyUI"
COMFY_HOST = "127.0.0.1"
COMFY_PORT = 8188
COMFY_API = f"http://{COMFY_HOST}:{COMFY_PORT}"
OLLAMA_API = "http://127.0.0.1:11434"

# Subcarpeta de ComfyUI reservada para ImageEngine.
COMFY_SUBFOLDER = "imageengine"

# Plazos globales, en segundos.
LOCK_TIMEOUT = _int_env("IMAGEENGINE_LOCK_TIMEOUT", 1800)
UNLOAD_TIMEOUT = _int_env("IMAGEENGINE_UNLOAD_TIMEOUT", 180)
RESTORE_TIMEOUT = _int_env("IMAGEENGINE_RESTORE_TIMEOUT", 900)
FREE_TIMEOUT = _int_env("IMAGEENGINE_FREE_TIMEOUT", 120)
COMFY_START_TIMEOUT = _int_env("IMAGEENGINE_COMFY_START_TIMEOUT", 180)
CANCEL_TIMEOUT = 30
WORKFLOW_TIMEOUT = 1200
KONTEXT_TIMEOUT = 1800
POLL_INTERVAL = 2.0
OLLAMA_CHECK_INTERVAL = 15.0

FREE_ATTEMPTS = 2

MIN_DIMENSION = 64
MAX_DIMENSION = 4096
MAX_PIXELS = _int_env("IMAGEENGINE_MAX_PIXELS", 8_388_608)
MAX_REFERENCES = 6

# Plantillas que no se pueden usar como workflow de generación.
INTERNAL_WORKFLOWS = {"flux_kontext_dev_basic"}

COMFY_LOG_MAX_BYTES = 10 * 1024 * 1024
ENGINE_LOG_MAX_BYTES = 5 * 1024 * 1024
ENGINE_LOG_BACKUPS = 3
