"""`memory_mode`, proveedores de memoria y progreso, con servidores HTTP simulados."""

import asyncio
import importlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import urlparse

from imagehearth_mcp import server
from imagehearth_mcp.engine import (
    comfyui_manager,
    config,
    memory,
    memory_servers,
    orchestrator,
    progress,
    state,
)
from imagehearth_mcp.engine.image_router import create_image
from imagehearth_mcp.engine.status import get_status
from tests.harness import EngineTestCase, FakeServer


class FakeLMStudio(FakeServer):
    def __init__(self, v1=True):
        self.v1 = v1
        self.instances = []
        self.fail_load = False
        super().__init__()

    def get(self, path, query):
        if path == "/api/v1/models" and self.v1:
            return 200, {
                "models": [
                    {
                        "key": "qwen",
                        "size_bytes": 1024 * 1024,
                        "loaded_instances": [
                            {"id": name, "config": {"context_length": 4096}}
                            for name in self.instances
                        ],
                    }
                ]
            }
        if path == "/api/v0/models" and not self.v1:
            return 200, {"data": [{"id": "qwen", "state": "loaded"}]}
        return 404, {}

    def post(self, path, headers, body):
        data = json.loads(body)

        if path == "/api/v1/models/unload":
            self.instances.remove(data["instance_id"])
            return 200, {"instance_id": data["instance_id"]}
        if path == "/api/v1/models/load":
            if self.fail_load:
                return 500, {}
            self.events.append(f"load {data['model']} {data.get('context_length')}")
            self.instances.append(data["model"])
            return 200, {"status": "loaded"}
        return 404, {}


class FakeLlamaCpp(FakeServer):
    def __init__(self, router=False):
        self.router = router
        self.status = "loaded"
        self.sleeping = False
        super().__init__()

    def get(self, path, query):
        if path == "/models":
            if self.router:
                return 200, {"data": [{"id": "m", "status": {"value": self.status}}]}
            return 200, {"data": [{"id": "m"}]}
        if path == "/props":
            return 200, {
                "default_generation_settings": {},
                "model_path": "/models/qwen.gguf",
                "is_sleeping": self.sleeping,
            }
        return 404, {}

    def post(self, path, headers, body):
        self.status = {"/models/unload": "unloaded", "/models/load": "loaded"}[path]
        return 200, {"success": True}


class FakeVllm(FakeServer):
    def __init__(self, sleep_mode=True, owner="vllm"):
        self.sleep_mode = sleep_mode
        self.owner = owner
        self.sleeping = False
        super().__init__()

    def get(self, path, query):
        if path == "/v1/models":
            return 200, {"data": [{"id": "qwen", "owned_by": self.owner}]}
        if path == "/is_sleeping" and self.sleep_mode:
            return 200, {"is_sleeping": self.sleeping}
        return 404, {}

    def post(self, path, headers, body):
        self.sleeping = urlparse(path).path == "/sleep"
        return 200, {}


class OtherProgram(FakeServer):
    """Lo que escucha de verdad en el 8080 de muchas máquinas."""

    def get(self, path, query):
        return 200, b"<html>SearXNG</html>"

    def post(self, path, headers, body):
        self.events.append(path)
        return 200, {}


