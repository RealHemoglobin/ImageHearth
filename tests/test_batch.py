"""Phase 8: several images in one GPU session."""

import asyncio
import threading
from pathlib import Path
from unittest import mock

from PIL import Image

from imagehearth_mcp import server
from imagehearth_mcp.engine import (
    batch,
    comfyui_manager,
    config,
    orchestrator,
    progress,
    state,
)
from imagehearth_mcp.engine.image_router import create_image
from imagehearth_mcp.engine.result import ImageResult
from tests.harness import EngineTestCase


def prompt_of(workflow):
    return next(
        node["inputs"]["text"]
        for node in workflow.values()
        if node.get("class_type") == "CLIPTextEncode" and node["inputs"]["text"]
    )


def image_id_of(workflow):
    prefix = next(
        node["inputs"]["filename_prefix"]
        for node in workflow.values()
        if node.get("class_type") == "SaveImage"
    )
    return prefix.rpartition("/")[2]


class BatchCase(EngineTestCase):
    def make_reference(self, name="foto.png"):
        path = self.tmp / name
        Image.new("RGB", (64, 64), "blue").save(path)
        return str(path)

    def no_gpu(self):
        """Fail the test if the batch reaches the orchestrator."""
        patcher = mock.patch.object(
            batch, "generation_session", side_effect=AssertionError("touched the GPU")
        )
        patcher.start()
        self.addCleanup(patcher.stop)


class Validation(BatchCase):
    def reject(self, items, pattern, **common):
        self.no_gpu()

        with self.assertRaisesRegex(ValueError, pattern) as caught:
            batch.run(items, **common)

        self.assertEqual(self.comfy.events, [])
        self.assertEqual(self.ollama.requests, [])
        self.assertIsNone(state.read())
        return str(caught.exception)

    def test_empty_batch(self):
        self.reject([], "at least one")

    def test_over_the_limit_says_how_to_change_it(self):
        with mock.patch.object(config, "BATCH_LIMIT", 2, create=True):
            message = self.reject(
                [{"prompt": "a"}, {"prompt": "b"}, {"prompt": "c"}], "at most 2"
            )

        self.assertIn("--batch-limit", message)
        self.assertIn("3", message)

    def test_mixed_batch_lists_both_kinds(self):
        reference = self.make_reference()
        message = self.reject(
            [
                {"prompt": "a"},
                {"prompt": "b", "image_paths": [reference]},
                {"prompt": "c"},
            ],
            "all generations or all edits",
        )

        self.assertIn("Generations: items 1, 3", message)
        self.assertIn("Edits: items 2", message)

    def test_all_failures_are_reported_with_one_based_indexes(self):
        message = self.reject(
            [
                {"prompt": "ok"},
                {"prompt": "  "},
                {"prompt": "big", "width": 100000, "height": 64},
                {"prompt": "x", "image_paths": ["/no/such/file.png"], "mode": "generate"},
                {"prompt": "x", "quality": "ultra"},
                {"prompt": "x", "bogus": 1},
            ],
            "Item 2",
        )

        for number in (2, 3, 4, 5, 6):
            self.assertIn(f"Item {number}:", message)

        self.assertNotIn("Item 1:", message)

    def test_missing_reference(self):
        message = self.reject(
            [{"prompt": "a", "image_paths": ["/no/such/file.png"]}], "Item 1"
        )
        self.assertIn("file.png", message)

    def test_workflow_not_installed(self):
        from imagehearth_mcp.engine import catalog

        entries = catalog.entries()
        broken = {
            name: catalog.Entry(name, entry.profile, name != "flux_dev")
            for name, entry in entries.items()
        }

        with mock.patch.object(catalog, "entries", return_value=broken):
            message = self.reject(
                [{"prompt": "a", "workflow": "flux_dev"}, {"prompt": "b"}],
                "Item 1",
            )

        self.assertIn("not installed", message)
        self.assertNotIn("Item 2", message)

    def test_references_over_the_limit(self):
        reference = self.make_reference()
        self.reject(
            [{"prompt": "a", "image_paths": [reference] * 7}], "At most 6 references"
        )

    def test_common_values_apply_and_items_override(self):
        _, prepared = batch.validate(
            [
                {"prompt": "a"},
                {"prompt": "b", "quality": "fast", "width": 512, "height": 512},
            ],
            quality="high",
            width=1536,
            height=1024,
        )

        sizes = []

        for item in prepared:
            latent = next(
                node["inputs"]
                for node in item.workflow.values()
                if "Latent" in node.get("class_type", "")
            )
            sizes.append((item.name, latent["width"], latent["height"]))

        self.assertEqual(sizes[0], (prepared[0].name, 1536, 1024))
        self.assertEqual(sizes[1], ("sdxl_turbo", 512, 512))
        self.assertNotEqual(prepared[0].name, "sdxl_turbo")

    def test_edit_negative_prompt_is_a_warning(self):
        kind, prepared = batch.validate(
            [{"prompt": "a", "image_paths": [self.make_reference()]}],
            negative_prompt="blur",
        )

        self.assertEqual(kind, "edit")
        self.assertEqual(prepared[0].warnings, ["FLUX Kontext ignores negative_prompt."])


