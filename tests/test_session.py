import contextlib
import io
import threading
from unittest import mock

import requests

from engine import config, ollama_manager, orchestrator, state
from engine.status import get_status
from engine.workflow_runner import run_workflow
from tests.harness import EngineTestCase


def generate(timeout=5):
    return run_workflow("sdxl_turbo.json", "un gato", timeout=timeout)


class SuccessfulSession(EngineTestCase):
    def test_restores_ollama_and_cleans_up(self):
        self.ollama.add(
            "modelo",
            context_length=131072,
            expires_at="2319-02-09T21:46:59.635940495Z",
        )

        result = generate()

        self.assertTrue(result.path.is_file())
        self.assertEqual(result.warnings, [])
        self.assertEqual(str(result), str(result.path))
        self.assertIn("modelo", self.ollama.loaded)
        self.assertIsNone(state.read())

        restore = self.ollama.requests[-1]
        self.assertEqual(restore["keep_alive"], -1)
        self.assertEqual(restore["options"], {"num_ctx": 131072})

    def test_unloads_ollama_before_prompt(self):
        self.ollama.add("modelo")
        seen = []
        self.comfy.on_prompt = lambda: seen.append(dict(self.ollama.loaded))

        generate()

        self.assertEqual(seen, [{}])

    def test_removes_only_its_copy_from_comfy_output(self):
        other = self.comfy_dir / "output" / "imageengine" / "antigua.png"
        other.parent.mkdir(parents=True)
        other.write_bytes(b"x")

        generate()

        remaining = [p.name for p in other.parent.iterdir()]
        self.assertEqual(remaining, ["antigua.png"])

    def test_writes_nothing_to_stdout(self):
        self.ollama.add("modelo")
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            generate()

        self.assertEqual(stdout.getvalue(), "")


class ReleaseFailures(EngineTestCase):
    def test_image_survives_and_ollama_waits_with_foreign_job(self):
        self.ollama.add("modelo")
        self.comfy.free_ok = False
        self.comfy.on_prompt = lambda: self.comfy.pending.append("ajeno")

        with mock.patch("engine.comfyui_manager.restart") as restart:
            result = generate()

        restart.assert_not_called()
        self.assertTrue(result.path.is_file())
        self.assertIn("recovery_required", str(result))
        self.assertNotIn("modelo", self.ollama.loaded)
        self.assertEqual(state.read()["phase"], state.RECOVERY_REQUIRED)
        self.assertEqual(state.read()["models"][0]["name"], "modelo")

    def test_restarts_once_with_empty_queue(self):
        self.ollama.add("modelo")
        self.comfy.free_ok = False

        def restart():
            self.comfy.free_ok = True

        with mock.patch(
            "engine.comfyui_manager.restart",
            side_effect=restart,
        ) as mocked:
            result = generate()

        mocked.assert_called_once()
        self.assertIn("ComfyUI se reinició", str(result))
        self.assertIn("modelo", self.ollama.loaded)
        self.assertIsNone(state.read())

    def test_failed_restart_keeps_ollama_unloaded(self):
        self.ollama.add("modelo")
        self.comfy.free_ok = False

        with mock.patch("engine.comfyui_manager.restart"):
            result = generate()

        self.assertIn("recovery_required", str(result))
        self.assertNotIn("modelo", self.ollama.loaded)

    def test_recover_restores_after_fix(self):
        self.ollama.add("modelo")
        self.comfy.free_ok = False
        self.comfy.on_prompt = lambda: self.comfy.pending.append("ajeno")
        generate()

        self.assertEqual(
            get_status()["imageengine"]["status"],
            "recovery_required",
        )

        self.comfy.pending.clear()
        self.comfy.free_ok = True
        result = orchestrator.recover()

        self.assertEqual(result["restored"], ["modelo"])
        self.assertIn("modelo", self.ollama.loaded)
        self.assertIsNone(state.read())

    def test_refuses_new_session_while_vram_held(self):
        state.write(phase=state.RECOVERY_REQUIRED, run_id="ab", models=[])
        self.comfy.free_ok = False
        self.comfy.models_loaded = 1
        self.comfy.pending.append("ajeno")

        with self.assertRaises(orchestrator.RecoveryRequired):
            generate()

        self.assertEqual(self.comfy.workflows, [])