class Providers(EngineTestCase):
    def serve(self, fake, setting):
        self.addCleanup(fake.stop)
        patcher = mock.patch.object(config, setting, f"http://127.0.0.1:{fake.port}")
        patcher.start()
        self.addCleanup(patcher.stop)
        return fake

    def setUp(self):
        super().setUp()
        # Puertos cerrados por defecto: cada prueba enciende el que necesita.
        for setting in ("LMSTUDIO_API", "LLAMACPP_API", "VLLM_API"):
            patcher = mock.patch.object(config, setting, "http://127.0.0.1:9")
            patcher.start()
            self.addCleanup(patcher.stop)

    def generate(self):
        return create_image("a cat")

    def test_lmstudio_is_unloaded_and_restored_with_its_settings(self):
        lm = self.serve(FakeLMStudio(), "LMSTUDIO_API")
        lm.instances = ["qwen"]
        seen = []
        self.comfy.on_prompt = lambda: seen.append(list(lm.instances))
        self.generate()
        self.assertEqual(seen, [[]])
        self.assertEqual(lm.instances, ["qwen"])
        self.assertIn("load qwen 4096", lm.events)
        self.assertIsNone(state.read())

    def test_several_servers_in_one_session(self):
        lm = self.serve(FakeLMStudio(), "LMSTUDIO_API")
        lm.instances = ["qwen"]
        self.ollama.add("gemma")
        self.generate()
        self.assertIn("gemma", self.ollama.loaded)
        self.assertEqual(lm.instances, ["qwen"])

    def test_restore_failure_requires_recovery_and_recover_works(self):
        lm = self.serve(FakeLMStudio(), "LMSTUDIO_API")
        lm.instances = ["qwen"]
        lm.fail_load = True
        result = self.generate()
        self.assertIn("recovery_required", result)
        self.assertEqual(get_status()["imageengine"]["status"], "recovery_required")
        lm.fail_load = False
        self.assertEqual(orchestrator.recover()["restored"], ["lmstudio/qwen"])
        self.assertIsNone(state.read())

    def test_server_gone_mid_session_keeps_the_protection(self):
        lm = self.serve(FakeLMStudio(), "LMSTUDIO_API")
        lm.instances = ["qwen"]
        self.comfy.on_prompt = lm.stop
        result = self.generate()
        self.assertIn("recovery_required", result)
        self.assertEqual(state.read()["models"][0]["name"], "lmstudio/qwen")

    def test_interrupted_session_is_recovered_with_its_provider(self):
        lm = self.serve(FakeLMStudio(), "LMSTUDIO_API")
        state.write(
            phase=state.GENERATING,
            run_id="abc",
            prompt_id=None,
            models=[
                {
                    "name": "lmstudio/qwen",
                    "provider": "lmstudio",
                    "key": "qwen",
                    "instance_id": "qwen",
                }
            ],
        )
        self.assertEqual(orchestrator.recover()["restored"], ["lmstudio/qwen"])
        self.assertEqual(lm.instances, ["qwen"])

    def test_old_lmstudio_warns_with_advice(self):
        self.serve(FakeLMStudio(v1=False), "LMSTUDIO_API")
        result = self.generate()
        self.assertIn("WARNING: lmstudio/qwen stays loaded", result)
        self.assertIn("lms unload", result)

    def test_single_model_llamacpp_warns_and_is_not_restored(self):
        self.serve(FakeLlamaCpp(), "LLAMACPP_API")
        result = self.generate()
        self.assertTrue(Path(result.splitlines()[0]).exists())
        self.assertIn("--sleep-idle-seconds", result)
        self.assertIsNone(state.read())

    def test_fixed_model_without_memory_fails_before_generating(self):
        self.serve(FakeLlamaCpp(), "LLAMACPP_API")
        self.gpu_free.return_value = 100

        with (
            mock.patch("imagehearth_mcp.engine.gpu._from_comfyui", return_value=100),
            self.assertRaisesRegex(MemoryError, "--sleep-idle-seconds"),
        ):
            self.generate()

        self.assertEqual(self.comfy.workflows, [])
        self.assertIsNone(state.read())

    def test_sleeping_llamacpp_holds_nothing(self):
        self.serve(FakeLlamaCpp(), "LLAMACPP_API").sleeping = True
        self.assertNotIn("WARNING", self.generate())

    def test_llamacpp_router_unloads_and_restores(self):
        llama = self.serve(FakeLlamaCpp(router=True), "LLAMACPP_API")
        seen = []
        self.comfy.on_prompt = lambda: seen.append(llama.status)
        self.generate()
        self.assertEqual(seen, ["unloaded"])
        self.assertEqual(llama.status, "loaded")

    def test_vllm_sleeps_and_wakes(self):
        vllm = self.serve(FakeVllm(), "VLLM_API")
        seen = []
        self.comfy.on_prompt = lambda: seen.append(vllm.sleeping)
        self.generate()
        self.assertEqual(seen, [True])
        self.assertFalse(vllm.sleeping)

    def test_vllm_without_sleep_mode_warns(self):
        self.serve(FakeVllm(sleep_mode=False), "VLLM_API")
        self.assertIn("--enable-sleep-mode", self.generate())

    def test_foreign_servers_are_never_touched(self):
        other = self.serve(OtherProgram(), "LLAMACPP_API")
        wrong = self.serve(FakeVllm(owner="someone"), "VLLM_API")
        self.assertNotIn("WARNING", self.generate())
        self.assertEqual(other.events, [])
        self.assertEqual(wrong.events, [])

    def test_status_reports_each_server(self):
        self.serve(FakeLMStudio(), "LMSTUDIO_API").instances = ["qwen"]
        servers = get_status()["memory"]["servers"]
        self.assertEqual(servers["lmstudio"]["loaded_models"], ["lmstudio/qwen"])
        self.assertEqual(servers["vllm"]["status"], "stopped")
        self.assertNotIn("lmstudio/qwen", get_status()["ollama"]["loaded_models"])

    def test_off_touches_nothing_and_does_not_check(self):
        self.ollama.add("gemma")
        self.gpu_free.return_value = 1

        with mock.patch.object(config, "MEMORY_MODE", "off"):
            self.generate()

        self.assertIn("gemma", self.ollama.loaded)
        self.assertNotIn("unload gemma", self.ollama.events)

    def test_manual_with_memory_generates_without_touching(self):
        self.ollama.add("gemma")

        with mock.patch.object(config, "MEMORY_MODE", "manual"):
            self.assertTrue(Path(self.generate().splitlines()[0]).exists())
            self.assertEqual(get_status()["memory"]["mode"], "manual")

        self.assertNotIn("unload gemma", self.ollama.events)

    def test_manual_without_memory_fails_with_advice(self):
        self.ollama.add("gemma")

        with (
            mock.patch.object(config, "MEMORY_MODE", "manual"),
            mock.patch("imagehearth_mcp.engine.gpu.free_mib", return_value=100),
            self.assertRaisesRegex(MemoryError, "memory_mode is manual"),
        ):
            self.generate()

        self.assertIn("gemma", self.ollama.loaded)
        self.assertEqual(self.comfy.workflows, [])
        self.assertIsNone(state.read())

    def test_memory_mode_beats_ollama_mode(self):
        self.ollama.add("gemma")

        with (
            mock.patch.object(config, "OLLAMA_MODE", "off"),
            mock.patch.object(config, "MEMORY_MODE", "auto"),
        ):
            self.assertIsInstance(memory.get_provider(), memory.CombinedProvider)

        with mock.patch.object(config, "OLLAMA_MODE", "off"):
            self.assertIsInstance(memory.get_provider(), memory.DisabledProvider)


