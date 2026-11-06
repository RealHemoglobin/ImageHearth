"""Registro de lo instalado: lo único que `uninstall` puede llegar a borrar.

Cada ruta se anota como propia solo si no existía al reclamarla, y una entrada
ya registrada no cambia: lo preexistente nunca pasa a ser propio.
"""

import json
import os
from pathlib import Path

from imagehearth_mcp.platform import files
from imagehearth_mcp.provisioner import ProvisionError

SCHEMA = 1


def _normal(path):
    return os.path.abspath(path)


class InstallManifest:
    def __init__(self, path, values=None):
        self.path = Path(path)
        values = values or {}
        self.mode = values.get("mode")
        self.comfy_dir = values.get("comfy_dir")
        self.models_dir = values.get("models_dir")
        self.comfyui_version = values.get("comfyui_version")
        self.profile = values.get("profile")
        # Model of the quality profile and the precision installed. Missing in records
        # from before phase 9: `quality.current` deduces the model from the files.
        self.quality_model = values.get("quality_model")
        self.precision = values.get("precision")
        self.edit_precision = values.get("edit_precision")
        self._normalize_legacy_profile()
        self.entries = values.get("entries", [])
        self.settings = values.get("settings", [])
        self.connections = values.get("connections", [])

    def _normalize_legacy_profile(self):
        """Records used to name the variant (quality-gguf); now profile and precision apart."""
        for suffix, precision in (("-gguf", "gguf"), ("-sdxl", None)):
            base = (self.profile or "").removesuffix(suffix)

            if base in ("quality", "full") and base != self.profile:
                self.profile = base
                self.precision = self.precision or precision
                self.edit_precision = self.edit_precision or (
                    precision if base == "full" else None
                )
                return

    @classmethod
    def load(cls, path):
        path = Path(path)

        try:
            values = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return cls(path)
        except (OSError, ValueError) as error:
            raise ProvisionError(
                f"Can't read the install record {path}: {error}. Nothing was changed."
            ) from error

        if not isinstance(values, dict) or values.get("schema") != SCHEMA:
            raise ProvisionError(
                f"Unknown install record format in {path}. Nothing was changed."
            )

        return cls(path, values)

    @property
    def exists(self):
        return self.path.exists()

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {
                    "schema": SCHEMA,
                    "mode": self.mode,
                    "comfy_dir": self.comfy_dir,
                    "models_dir": self.models_dir,
                    "comfyui_version": self.comfyui_version,
                    "profile": self.profile,
                    "quality_model": self.quality_model,
                    "precision": self.precision,
                    "edit_precision": self.edit_precision,
                    "entries": self.entries,
                    "settings": self.settings,
                    "connections": self.connections,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        files.replace(temporary, self.path)

    def entry(self, path):
        normal = _normal(path)
        return next((e for e in self.entries if e["path"] == normal), None)

    def _record(self, kind, path, owned):
        if self.entry(path) is None:
            self.entries.append({"kind": kind, "path": _normal(path), "owned": owned})
            self.save()

    def claim(self, kind, path):
        """Llamar justo antes de crear `path`: será propio solo si aún no existe."""
        self._record(kind, path, not Path(path).exists())

    def claim_verified(self, kind, path):
        """Como `claim`, cuando quien llama ya ha comprobado que nada es ajeno."""
        self._record(kind, path, True)

    def note_preexisting(self, kind, path):
        self._record(kind, path, False)

    def is_owned(self, path):
        entry = self.entry(path)
        return entry is not None and entry["owned"]

    def owned(self, *kinds):
        return [
            entry
            for entry in self.entries
            if entry["owned"] and (not kinds or entry["kind"] in kinds)
        ]

    def forget(self, path):
        normal = _normal(path)
        self.entries = [e for e in self.entries if e["path"] != normal]

    def record_setting(self, key, value, previous):
        for setting in self.settings:
            if setting["key"] == key:
                setting["value"] = value
                break
        else:
            self.settings.append({"key": key, "value": value, "previous": previous})

        self.save()
