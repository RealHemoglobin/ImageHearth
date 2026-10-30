import contextvars
import fcntl
import json
import logging
import os
import sys
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler

from engine import config

run_id = contextvars.ContextVar("imageengine_run_id", default="")


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


class SharedRotatingFileHandler(RotatingFileHandler):
    """Rotación segura entre los procesos MCP de cada agente."""

    def emit(self, record):
        with open(f"{self.baseFilename}.lock", "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            self._reopen_if_rotated()
            super().emit(record)

    def _reopen_if_rotated(self):
        if self.stream is None:
            return

        try:
            current = os.stat(self.baseFilename).st_ino
        except FileNotFoundError:
            current = None

        if current != os.fstat(self.stream.fileno()).st_ino:
            self.stream.close()
            self.stream = None


def get_logger(name):
    root = logging.getLogger("imageengine")

    if not root.handlers:
        root.setLevel(logging.INFO)
        root.propagate = False

        # stdout pertenece al protocolo MCP: nunca se escribe ahí.
        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(logging.Formatter("%(message)s"))
        root.addHandler(console)

        config.LOG_DIR.mkdir(parents=True, exist_ok=True)
        file_handler = SharedRotatingFileHandler(
            config.ENGINE_LOG_FILE,
            maxBytes=config.ENGINE_LOG_MAX_BYTES,
            backupCount=config.ENGINE_LOG_BACKUPS,
            encoding="utf-8",
        )
        file_handler.setFormatter(JsonFormatter())
        root.addHandler(file_handler)

    return root.getChild(name)
