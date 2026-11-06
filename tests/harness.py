"""ComfyUI y Ollama simulados sobre HTTP real, sin tocar la GPU."""

import io
import json
import logging
import os
import shutil
import tempfile
import threading
import unittest
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlparse

from PIL import Image

from imagehearth_mcp.engine import config
from imagehearth_mcp.provisioner import models

# Antes de importar módulos con logger: las pruebas no escriben en logs/.
_LOGS = Path(tempfile.mkdtemp(prefix="imagehearth-test-logs-"))
config.LOG_DIR = _LOGS
config.ENGINE_LOG_DIR = _LOGS

from imagehearth_mcp.engine.log import get_logger

get_logger("tests")

for _handler in list(logging.getLogger("imagehearth").handlers):
    if type(_handler) is logging.StreamHandler:
        logging.getLogger("imagehearth").removeHandler(_handler)


def home_env(home):
    """Entorno de un subproceso cuyas carpetas de usuario caen dentro de `home`."""
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("IMAGEHEARTH_", "XDG_"))
    }
    env["HOME"] = str(home)
    # En Windows, HOME no cuenta: Path.home() usa USERPROFILE y platformdirs
    # pregunta al sistema salvo que se fuerce con estas variables.
    env["USERPROFILE"] = str(home)
    env["WIN_PD_OVERRIDE_LOCAL_APPDATA"] = str(home / "AppData" / "Local")
    env["WIN_PD_OVERRIDE_APPDATA"] = str(home / "AppData" / "Roaming")
    return env


def png_bytes():
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(buffer, "PNG")
    return buffer.getvalue()


