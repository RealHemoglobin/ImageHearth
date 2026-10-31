import json
import os
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import requests

from imagehearth_mcp.engine import comfyui_manager, config, gpu
from imagehearth_mcp.platform import files, locks, paths, processes, spawn
from tests.harness import EngineTestCase


class Locks(unittest.TestCase):
    def setUp(self):
        import tempfile

        self.path = Path(tempfile.mkdtemp(prefix="imagehearth-test-lock-")) / "a.lock"

    def test_second_holder_times_out(self):
        with locks.held(self.path, timeout=1):
            self.assertTrue(locks.is_locked(self.path))

            with self.assertRaises(TimeoutError):
                locks.acquire(self.path, timeout=0.1, poll=0.01)

        self.assertFalse(locks.is_locked(self.path))

    def test_waiter_announces_once_and_gets_the_lock(self):
        announced = []
        release = threading.Event()
        started = threading.Event()

        def hold():
            with locks.held(self.path, timeout=1):
                started.set()
                release.wait(5)

        thread = threading.Thread(target=hold)
        thread.start()
        started.wait(5)
        threading.Timer(0.1, release.set).start()

        with locks.held(self.path, 5, on_wait=lambda: announced.append(1)):
            pass

        thread.join()
        self.assertEqual(announced, [1])

    def test_lock_is_released_when_the_holder_process_dies(self):
        holder = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "; ".join(
                    [
                        "import pathlib, time",
                        "from imagehearth_mcp.platform import locks",
                        f"l = locks.acquire(pathlib.Path({str(self.path)!r}), 5)",
                        "print('held', flush=True)",
                        "time.sleep(60)",
                    ]
                )
            ],
            stdout=subprocess.PIPE,
            text=True,
        )
        self.addCleanup(holder.kill)
        self.assertEqual(holder.stdout.readline().strip(), "held")
        self.assertTrue(locks.is_locked(self.path))

        holder.kill()
        holder.wait()

        self.assertFalse(locks.is_locked(self.path))


class Processes(unittest.TestCase):
    def test_current_process_is_found_by_script_and_cwd(self):
        process = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)", "main.py"],
            cwd=Path.cwd(),
        )
        self.addCleanup(process.kill)
        time.sleep(0.3)

        self.assertIn(process.pid, processes.find_by_cwd_and_script(Path.cwd(), "main.py"))
        self.assertNotIn(
            process.pid, processes.find_by_cwd_and_script(Path.cwd() / "x", "main.py")
        )

    def test_reused_pid_is_not_the_same_process(self):
        created = processes.create_time(os.getpid())

        self.assertTrue(processes.is_same_process(os.getpid(), created))
        self.assertFalse(processes.is_same_process(os.getpid(), created - 100))
        self.assertFalse(processes.is_same_process(os.getpid(), None))

    def test_terminate_and_kill(self):
        for stop in (lambda pid: processes.terminate(pid, 10), processes.kill):
            process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
            self.addCleanup(process.kill)

            self.assertTrue(stop(process.pid))
            process.wait(timeout=10)
            self.assertIsNone(processes.create_time(process.pid))

    def test_missing_process_counts_as_terminated(self):
        self.assertTrue(processes.terminate(2**22 + 12345, 1))


class Paths(unittest.TestCase):
    def test_venv_python_per_system(self):
        venv = Path("v")

        with mock.patch.object(sys, "platform", "linux"):
            self.assertEqual(paths.venv_python(venv), venv / "bin" / "python")

        with mock.patch.object(sys, "platform", "win32"):
            self.assertEqual(paths.venv_python(venv), venv / "Scripts" / "python.exe")

    def test_detached_options_per_system(self):
        with mock.patch.object(sys, "platform", "linux"):
            self.assertTrue(spawn.detached_options()["start_new_session"])

        with (
            mock.patch.object(sys, "platform", "win32"),
            mock.patch.object(subprocess, "CREATE_NEW_PROCESS_GROUP", 512, create=True),
            mock.patch.object(subprocess, "DETACHED_PROCESS", 8, create=True),
        ):
            self.assertEqual(spawn.detached_options(), {"creationflags": 520})