class ComfyCrash(EngineTestCase):
    def crash(self):
        threading.Thread(target=self.comfy.stop).start()

    def test_restores_ollama_when_comfy_dies(self):
        self.ollama.add("modelo")
        self.comfy.on_prompt = self.crash

        with self.assertRaises(requests.RequestException):
            generate()

        self.assertIn("modelo", self.ollama.loaded)
        self.assertIsNone(state.read())

    def test_low_vram_blocks_restore_after_death(self):
        self.ollama.add("modelo")
        self.comfy.on_prompt = self.crash
        self.gpu_free.return_value = 0

        with self.assertRaises(RuntimeError) as caught:
            generate()

        self.assertIn("recovery_required", str(caught.exception))
        self.assertNotIn("modelo", self.ollama.loaded)


class GenerationFailures(EngineTestCase):
    def test_timeout_interrupts_before_restoring(self):
        self.ollama.add("modelo")
        self.comfy.behavior = "never"

        with self.assertRaises(TimeoutError):
            generate(timeout=0.05)

        self.assertIn("interrupt prompt-1", self.comfy.events)
        self.assertEqual(self.comfy.running, [])
        self.assertIn("modelo", self.ollama.loaded)

    def test_execution_error_reports_node(self):
        self.comfy.behavior = "error"

        with self.assertRaisesRegex(RuntimeError, "KSampler.*Out of memory"):
            generate()

    def test_rejection_includes_node_errors(self):
        self.comfy.reject = {
            "error": {"message": "Prompt no válido"},
            "node_errors": {
                "5": {
                    "class_type": "KSampler",
                    "errors": [{"message": "Falta modelo", "details": "x.safetensors"}],
                }
            },
        }

        with self.assertRaisesRegex(RuntimeError, "Falta modelo x.safetensors"):
            generate()

    def test_completed_without_image_fails_immediately(self):
        self.comfy.behavior = "empty"

        with self.assertRaisesRegex(RuntimeError, "sin producir"):
            generate(timeout=60)

    def test_corrupt_image_is_not_saved(self):
        self.comfy.behavior = "corrupt"

        with self.assertRaisesRegex(RuntimeError, "no válida"):
            generate()

        self.assertEqual(self.outputs(), [])

    def test_failure_is_not_masked_by_cleanup(self):
        self.ollama.add("modelo")
        self.ollama.fail_restore = True
        self.comfy.behavior = "error"

        with self.assertRaises(RuntimeError) as caught:
            generate()

        message = str(caught.exception)
        self.assertIn("Out of memory", message)
        self.assertIn("No se pudieron restaurar", message)


class OllamaRaces(EngineTestCase):
    def test_model_reloaded_before_submit_is_unloaded_and_restored(self):
        self.ollama.add("original")
        original_unload = ollama_manager.unload_all

        def unload_then_reload(models, timeout=None):
            original_unload(models, timeout)
            if "intruso" not in {m["name"] for m in models}:
                self.ollama.add("intruso")

        seen = []
        self.comfy.on_prompt = lambda: seen.append(set(self.ollama.loaded))

        with mock.patch(
            "engine.orchestrator.ollama_manager.unload_all",
            side_effect=unload_then_reload,
        ):
            result = generate()

        self.assertEqual(seen, [set()])
        self.assertEqual(result.warnings, [])
        self.assertEqual(set(self.ollama.loaded), {"original", "intruso"})

    def test_model_loaded_during_generation_only_warns(self):
        self.comfy.on_prompt = lambda: self.ollama.add("intruso")
        self.comfy.behavior = "ok"
        real_history = self.comfy.get_history
        calls = []

        def slow_history(prompt_id):
            calls.append(prompt_id)
            return {} if len(calls) < 2 else real_history(prompt_id)

        self.comfy.get_history = slow_history
        result = generate()

        self.assertIn("durante la generación", str(result))
        self.assertIn("intruso", self.ollama.loaded)
        self.assertNotIn("unload intruso", self.ollama.events)