class OneSession(BatchCase):
    def count_starts(self):
        patcher = mock.patch.object(comfyui_manager, "start")
        started = patcher.start()
        self.addCleanup(patcher.stop)
        return started

    def test_models_and_comfy_are_handled_once(self):
        self.ollama.add("modelo")
        starts = self.count_starts()

        result = batch.run([{"prompt": f"p{n}"} for n in range(4)])

        self.assertEqual(starts.call_count, 1)
        self.assertEqual(len(self.comfy.workflows), 4)
        self.assertEqual(
            [e for e in self.ollama.events if e.startswith(("unload", "load"))],
            ["unload modelo", "load modelo"],
        )
        self.assertIn("modelo", self.ollama.loaded)
        self.assertIsNone(state.read())
        self.assertEqual(self.comfy.models_loaded, 0)
        self.assertEqual(len(self.outputs()), 4)
        self.assertTrue(all(o.path.is_file() for o in result.outcomes))
        self.assertEqual(result.warnings, [])

    def test_memory_is_checked_once_for_the_most_demanding_workflow(self):
        calls = []
        real = orchestrator._free_server_memory

        def spy(session):
            calls.append(session.required_mib)
            return real(session)

        with (
            mock.patch.object(
                orchestrator.catalog,
                "required_vram_mib",
                side_effect=lambda name: 4000 if name == "sdxl_turbo" else 12000,
            ),
            mock.patch.object(orchestrator, "_free_server_memory", spy),
        ):
            batch.run([{"prompt": "a"}, {"prompt": "b", "quality": "high"}])

        self.assertEqual(calls, [12000])

    def test_groups_by_workflow_and_answers_in_requested_order(self):
        items = [
            {"prompt": "a", "quality": "high"},
            {"prompt": "b", "quality": "fast"},
            {"prompt": "c", "quality": "high"},
            {"prompt": "d", "quality": "fast"},
        ]

        result = batch.run(items)

        executed = [prompt_of(w) for w in self.comfy.workflows]
        self.assertEqual(executed, ["a", "c", "b", "d"])

        by_prompt = {
            prompt_of(w): self.comfy_output_name(w) for w in self.comfy.workflows
        }
        names = [Path(o.path).stem for o in result.outcomes]
        self.assertEqual(names, [by_prompt[p] for p in "abcd"])

    def comfy_output_name(self, workflow):
        return image_id_of(workflow)

    def test_response_format(self):
        result = batch.run(
            [
                {"prompt": "a", "negative_prompt": "blur"},
                {"prompt": "b"},
            ]
        )
        lines = str(result).splitlines()

        self.assertEqual(len(lines), 2)
        self.assertRegex(lines[0], r"^1: .*\.png$")
        self.assertRegex(lines[1], r"^2: .*\.png$")

    def test_item_warning_goes_on_its_line(self):
        result = batch.BatchResult(
            [
                ImageResult(Path("/x/a.png"), ["careful"]),
                "boom",
                ImageResult(Path("/x/c.png")),
            ],
            ["global"],
        )

        self.assertEqual(
            str(result).splitlines(),
            [
                "1: /x/a.png | WARNING: careful",
                "2: ERROR: boom",
                "3: /x/c.png",
                "WARNING: global",
            ],
        )

    def test_edit_batch_uses_kontext_in_one_session(self):
        starts = self.count_starts()
        reference = self.make_reference()

        result = batch.run(
            [
                {"prompt": "uno", "image_paths": [reference]},
                {"prompt": "dos", "image_paths": [reference]},
            ]
        )

        self.assertEqual(starts.call_count, 1)
        self.assertEqual(len(self.comfy.workflows), 2)
        self.assertTrue(all(o.path.is_file() for o in result.outcomes))
        self.assertEqual(
            list((self.comfy_dir / "input" / "imagehearth").iterdir()), []
        )

    def test_progress_and_session_state_follow_the_batch(self):
        tracker = progress.Tracker()
        seen = []

        def on_prompt():
            data = state.read()
            seen.append((tracker.stage, data["batch_index"], data["batch_total"]))

        self.comfy.on_prompt = on_prompt

        with progress.tracking(tracker):
            batch.run([{"prompt": "a"}, {"prompt": "b"}, {"prompt": "c"}])

        self.assertEqual(
            seen,
            [
                ("Generating image 1 of 3", 1, 3),
                ("Generating image 2 of 3", 2, 3),
                ("Generating image 3 of 3", 3, 3),
            ],
        )
        self.assertIsNone(state.read())


