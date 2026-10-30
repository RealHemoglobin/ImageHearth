import json
import logging
import subprocess
import sys
from pathlib import Path

from PIL import Image

from engine import config, kontext
from engine.image_router import create_image
from engine.log import SharedRotatingFileHandler
from engine.validation import fit_to_limits, resolve_workflow, validate_dimensions
from engine.workflow_runner import run_workflow
from tests.harness import EngineTestCase

ROOT = Path(__file__).resolve().parent.parent


class KontextReferences(EngineTestCase):
    def make_reference(self, relative, color="blue", size=(64, 64)):
        path = self.tmp / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", size, color).save(path)
        return path

    def test_same_filename_references_stay_separate(self):
        first = self.make_reference("a/foto.png", "red")
        second = self.make_reference("b/foto.png", "blue")
        seen = []
        self.comfy.on_prompt = lambda: seen.extend(
            sorted(p.name for p in (self.comfy_dir / "input").rglob("*.png"))
        )

        kontext.generate("edita", image_paths=[first, second])

        self.assertEqual(seen, ["reference_1.png", "reference_2.png"])
        images = [
            node["inputs"]["image"]
            for node in self.comfy.workflows[0].values()
            if node.get("class_type") == "LoadImage"
        ]
        self.assertEqual(len(set(images)), 2)

    def test_user_inputs_survive_and_run_folder_is_removed(self):
        mine = self.comfy_dir / "input" / "foto.png"
        mine.write_bytes(b"mi archivo")
        reference = self.make_reference("foto.png")

        result = kontext.generate("edita", image_paths=[reference])

        self.assertEqual(mine.read_bytes(), b"mi archivo")
        self.assertEqual(result.warnings, [])
        self.assertEqual(
            list((self.comfy_dir / "input" / "imageengine").iterdir()),
            [],
        )

    def test_inputs_removed_after_failure(self):
        self.comfy.behavior = "error"
        reference = self.make_reference("foto.png")

        with self.assertRaises(RuntimeError):
            kontext.generate("edita", image_paths=[reference])

        self.assertEqual(
            list((self.comfy_dir / "input" / "imageengine").iterdir()),
            [],
        )

    def test_seed_changes_between_runs(self):
        reference = self.make_reference("foto.png")

        kontext.generate("edita", image_paths=[reference])
        kontext.generate("edita", image_paths=[reference])

        seeds = {w["192:31"]["inputs"]["seed"] for w in self.comfy.workflows}
        self.assertEqual(len(seeds), 2)

    def test_large_reference_is_reduced_with_warning(self):
        reference = self.make_reference("grande.png", size=(6000, 3000))

        width, height, warning = kontext.output_dimensions(reference)

        self.assertLessEqual(width, config.MAX_DIMENSION)
        self.assertLessEqual(width * height, config.MAX_PIXELS)
        self.assertEqual(width % 16, 0)
        self.assertIn("6000x3000", warning)

    def test_negative_dimensions_rejected(self):
        reference = self.make_reference("foto.png")

        with self.assertRaises(ValueError):
            kontext.output_dimensions(reference, -100, 512)


class Validation(EngineTestCase):
    def test_internal_workflow_is_blocked(self):
        with self.assertRaisesRegex(ValueError, "no disponible"):
            resolve_workflow("flux_kontext_dev_basic", "fast")

    def test_path_traversal_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "no válido"):
            resolve_workflow("../secreto", "fast")

    def test_total_pixels_limit(self):
        with self.assertRaisesRegex(ValueError, "píxeles"):
            validate_dimensions(4096, 4096)

    def test_oversized_dimension_in_runner(self):
        with self.assertRaises(ValueError):
            run_workflow("sdxl_turbo.json", "x", width=100000)

        self.assertEqual(self.comfy.workflows, [])

    def test_fit_to_limits_keeps_small_sizes(self):
        self.assertEqual(fit_to_limits(1024, 768), (1024, 768))

    def test_negative_prompt_ignored_warns_on_flux(self):
        result = create_image("gato", workflow="flux_dev", negative_prompt="perro")

        self.assertIn("ADVERTENCIA: flux_dev ignora negative_prompt", result)

    def test_negative_prompt_applied_on_sdxl(self):
        result = create_image("gato", negative_prompt="perro")

        self.assertNotIn("ADVERTENCIA", result)
        self.assertEqual(self.comfy.workflows[0]["3"]["inputs"]["text"], "perro")


class Logging(EngineTestCase):
    def test_rotation_shared_between_handlers(self):
        path = self.tmp / "shared.log"
        first = SharedRotatingFileHandler(path, maxBytes=200, backupCount=2)
        second = SharedRotatingFileHandler(path, maxBytes=200, backupCount=2)
        self.addCleanup(first.close)
        self.addCleanup(second.close)

        for index in range(40):
            record = logging.LogRecord(
                "t", logging.INFO, "f", 1, f"linea {index:04}", None, None
            )
            (first if index % 2 else second).emit(record)

        self.assertTrue((self.tmp / "shared.log.1").exists())
        self.assertFalse((self.tmp / "shared.log.3").exists())
        self.assertIn("linea 0039", path.read_text())


class McpProtocol(EngineTestCase):
    def test_server_lists_tools_over_stdio(self):
        messages = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            },
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "list_workflows", "arguments": {}},
            },
        ]

        process = subprocess.Popen(
            [sys.executable, str(ROOT / "mcp" / "server.py")],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        self.addCleanup(process.wait, 30)
        self.addCleanup(process.stdout.close)
        self.addCleanup(process.stdin.close)

        process.stdin.write("".join(json.dumps(m) + "\n" for m in messages))
        process.stdin.flush()

        # Cada línea debe ser JSON-RPC válido: stdout es del protocolo.
        replies = {}

        while 3 not in replies:
            reply = json.loads(process.stdout.readline())
            replies[reply["id"]] = reply

        tools = {tool["name"] for tool in replies[2]["result"]["tools"]}
        self.assertTrue(
            {"create_image", "recover_engine", "get_engine_status"} <= tools
        )

        text = replies[3]["result"]["content"]
        self.assertNotIn("flux_kontext_dev_basic", json.dumps(text))
        self.assertIn("sdxl_turbo", json.dumps(text))