class PersistedState(EngineTestCase):
    def test_dead_session_models_are_adopted_and_restored(self):
        state.write(
            phase=state.GENERATING,
            run_id="abc123",
            prompt_id="viejo",
            models=[{"name": "perdido", "size_vram": 1024 * 1024}],
        )
        self.comfy.running.append("viejo")
        leftovers = self.comfy_dir / "input" / "imageengine" / "abc123"
        leftovers.mkdir(parents=True)
        (leftovers / "reference_1.png").write_bytes(b"x")

        generate()

        self.assertIn("interrupt viejo", self.comfy.events)
        self.assertIn("perdido", self.ollama.loaded)
        self.assertFalse(leftovers.exists())
        self.assertIsNone(state.read())

    def test_failed_restore_stays_pending(self):
        self.ollama.add("modelo")
        self.ollama.fail_restore = True

        result = generate()

        self.assertIn("No se pudieron restaurar", str(result))
        self.assertEqual(state.read()["models"][0]["name"], "modelo")

    def test_unreadable_state_is_not_clean(self):
        config.STATE_FILE.parent.mkdir(parents=True)
        config.STATE_FILE.write_text("{roto")

        self.assertEqual(state.read()["phase"], state.RECOVERY_REQUIRED)


class Locking(EngineTestCase):
    def test_lock_wait_has_deadline(self):
        started = threading.Event()
        release = threading.Event()

        def hold():
            with orchestrator._engine_lock(timeout=1):
                started.set()
                release.wait(5)

        holder = threading.Thread(target=hold)
        holder.start()
        started.wait(5)

        try:
            with mock.patch.object(config, "LOCK_TIMEOUT", 0.05):
                with self.assertRaisesRegex(TimeoutError, "ocupado"):
                    generate()

            self.assertEqual(get_status()["imageengine"]["status"], "busy")
        finally:
            release.set()
            holder.join()

    def test_lock_released_after_failure(self):
        self.comfy.behavior = "error"

        with self.assertRaises(RuntimeError):
            generate()

        self.assertFalse(orchestrator.is_busy())


class OllamaManager(EngineTestCase):
    def test_unload_deadline_is_global(self):
        self.ollama.add("pegado")

        def post(path, headers, body):
            return 200, {}

        self.ollama.post = post

        with self.assertRaisesRegex(TimeoutError, "pegado"):
            ollama_manager.unload_all(
                ollama_manager.get_loaded_models(),
                timeout=0.05,
            )

    def test_embedding_model_falls_back(self):
        self.ollama.add("embed")
        original = self.ollama.post
        paths = []

        def post(path, headers, body):
            paths.append(path)
            if path == "/api/generate":
                return 400, {"error": "does not support generate"}
            return original(path, headers, body)

        self.ollama.post = post
        ollama_manager.unload_model("embed")

        self.assertEqual(paths, ["/api/generate", "/api/embed"])

    def test_short_keep_alive_is_preserved(self):
        from datetime import datetime, timedelta, timezone

        expires = datetime.now(timezone.utc) + timedelta(minutes=5)
        options = ollama_manager.restore_options(
            {"expires_at": expires.isoformat()}
        )

        self.assertRegex(options["keep_alive"], r"^(29\d|300)s$")


class Status(EngineTestCase):
    def test_ready(self):
        self.assertEqual(get_status()["imageengine"]["status"], "ready")

    def test_missing_route_is_degraded(self):
        self.comfy.status_route = False

        status = get_status()["imageengine"]

        self.assertEqual(status["status"], "degraded")
        self.assertIn("imageengine_status", status["issues"][0])
