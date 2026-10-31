import contextvars
import json
import logging
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from imagehearth_mcp.engine import config

run_id = contextvars.ContextVar("imagehearth_run_id", default="")


class JsonFormatter(logging.Formatter):
    def format(self, record):
        entry = {
            "time": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "pid": os.getpid(),
            "run_id": run_id.get(),
            "module": record.module,
            "message": record.getMessage(),
        }

        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(entry, ensure_ascii=False)


class LazyFileHandler(logging.FileHandler):
    """Crea la carpeta y el archivo al escribir, no al importar."""

    def __init__(self, path):
        super().__init__(path, encoding="utf-8", delay=True)

    def emit(self, record):
        Path(self.baseFilename).parent.mkdir(parents=True, exist_ok=True)
        super().emit(record)


def cleanup_old_logs(directory, max_age_days):
    """Borra los logs de procesos antiguos; nunca falla."""
    cutoff = time.time() - max_age_days * 86400

    for path in directory.glob("imagehearth-*.log"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            pass


def get_logger(name):
    root = logging.getLogger("imagehearth")

    if not root.handlers:
        root.setLevel(logging.INFO)
        root.propagate = False

        # stdout pertenece al protocolo MCP: nunca se escribe ahí.
        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(logging.Formatter("%(message)s"))
        root.addHandler(console)

        # Un archivo por proceso: sin rotación ni bloqueos compartidos.
        cleanup_old_logs(config.ENGINE_LOG_DIR, config.LOG_RETENTION_DAYS)
        file_handler = LazyFileHandler(
            config.ENGINE_LOG_DIR / f"imagehearth-{os.getpid()}.log"
        )
        file_handler.setFormatter(JsonFormatter())
        root.addHandler(file_handler)

    return root.getChild(name)