class MemoryModeConfig(unittest.TestCase):
    def load(self, toml="", **env):
        folder = Path(tempfile.mkdtemp(prefix="imagehearth-test-config-"))
        self.addCleanup(shutil.rmtree, folder, True)
        self.addCleanup(importlib.reload, config)
        path = folder / "config.toml"
        path.write_text(toml, encoding="utf-8")
        clean = {k: v for k, v in os.environ.items() if not k.startswith("IMAGEHEARTH_")}
        clean["IMAGEHEARTH_CONFIG_FILE"] = str(path)
        clean.update(env)

        with mock.patch.dict(os.environ, clean, clear=True):
            return importlib.reload(config).memory_mode()

    def test_precedence(self):
        self.assertEqual(self.load(), "auto")
        self.assertEqual(self.load('ollama_mode = "off"\n'), "off")
        self.assertEqual(self.load('memory_mode = "manual"\n'), "manual")
        self.assertEqual(self.load('memory_mode = "auto"\nollama_mode = "off"\n'), "auto")
        self.assertEqual(self.load(IMAGEHEARTH_MEMORY_MODE="off"), "off")
        self.assertEqual(
            self.load('memory_mode = "auto"\n', IMAGEHEARTH_OLLAMA_MODE="off"), "auto"
        )

    def test_invalid_names_its_source(self):
        with self.assertRaisesRegex(RuntimeError, "IMAGEHEARTH_MEMORY_MODE"):
            self.load(IMAGEHEARTH_MEMORY_MODE="maybe")


class FakeContext:
    def __init__(self):
        self.reports = []

    async def report_progress(self, progress_value, total=None, message=None):
        self.reports.append((progress_value, message))


