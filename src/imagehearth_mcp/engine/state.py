import json
import os
import time

from imagehearth_mcp.engine import config

UNLOADING = "unloading"
GENERATING = "generating"
RELEASING = "releasing"
RESTORING = "restoring"
RECOVERY_REQUIRED = "recovery_required"


def read():
    try:
        return json.loads(config.STATE_FILE.read_text())
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as error:
        # Un estado ilegible no debe parecer una sesión limpia.
        return {
            "phase": RECOVERY_REQUIRED,
            "run_id": "",
            "models": [],
            "prompt_id": None,
            "reason": f"Estado de sesión ilegible: {error}",
        }


def write(**fields):
    data = {**(read() or {}), **fields, "updated_at": time.time()}

    config.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = config.STATE_FILE.with_suffix(f".{os.getpid()}.tmp")

    with temporary.open("w") as file:
        json.dump(data, file)
        file.flush()
        os.fsync(file.fileno())

    os.replace(temporary, config.STATE_FILE)
    return data


def clear():
    config.STATE_FILE.unlink(missing_ok=True)