class Replace(unittest.TestCase):
    def test_retries_transient_permission_errors(self):
        calls = []

        def flaky(source, destination):
            calls.append(1)

            if len(calls) < 3:
                raise PermissionError

        with mock.patch("os.replace", side_effect=flaky):
            files.replace("a", "b", delay=0)

        self.assertEqual(len(calls), 3)

    def test_gives_up_after_the_last_attempt(self):
        with (
            mock.patch("os.replace", side_effect=PermissionError) as replace,
            self.assertRaises(PermissionError),
        ):
            files.replace("a", "b", attempts=3, delay=0)

        self.assertEqual(replace.call_count, 3)


class GpuMemory(EngineTestCase):
    def test_prefers_comfyui_system_stats(self):
        self.comfy.vram_free = 1234

        self.assertEqual(gpu.free_mib(), 1234)
        self.gpu_free.assert_not_called()

    def test_falls_back_to_nvidia_smi(self):
        self.assertEqual(gpu.free_mib(), 20000)

    def test_unknown_when_nothing_answers(self):
        self.gpu_free.side_effect = OSError

        self.assertIsNone(gpu.free_mib())

    def test_cpu_device_is_ignored(self):
        self.comfy.vram_free = 5

        with mock.patch.object(
            requests, "get", return_value=mock.Mock(
                raise_for_status=lambda: None,
                json=lambda: {"devices": [{"type": "cpu", "vram_free": 9}]},
            )
        ):
            self.assertEqual(gpu.free_mib(), 20000)


class ManagedInstance(EngineTestCase):
    def register(self, pid, create_time):
        config.PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        config.PID_FILE.write_text(
            json.dumps({"pid": pid, "create_time": create_time}), encoding="utf-8"
        )

    def test_no_registry_means_no_managed_instance(self):
        self.assertIsNone(comfyui_manager.managed_pid())

    def test_registered_live_process_is_managed(self):
        self.register(os.getpid(), processes.create_time(os.getpid()))

        self.assertEqual(comfyui_manager.managed_pid(), os.getpid())

    def test_reused_pid_clears_the_registry(self):
        self.register(os.getpid(), processes.create_time(os.getpid()) - 1000)

        self.assertIsNone(comfyui_manager.managed_pid())
        self.assertFalse(config.PID_FILE.exists())

    def test_dead_process_clears_the_registry(self):
        self.register(2**22 + 999, 1.0)

        self.assertIsNone(comfyui_manager.managed_pid())
        self.assertFalse(config.PID_FILE.exists())

    def test_corrupt_registry_is_discarded(self):
        config.PID_FILE.parent.mkdir(parents=True)
        config.PID_FILE.write_text("{roto", encoding="utf-8")

        self.assertIsNone(comfyui_manager.managed_pid())
        self.assertFalse(config.PID_FILE.exists())

    def test_foreign_instance_is_never_stopped_or_restarted(self):
        with (
            mock.patch.object(processes, "terminate") as terminate,
            mock.patch.object(processes, "kill") as kill,
            mock.patch.object(comfyui_manager, "start") as start,
            self.assertRaisesRegex(RuntimeError, "not started by ImageHearth"),
        ):
            comfyui_manager.restart()

        terminate.assert_not_called()
        kill.assert_not_called()
        start.assert_not_called()

    def test_restart_stops_only_the_registered_pid(self):
        self.register(os.getpid(), processes.create_time(os.getpid()))
        stopped = []

        with (
            mock.patch.object(
                processes, "terminate", side_effect=lambda pid, t: stopped.append(pid) or True
            ),
            mock.patch.object(comfyui_manager, "port_is_open", return_value=False),
            mock.patch.object(comfyui_manager, "start") as start,
        ):
            comfyui_manager.restart()

        self.assertEqual(stopped, [os.getpid()])
        self.assertFalse(config.PID_FILE.exists())
        start.assert_called_once()

    def test_status_reports_whether_the_instance_is_managed(self):
        from imagehearth_mcp.engine.status import get_status

        self.assertFalse(get_status()["comfyui"]["managed"])
