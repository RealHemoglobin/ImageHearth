import os
import tomllib
from importlib import resources
from pathlib import Path

from platformdirs import user_config_path, user_data_path, user_log_path

APP_NAME = "imagehearth"


class ConfigError(RuntimeError):
    """Invalid configuration: the message names the file or variable."""


def _int_env(name, default):
    value = os.environ.get(name)

    if value is None:
        return default

    try:
        return int(value)
    except ValueError:
        raise ConfigError(f"{name} must be an integer, not {value!r}.") from None


def _load_file(path):
    try:
        with path.open("rb") as file:
            return tomllib.load(file)
    except FileNotFoundError:
        return {}
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ConfigError(f"Invalid configuration in {path}: {error}") from error


def _lookup(values, key, env):
    """Environment variable first, then config.toml. Returns (value, source)."""
    value = os.environ.get(env)

    if value is not None:
        return value, env

    value = values.get(key)

    if value is not None:
        return value, f"{key} in {CONFIG_FILE}"

    return None, None


def _path_setting(values, key, env, default):
    value, source = _lookup(values, key, env)

    if value is None:
        return default

    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{source} must be a path.")

    return Path(value).expanduser()


def _port_setting(values, key, env, default):
    value, source = _lookup(values, key, env)

    if value is None:
        return default

    try:
        if isinstance(value, bool):
            raise TypeError
        port = int(value)
    except (TypeError, ValueError):
        port = 0

    if not 0 < port < 65536:
        raise ConfigError(f"{source} must be a port between 1 and 65535.")

    return port


def _choice_setting(values, key, env, choices, default):
    value, source = _lookup(values, key, env)

    if value is None:
        return default

    if value not in choices:
        raise ConfigError(f"{source} must be one of {', '.join(choices)}.")

    return value


def _url_setting(values, key, env, default):
    value, source = _lookup(values, key, env)

    if value is None:
        return default

    if not isinstance(value, str) or not value.startswith(("http://", "https://")):
        raise ConfigError(f"{source} must be an http(s) URL.")

    return value.rstrip("/")


# Se calcula al importar, pero nunca se crea nada en disco:
# las carpetas se crean al escribir en ellas.
CONFIG_DIR = user_config_path(APP_NAME)
DATA_DIR = user_data_path(APP_NAME)
LOG_DIR = user_log_path(APP_NAME)
CONFIG_FILE = Path(
    os.environ.get("IMAGEHEARTH_CONFIG_FILE") or CONFIG_DIR / "config.toml"
)

_values = _load_file(CONFIG_FILE)

COMFY_DIR = _path_setting(
    _values, "comfy_dir", "IMAGEHEARTH_COMFY_DIR", DATA_DIR / "comfyui"
)
OUTPUT_DIR = _path_setting(
    _values,
    "output_dir",
    "IMAGEHEARTH_OUTPUT_DIR",
    Path.home() / "Pictures" / "ImageHearth",
)
COMFY_HOST = "127.0.0.1"
COMFY_PORT = _port_setting(_values, "comfy_port", "IMAGEHEARTH_COMFY_PORT", 8188)
COMFY_API = f"http://{COMFY_HOST}:{COMFY_PORT}"
OLLAMA_API = _url_setting(
    _values, "ollama_url", "IMAGEHEARTH_OLLAMA_URL", "http://127.0.0.1:11434"
)

OLLAMA_MODE = _choice_setting(
    _values, "ollama_mode", "IMAGEHEARTH_OLLAMA_MODE", ("auto", "off"), "auto"
)

LOCK_FILE = DATA_DIR / "engine.lock"
STATE_FILE = DATA_DIR / "state" / "session.json"
PID_FILE = DATA_DIR / "state" / "comfyui.pid"
COMFY_LOG_FILE = LOG_DIR / "comfyui.log"
ENGINE_LOG_DIR = LOG_DIR

# Subcarpeta de ComfyUI reservada para ImageHearth.
COMFY_SUBFOLDER = "imagehearth"


def data_files():
    """Carpeta `data/` del paquete (workflows, skill y nodo de ComfyUI)."""
    return resources.files("imagehearth_mcp") / "data"


def data_path(*parts):
    """Ruta real de un dato de paquete, para quien necesite un archivo."""
    return Path(str(data_files().joinpath(*parts)))


WORKFLOWS_DIR = data_path("workflows")

# Plazos globales, en segundos.
LOCK_TIMEOUT = _int_env("IMAGEHEARTH_LOCK_TIMEOUT", 1800)
UNLOAD_TIMEOUT = _int_env("IMAGEHEARTH_UNLOAD_TIMEOUT", 180)
RESTORE_TIMEOUT = _int_env("IMAGEHEARTH_RESTORE_TIMEOUT", 900)
FREE_TIMEOUT = _int_env("IMAGEHEARTH_FREE_TIMEOUT", 120)
COMFY_START_TIMEOUT = _int_env("IMAGEHEARTH_COMFY_START_TIMEOUT", 180)
CANCEL_TIMEOUT = 30
WORKFLOW_TIMEOUT = 1200
KONTEXT_TIMEOUT = 1800
POLL_INTERVAL = 2.0
OLLAMA_CHECK_INTERVAL = 15.0

FREE_ATTEMPTS = 2

MIN_DIMENSION = 64
MAX_DIMENSION = 4096
MAX_PIXELS = _int_env("IMAGEHEARTH_MAX_PIXELS", 8_388_608)
MAX_REFERENCES = 6

# Plantillas que no se pueden usar como workflow de generación.
INTERNAL_WORKFLOWS = {"flux_kontext_dev_basic"}

COMFY_LOG_MAX_BYTES = 10 * 1024 * 1024
LOG_RETENTION_DAYS = 14

# Nodo de ComfyUI que informa de los modelos cargados.
STATUS_NODE = "imagehearth_status"
STATUS_ROUTE = "/imagehearth/status"
STATUS_NODE_VERSION = 1
