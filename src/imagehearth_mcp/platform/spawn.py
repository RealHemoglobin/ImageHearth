import subprocess
import sys


def detached_options():
    """Opciones de Popen para que el proceso sobreviva al servidor MCP."""
    if sys.platform == "win32":
        return {
            "creationflags": (
                subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
            ),
        }

    return {"start_new_session": True, "close_fds": True}