class FakeServer:
    def __init__(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _reply(self, status, body):
                data = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                url = urlparse(self.path)
                self._reply(*fake.get(url.path, parse_qs(url.query)))

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                fake.events.append(f"POST {self.path}")
                self._reply(*fake.post(self.path, self.headers, body))

        self.events = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.closed = False

    def stop(self):
        if not self.closed:
            self.closed = True
            self.server.shutdown()
            self.server.server_close()


class FakeOllama(FakeServer):
    def __init__(self):
        self.loaded = {}
        self.requests = []
        self.fail_restore = False
        super().__init__()

    def add(self, name, **fields):
        self.loaded[name] = {"name": name, "size_vram": 1024 * 1024, **fields}

    def get(self, path, query):
        if path == "/api/ps":
            return 200, {"models": list(self.loaded.values())}
        if path == "/api/version":
            return 200, {"version": "test"}
        return 404, {}

    def post(self, path, headers, body):
        data = json.loads(body)
        self.requests.append(data)

        if data.get("keep_alive") == 0:
            self.loaded.pop(data["model"], None)
            self.events.append(f"unload {data['model']}")
            return 200, {}

        if self.fail_restore:
            return 500, {"error": "failure"}

        self.events.append(f"load {data['model']}")
        self.loaded[data["model"]] = {
            "name": data["model"],
            "size_vram": 1024 * 1024,
        }
        return 200, {}


class FakeComfy(FakeServer):
    def __init__(self, comfy_dir):
        self.comfy_dir = comfy_dir
        self.models_loaded = 0
        self.free_ok = True
        self.running = []
        self.pending = []
        self.history = {}
        self.outputs = {}
        self.workflows = []
        self.behavior = "ok"
        self.reject = None
        self.on_prompt = None
        self.status_route = True
        self.vram_free = None
        self.node_version = config.STATUS_NODE_VERSION
        super().__init__()

    def get(self, path, query):
        if path == "/system_stats":
            if self.vram_free is None:
                return 200, {"devices": []}
            return 200, {
                "devices": [{"type": "cuda", "vram_free": self.vram_free * 1024 * 1024}]
            }
        if path == "/imagehearth/status":
            if not self.status_route:
                return 404, {}
            return 200, {
                "version": self.node_version,
                "models_loaded": self.models_loaded,
                "loaded_models": [{"class": "x"}] * self.models_loaded,
            }
        if path == "/queue":
            return 200, {
                "queue_running": [[0, item] for item in self.running],
                "queue_pending": [[0, item] for item in self.pending],
            }
        if path.startswith("/history/"):
            return 200, self.get_history(path.rsplit("/", 1)[1])
        if path == "/view":
            if self.behavior == "corrupt":
                return 200, b"no es una imagen"
            return 200, png_bytes()
        return 404, {}

    def get_history(self, prompt_id):
        if self.behavior == "never":
            return {}

        if prompt_id not in self.outputs:
            return {}

        if prompt_id in self.running:
            self.running.remove(prompt_id)

        if self.behavior == "error":
            return {
                prompt_id: {
                    "status": {
                        "status_str": "error",
                        "messages": [
                            [
                                "execution_error",
                                {
                                    "node_id": "5",
                                    "node_type": "KSampler",
                                    "exception_message": "Out of memory",
                                },
                            ]
                        ],
                    }
                }
            }

        outputs = {}

        if self.behavior != "empty":
            outputs = {"7": {"images": [self.outputs[prompt_id]]}}

        return {
            prompt_id: {
                "status": {"status_str": "success", "completed": True},
                "outputs": outputs,
            }
        }

    def post(self, path, headers, body):
        if path == "/prompt":
            return self.post_prompt(json.loads(body)["prompt"])
        if path == "/upload/image":
            return self.post_upload(headers, body)
        if path == "/free":
            if self.free_ok:
                self.models_loaded = 0
            return 200, {}
        if path == "/interrupt":
            target = json.loads(body).get("prompt_id")
            self.events.append(f"interrupt {target}")
            if target in self.running:
                self.running.remove(target)
            return 200, {}
        if path == "/queue":
            for item in json.loads(body).get("delete", []):
                self.pending.remove(item)
            return 200, {}
        return 404, {}

    def post_prompt(self, workflow):
        if self.reject:
            return 400, self.reject

        self.workflows.append(workflow)
        prompt_id = f"prompt-{len(self.workflows)}"
        self.models_loaded = 1
        self.running.append(prompt_id)

        prefix = next(
            node["inputs"]["filename_prefix"]
            for node in workflow.values()
            if node.get("class_type") == "SaveImage"
        )
        subfolder, _, name = prefix.rpartition("/")
        filename = f"{name}_00001_.png"
        copy = self.comfy_dir / "output" / subfolder / filename
        copy.parent.mkdir(parents=True, exist_ok=True)
        copy.write_bytes(png_bytes())

        self.outputs[prompt_id] = {
            "filename": filename,
            "subfolder": subfolder,
            "type": "output",
        }

        if self.on_prompt:
            self.on_prompt()

        return 200, {"prompt_id": prompt_id}

    def post_upload(self, headers, body):
        message = BytesParser().parsebytes(
            b"Content-Type: " + headers["Content-Type"].encode() + b"\r\n\r\n" + body
        )
        fields = {}
        filename = None
        content = None

        for part in message.get_payload():
            name = part.get_param("name", header="content-disposition")
            if part.get_filename():
                filename = part.get_filename()
                content = part.get_payload(decode=True)
            else:
                fields[name] = part.get_payload(decode=True).decode()

        target = self.comfy_dir / "input" / fields.get("subfolder", "") / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

        return 200, {
            "name": filename,
            "subfolder": fields.get("subfolder", ""),
            "type": "input",
        }


class EngineTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="imagehearth-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

        self.comfy_dir = self.tmp / "ComfyUI"
        (self.comfy_dir / "input").mkdir(parents=True)
        (self.comfy_dir / "output").mkdir()

        self.comfy = FakeComfy(self.comfy_dir)
        self.ollama = FakeOllama()
        self.addCleanup(self.comfy.stop)
        self.addCleanup(self.ollama.stop)

        patches = {
            "COMFY_DIR": self.comfy_dir,
            "COMFY_PORT": self.comfy.port,
            "COMFY_API": f"http://127.0.0.1:{self.comfy.port}",
            "OLLAMA_API": f"http://127.0.0.1:{self.ollama.port}",
            # Sin servidor en estos puertos: en Windows rechazar una conexión tarda 2 s.
            "LMSTUDIO_API": f"http://127.0.0.1:{self.ollama.port}/lmstudio",
            "LLAMACPP_API": f"http://127.0.0.1:{self.ollama.port}/llamacpp",
            "VLLM_API": f"http://127.0.0.1:{self.ollama.port}/vllm",
            "OUTPUT_DIR": self.tmp / "output",
            "LOCK_FILE": self.tmp / "engine.lock",
            "PID_FILE": self.tmp / "state" / "comfyui.pid",
            "STATE_FILE": self.tmp / "state" / "session.json",
            "POLL_INTERVAL": 0.01,
            "OLLAMA_CHECK_INTERVAL": 0.0,
            "FREE_TIMEOUT": 0.1,
            "CANCEL_TIMEOUT": 1,
            "UNLOAD_TIMEOUT": 1,
            "RESTORE_TIMEOUT": 1,
            "INSTALL_MANIFEST": self.tmp / "install.json",
        }

        for name, value in patches.items():
            patcher = mock.patch.object(config, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

        gpu = mock.patch(
            "imagehearth_mcp.engine.gpu._from_nvidia_smi",
            return_value=20000,
        )
        self.gpu_free = gpu.start()
        self.addCleanup(gpu.stop)

        # Los modelos reales pesan decenas de GB: salvo que una prueba de catálogo
        # lo cambie, todos constan como presentes.
        present = mock.patch(
            "imagehearth_mcp.provisioner.models.inspect",
            side_effect=lambda items, folder, extra=None: [
                models.ModelState(item, Path(folder) / item.dest, models.PRESENT)
                for item in items
            ],
        )
        self.models_present = present.start()
        self.addCleanup(present.stop)

    def outputs(self):
        return list(config.OUTPUT_DIR.glob("*")) if config.OUTPUT_DIR.exists() else []


def swap_models(real, replacements):
    """The manifest with `replacements` (name -> Model) instead of those models everywhere."""
    import dataclasses

    models = {name: replacements.get(name, model) for name, model in real.models.items()}

    def pick(items):
        return tuple(models[item.name] for item in items)

    def options(found):
        return tuple(dataclasses.replace(item, models=pick(item.models)) for item in found)

    return dataclasses.replace(
        real,
        models=models,
        profiles={
            name: dataclasses.replace(profile, models=pick(profile.models))
            for name, profile in real.profiles.items()
        },
        quality_models={
            name: dataclasses.replace(model, options=options(model.options))
            for name, model in real.quality_models.items()
        },
        edit_options=options(real.edit_options),
    )
