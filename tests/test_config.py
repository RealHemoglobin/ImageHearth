import importlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from imagehearth_mcp.engine import config

ENV_KEYS = (
    "IMAGEHEARTH_CONFIG_FILE",
    "IMAGEHEARTH_COMFY_DIR",
    "IMAGEHEARTH_COMFY_PORT",
    "IMAGEHEARTH_OUTPUT_DIR",
    "IMAGEHEARTH_OLLAMA_URL",
    "IMAGEHEARTH_OLLAMA_MODE",
)


class ConfigLoading(unittest.TestCase):
    """Recarga config.py con un entorno y un config.toml controlados."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="imagehearth-test-config-"))
        self.addCleanup(subprocess.run, ["rm", "-rf", str(self.tmp)])
        self.addCleanup(importlib.reload, config)

    def load(self, toml=None, **env):
        path = self.tmp / "config.toml"

        if toml is not None:
            path.write_text(toml, encoding="utf-8")

        clean = {k: v for k, v in os.environ.items() if k not in ENV_KEYS}
        clean["IMAGEHEARTH_CONFIG_FILE"] = str(path)
        clean.update(env)

        with mock.patch.dict(os.environ, clean, clear=True):
            return importlib.reload(config)

    def test_defaults(self):
        loaded = self.load()
        self.assertEqual(loaded.COMFY_PORT, 8188)
        self.assertEqual(loaded.OLLAMA_API, "http://127.0.0.1:11434")
        self.assertEqual(loaded.COMFY_DIR, loaded.DATA_DIR / "comfyui")
        self.assertEqual(loaded.OUTPUT_DIR, Path.home() / "Pictures" / "ImageHearth")

    def test_file_overrides_default_and_expands_home(self):
        loaded = self.load('comfy_dir = "~/AI/ComfyUI"\ncomfy_port = 9000\n')
        self.assertEqual(loaded.COMFY_DIR, Path.home() / "AI" / "ComfyUI")
        self.assertEqual(loaded.COMFY_PORT, 9000)
        self.assertEqual(loaded.COMFY_API, "http://127.0.0.1:9000")

    def test_environment_overrides_file(self):
        loaded = self.load(
            'comfy_port = 9000\noutput_dir = "/from/file"\n',
            IMAGEHEARTH_COMFY_PORT="9100",
            IMAGEHEARTH_OUTPUT_DIR="/from/env",
        )
        self.assertEqual(loaded.COMFY_PORT, 9100)
        self.assertEqual(loaded.OUTPUT_DIR, Path("/from/env"))

    def test_ollama_mode(self):
        self.assertEqual(self.load().OLLAMA_MODE, "auto")
        self.assertEqual(self.load('ollama_mode = "off"\n').OLLAMA_MODE, "off")
        self.assertEqual(
            self.load('ollama_mode = "off"\n', IMAGEHEARTH_OLLAMA_MODE="auto").OLLAMA_MODE,
            "auto",
        )

    def test_invalid_ollama_mode_names_its_source(self):
        with self.assertRaisesRegex(RuntimeError, "IMAGEHEARTH_OLLAMA_MODE"):
            self.load(IMAGEHEARTH_OLLAMA_MODE="maybe")

        with self.assertRaisesRegex(RuntimeError, "ollama_mode"):
            self.load('ollama_mode = "on"\n')

    def test_ollama_url(self):
        loaded = self.load('ollama_url = "http://host:1234/"\n')
        self.assertEqual(loaded.OLLAMA_API, "http://host:1234")

    def test_invalid_toml_names_the_file(self):
        with self.assertRaisesRegex(RuntimeError, "config.toml"):
            self.load("esto no es [toml")

    def test_non_numeric_port_names_the_variable(self):
        with self.assertRaisesRegex(RuntimeError, "IMAGEHEARTH_COMFY_PORT"):
            self.load(IMAGEHEARTH_COMFY_PORT="abc")

    def test_invalid_port_in_file_names_the_key(self):
        with self.assertRaisesRegex(RuntimeError, "comfy_port"):
            self.load('comfy_port = "x"\n')

    def test_non_numeric_timeout_names_the_variable(self):
        with self.assertRaisesRegex(RuntimeError, "IMAGEHEARTH_LOCK_TIMEOUT"):
            self.load(IMAGEHEARTH_LOCK_TIMEOUT="x")


class ImportHasNoSideEffects(unittest.TestCase):
    def test_import_writes_nothing(self):
        home = Path(tempfile.mkdtemp(prefix="imagehearth-test-home-"))
        self.addCleanup(subprocess.run, ["rm", "-rf", str(home)])

        env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith(("IMAGEHEARTH_", "XDG_"))
        }
        env["HOME"] = str(home)

        code = (
            "import imagehearth_mcp.server, imagehearth_mcp.engine.status"
        )
        subprocess.run([sys.executable, "-c", code], env=env, check=True)

        self.assertEqual(list(home.rglob("*")), [])


class PackageData(unittest.TestCase):
    def test_workflows_resolve_from_the_package(self):
        names = {path.name for path in config.WORKFLOWS_DIR.glob("*.json")}
        self.assertEqual(
            names,
            {"sdxl_turbo.json", "flux_dev.json", "flux_kontext_dev_basic.json"},
        )

    def test_skill_and_node_resolve_from_the_package(self):
        data = config.data_files()
        self.assertIn("name: imagehearth", (data / "skill" / "SKILL.md").read_text())
        self.assertTrue((data / "imagehearth_status" / "__init__.py").is_file())
        self.assertTrue((data / "imagehearth_status" / "LICENSE").is_file())

    def test_skill_has_no_personal_paths(self):
        text = (config.data_files() / "skill" / "SKILL.md").read_text()
        self.assertNotIn("~/AI/", text)