class Failures(BatchCase):
    def crash(self):
        threading.Thread(target=self.comfy.stop).start()

    def test_failed_item_does_not_stop_the_rest(self):
        def on_prompt():
            self.comfy.behavior = "error" if len(self.comfy.workflows) == 2 else "ok"

        self.comfy.on_prompt = on_prompt

        result = batch.run([{"prompt": "a"}, {"prompt": "b"}, {"prompt": "c"}])
        lines = str(result).splitlines()

        self.assertEqual(len(self.comfy.workflows), 3)
        self.assertRegex(lines[0], r"^1: .*\.png$")
        self.assertRegex(lines[1], r"^2: ERROR: ComfyUI error")
        self.assertRegex(lines[2], r"^3: .*\.png$")
        self.assertIsNone(state.read())

    def test_comfy_down_aborts_the_rest_and_restores_models(self):
        self.ollama.add("modelo")
        self.comfy.on_prompt = lambda: (
            self.crash() if len(self.comfy.workflows) == 2 else None
        )

        result = batch.run([{"prompt": f"p{n}"} for n in range(4)])
        lines = str(result).splitlines()

        self.assertRegex(lines[0], r"^1: .*\.png$")
        self.assertIn("2: ERROR", lines[1])
        self.assertIn("3: ERROR: not attempted", lines[2])
        self.assertIn("4: ERROR: not attempted", lines[3])
        self.assertIn("modelo", self.ollama.loaded)
        self.assertIsNone(state.read())

    def test_crash_with_memory_held_leaves_a_recoverable_batch(self):
        self.ollama.add("modelo")
        self.gpu_free.return_value = 0
        self.comfy.on_prompt = lambda: (
            self.crash() if len(self.comfy.workflows) == 2 else None
        )

        result = batch.run([{"prompt": f"p{n}"} for n in range(3)])

        self.assertTrue(any("recovery_required" in w for w in result.warnings))
        pending = state.read()
        self.assertEqual(pending["phase"], state.RECOVERY_REQUIRED)
        self.assertEqual(pending["batch_total"], 3)
        self.assertNotIn("modelo", self.ollama.loaded)

        self.gpu_free.return_value = 20000
        recovered = orchestrator.recover()

        self.assertEqual(recovered["restored"], ["modelo"])
        self.assertIn("modelo", self.ollama.loaded)
        self.assertIsNone(state.read())

    def test_cancel_keeps_finished_images_and_restores_models(self):
        self.ollama.add("modelo")
        tracker = progress.Tracker()

        def on_prompt():
            if len(self.comfy.workflows) == 2:
                tracker.cancelled.set()

        self.comfy.on_prompt = on_prompt

        with progress.tracking(tracker):
            result = batch.run([{"prompt": f"p{n}"} for n in range(4)])

        lines = str(result).splitlines()
        self.assertRegex(lines[0], r"^1: .*\.png$")
        self.assertRegex(lines[1], r"^2: .*\.png$")
        self.assertEqual(lines[2], "3: ERROR: cancelled")
        self.assertEqual(lines[3], "4: ERROR: cancelled")
        self.assertEqual(len(self.outputs()), 2)
        self.assertIn("modelo", self.ollama.loaded)
        self.assertIsNone(state.read())
        self.assertEqual(self.comfy.models_loaded, 0)

    def test_cancel_before_start_generates_nothing(self):
        tracker = progress.Tracker()
        tracker.cancelled.set()

        with progress.tracking(tracker):
            result = batch.run([{"prompt": "a"}, {"prompt": "b"}])

        self.assertEqual(self.comfy.workflows, [])
        self.assertEqual(
            str(result).splitlines()[:2], ["1: ERROR: cancelled", "2: ERROR: cancelled"]
        )


class Unchanged(BatchCase):
    def test_create_image_still_returns_a_single_path(self):
        text = create_image("un gato")

        self.assertEqual(len(text.splitlines()), 1)
        self.assertTrue(Path(text).is_file())


class Tool(BatchCase):
    def call(self, **arguments):
        return asyncio.run(server.create_image(ctx=None, **arguments))

    def test_tool_returns_lines_in_order(self):
        text = self.call(prompt=["a", {"prompt": "b"}])

        self.assertEqual(len(text.splitlines()), 2)

    def test_rejection_is_an_error_of_the_tool(self):
        self.no_gpu()

        with self.assertRaisesRegex(ValueError, "Item 1"):
            self.call(prompt=[""])

    def test_single_prompt_keeps_its_format(self):
        text = self.call(prompt="a")

        self.assertEqual(len(text.splitlines()), 1)
        self.assertTrue(Path(text).is_file())

    def test_common_values_reach_every_prompt(self):
        reference = self.make_reference()

        text = self.call(prompt=["uno", "dos"], image_paths=[reference])

        self.assertEqual(len(text.splitlines()), 2)
        self.assertEqual(len(self.comfy.workflows), 2)

    def test_include_image_needs_a_single_prompt(self):
        with self.assertRaisesRegex(ValueError, "include_image"):
            self.call(prompt=["a", "b"], include_image=True)

    def test_there_is_only_one_image_tool(self):
        tools = server.mcp._tool_manager._tools

        self.assertIn("create_image", tools)
        self.assertNotIn("create_images", tools)
        self.assertIn("list of prompts", server.INSTRUCTIONS)