class Responses(EngineTestCase):
    def test_progress_is_emitted_during_generation(self):
        ctx = FakeContext()

        with mock.patch.object(server, "HEARTBEAT_SECONDS", 0.01):
            self.comfy.on_prompt = lambda: asyncio.run(asyncio.sleep(0.1))
            result = asyncio.run(server.create_image("a cat", ctx=ctx))

        self.assertTrue(Path(result.splitlines()[0]).exists())
        self.assertTrue(ctx.reports)
        values = [value for value, _ in ctx.reports]
        self.assertEqual(values, sorted(values))
        self.assertTrue(any("Generating" in text or "Starting" in text for _, text in ctx.reports))

    def test_works_without_context(self):
        self.assertTrue(asyncio.run(server.create_image("a cat")))

    def test_default_response_has_only_the_path_first(self):
        result = asyncio.run(server.create_image("a cat"))
        self.assertIsInstance(result, str)
        self.assertTrue(Path(result.splitlines()[0]).is_file())

    def test_optional_image_keeps_the_path_first(self):
        text, image = asyncio.run(server.create_image("a cat", include_image=True))
        self.assertTrue(Path(text.splitlines()[0]).is_file())
        self.assertEqual(image.to_image_content().mimeType, "image/jpeg")

    def test_create_image_covers_generation_and_editing(self):
        created = asyncio.run(server.create_image("a cat", workflow="flux_dev", width=512, height=512))
        reference = created.splitlines()[0]
        edited = asyncio.run(server.create_image("a dog", image_paths=[reference]))
        self.assertIn("kontext_", edited.splitlines()[0])

        with self.assertRaisesRegex(ValueError, "at most|At most"):
            asyncio.run(server.create_image("x", image_paths=[reference] * 7))

    def test_cancelling_cleans_the_session(self):
        self.ollama.add("gemma")
        self.comfy.behavior = "never"

        async def cancelled():
            task = asyncio.create_task(server.create_image("a cat"))

            while not self.comfy.workflows:
                await asyncio.sleep(0.01)

            threads = asyncio.all_tasks()
            task.cancel()

            with self.assertRaises(asyncio.CancelledError):
                await task

            return threads

        asyncio.run(cancelled())
        self.assertIsNone(state.read())
        self.assertIn("gemma", self.ollama.loaded)
        self.assertIn("interrupt prompt-1", self.comfy.events)
        self.assertEqual(self.outputs(), [])


class WithoutInstallation(EngineTestCase):
    def setUp(self):
        super().setUp()
        self.comfy.stop()
        self.models_present.side_effect = None
        from imagehearth_mcp.provisioner import models

        self.models_present.side_effect = lambda items, folder, extra=None: [
            models.ModelState(item, Path(folder) / item.dest, models.MISSING) for item in items
        ]
        shutil.rmtree(self.comfy_dir)

    def test_status_says_what_is_missing(self):
        engine = get_status()["imageengine"]
        self.assertEqual(engine["status"], "not_installed")
        self.assertIn("imagehearth-mcp setup", engine["issues"][0])

    def test_image_tools_name_the_command(self):
        for call in (
            lambda: create_image("a cat"),
            lambda: create_image("a cat", quality="high"),
            lambda: asyncio.run(server.create_image("y", image_paths=["/x.png"])),
        ):
            with self.assertRaisesRegex(ValueError, "imagehearth-mcp setup --profile"):
                call()

    def test_ensure_comfyui_names_the_command(self):
        with self.assertRaisesRegex(FileNotFoundError, "imagehearth-mcp setup"):
            comfyui_manager.start()

    def test_list_workflows_explains(self):
        self.assertIn("imagehearth-mcp setup", server.list_workflows()[0]["next_step"])

    def test_recover_has_nothing_to_do(self):
        self.assertEqual(asyncio.run(server.recover_engine())["status"], "ready")

    def test_models_missing_with_comfyui_present(self):
        self.comfy_dir.mkdir()
        (self.comfy_dir / "main.py").write_text("", encoding="utf-8")
        self.assertIn("--profile fast", get_status()["imageengine"]["issues"][0])


def test_memory_servers_module_is_lazy():
    assert memory_servers.REQUEST_TIMEOUT > 0
    assert progress.Tracker().stage
