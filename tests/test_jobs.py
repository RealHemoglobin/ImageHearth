"""Image jobs: a generation outlives the call that waits for it and is always reported truthfully."""

import asyncio
import json
import time
from unittest import mock

from imagehearth_mcp import server
from imagehearth_mcp.engine import config, jobs, state
from imagehearth_mcp.engine.status import get_status
from tests.harness import EngineTestCase


def call(coroutine):
    return asyncio.run(coroutine)


class SlowGeneration(EngineTestCase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(config, "JOB_WAIT_SECONDS", 0.3)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.comfy.on_prompt = lambda: time.sleep(0.8)

    def test_a_slow_image_is_reported_as_running_not_failed(self):
        text = call(server.create_image("a cat"))

        self.assertTrue(text.startswith("RUNNING: image job "))
        self.assertIn("NOT failed", text)
        self.assertIn("get_image_job", text)
        job = jobs.get()
        self.assertIn(job.id, text)
        self.assertTrue(job.done.wait(5))

    def test_get_image_job_returns_the_result_once_it_finishes(self):
        text = call(server.create_image("a cat"))
        job_id = text.split()[3]

        result = ""
        for _ in range(20):
            result = call(server.get_image_job(job_id))

            if not result.startswith("RUNNING"):
                break

        self.assertTrue(result.splitlines()[0].endswith(".png"))
        self.assertEqual(len(self.comfy.workflows), 1)
        self.assertIsNone(state.read())

    def test_without_an_id_it_shows_the_latest_job(self):
        call(server.create_image("a cat"))
        jobs.get().done.wait(5)

        self.assertTrue(call(server.get_image_job()).splitlines()[0].endswith(".png"))

    def test_status_lists_the_running_job(self):
        call(server.create_image("a cat"))
        status = get_status()["imageengine"]

        self.assertEqual(status["status"], "busy")
        self.assertEqual(status["jobs"][0]["id"], jobs.get().id)
        self.assertTrue(jobs.get().done.wait(5))
        self.assertNotIn("jobs", get_status()["imageengine"])

    def test_a_batch_also_runs_on(self):
        text = call(server.create_image(["a cat", "a dog"]))

        self.assertTrue(text.startswith("RUNNING:"))
        job = jobs.get()
        self.assertTrue(job.done.wait(10))
        self.assertEqual(len(call(server.get_image_job(job.id)).splitlines()), 2)

    def test_include_image_asked_at_creation_is_kept(self):
        call(server.create_image("a cat", include_image=True))
        jobs.get().done.wait(5)

        text, image = call(server.get_image_job())
        self.assertTrue(text.splitlines()[0].endswith(".png"))
        self.assertEqual(image.to_image_content().mimeType, "image/jpeg")


class Failures(EngineTestCase):
    def test_a_failed_job_raises_its_error(self):
        with self.assertRaisesRegex(ValueError, "prompt"):
            call(server.create_image(""))

        job = jobs.get()
        self.assertEqual(job.status, jobs.FAILED)

        with self.assertRaisesRegex(ValueError, "prompt"):
            call(server.get_image_job(job.id))

    def test_unknown_job_names_the_known_ones(self):
        call(server.create_image("a cat"))

        with self.assertRaisesRegex(ValueError, "no image job 'nope'.*" + jobs.get().id):
            call(server.get_image_job("nope"))

    def test_no_jobs_at_all(self):
        with self.assertRaisesRegex(ValueError, "Known jobs: none"):
            call(server.get_image_job())

    def test_cancel_of_a_finished_job_says_so(self):
        call(server.create_image("a cat"))

        self.assertIn("is not running", call(server.cancel_image_job()))


class Persistence(EngineTestCase):
    def test_a_job_of_a_dead_server_is_interrupted_not_unknown(self):
        config.JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)
        config.JOBS_FILE.write_text(
            json.dumps(
                {
                    "dead0001": {
                        "id": "dead0001",
                        "kind": "single",
                        "status": "running",
                        "stage": "Generating the image",
                        "started": time.time() - 70,
                        "pid": 2**22 + 12345,
                        "created": 1.0,
                    }
                }
            )
        )

        with self.assertRaisesRegex(RuntimeError, "interrupted.*recover_engine"):
            call(server.get_image_job("dead0001"))

        self.assertEqual(jobs.active(), [])

    def test_finished_jobs_are_readable_by_another_process(self):
        call(server.create_image("a cat"))
        job = jobs.get()
        jobs._jobs.clear()

        self.assertEqual(jobs.get(job.id).status, jobs.COMPLETED)
        self.assertTrue(call(server.get_image_job(job.id)).splitlines()[0].endswith(".png"))


class Status(EngineTestCase):
    def test_an_interrupted_session_explains_itself(self):
        state.write(phase=state.RELEASING, models=[], run_id="x", prompt_id=None, reason=None)

        session = get_status()["imageengine"]["session"]

        self.assertIn("interrupted while releasing", session["reason"])
        self.assertIn("recover_engine", session["reason"])
