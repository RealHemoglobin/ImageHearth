"""Política de versiones (fase 16): migraciones del registro de instalación y `update`."""

import json

import pytest

from imagehearth_mcp.engine import config
from imagehearth_mcp.provisioner import (
    ProvisionError,
    doctor,
    maintenance,
    manifest,
    migrations,
)
from imagehearth_mcp.provisioner import setup as setup_command
from imagehearth_mcp.provisioner.install_manifest import InstallManifest
from tests.test_provisioner import (  # noqa: F401
    machine,
    setup_args,
    update_args,
)

# Registros de esquema 1 como los dejó cada fase.
PHASE_9 = {
    "schema": 1,
    "mode": "managed",
    "comfy_dir": "/data/comfyui",
    "models_dir": "/data/comfyui/models",
    "comfyui_version": "0.43.0",
    "profile": "quality-gguf",
    "quality_model": "flux-dev",
    "precision": "gguf",
    "entries": [{"kind": "model", "path": "/data/comfyui/models/a.safetensors", "owned": True}],
    "settings": [{"key": "comfy_dir", "value": "/data/comfyui", "previous": None}],
    "connections": [
        {"client": "codex", "path": "/h/.codex/config.toml", "command": "x", "method": "file"}
    ],
}
PHASE_13 = {
    **PHASE_9,
    "profile": "full",
    "precision": "fp8",
    "edit_precision": "fp8",
    "install_dir": "/data",
    "legacy_quality": True,
}
PHASE_15 = {
    **PHASE_13,
    "models": {"fast": [{"model": "sdxl-turbo", "precision": "fp16"}]},
    "defaults": {"fast": "sdxl-turbo"},
}
PHASES = pytest.mark.parametrize(
    "values", [PHASE_9, PHASE_13, PHASE_15], ids=["phase9", "phase13", "phase15"]
)


def write(values):
    config.INSTALL_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    config.INSTALL_MANIFEST.write_text(json.dumps(values), encoding="utf-8")


@pytest.fixture
def current(monkeypatch):
    """Un esquema 2 simulado, con una migración que cambia un campo."""
    monkeypatch.setattr(migrations, "INSTALL_SCHEMA", 2)
    steps = []

    def one_to_two(values):
        steps.append(values["schema"])
        return {**values, "profile": "migrated"}

    monkeypatch.setattr(migrations, "MIGRATIONS", {1: one_to_two})
    return steps


@PHASES
def test_schema_1_records_of_every_phase_load_unchanged(machine, values):
    write(values)
    records = InstallManifest.load(config.INSTALL_MANIFEST)

    assert not records.needs_migration
    assert records.mode == "managed"
    assert records.entries == values["entries"]
    assert records.settings == values["settings"]
    assert records.connections == values["connections"]
    assert records.models == values.get("models", {})
    assert records.defaults == values.get("defaults", {})
    assert records.install_dir == values.get("install_dir")
    assert records.written_by is None

    records.save()
    saved = json.loads(config.INSTALL_MANIFEST.read_text(encoding="utf-8"))
    assert saved["schema"] == 1
    assert saved["imagehearth_version"] == migrations.package_version()
    assert saved["entries"] == values["entries"]
    assert not list(config.INSTALL_MANIFEST.parent.glob("install.json.bak-*"))


@PHASES
def test_schema_1_record_migrates_to_2_keeping_everything(machine, current, values):
    write(values)
    records = InstallManifest.load(config.INSTALL_MANIFEST)

    assert records.needs_migration
    assert records.migrated_from == 1
    assert current == [1]
    assert records.profile == "migrated"
    assert records.entries == values["entries"]
    assert records.connections == values["connections"]
    # Cargar migra en memoria: el archivo no cambia hasta guardar.
    assert json.loads(config.INSTALL_MANIFEST.read_text(encoding="utf-8")) == values


def test_saving_a_migrated_record_backs_up_the_old_one(machine, current):
    write(PHASE_15)
    before = config.INSTALL_MANIFEST.read_text(encoding="utf-8")
    records = InstallManifest.load(config.INSTALL_MANIFEST)
    records.save()
    records.save()

    backup = config.INSTALL_MANIFEST.with_name("install.json.bak-1")
    assert backup.read_text(encoding="utf-8") == before
    saved = json.loads(config.INSTALL_MANIFEST.read_text(encoding="utf-8"))
    assert saved["schema"] == 2
    assert not InstallManifest.load(config.INSTALL_MANIFEST).needs_migration
    assert current == [1]


def test_migrations_run_in_order(machine, monkeypatch):
    order = []
    monkeypatch.setattr(migrations, "INSTALL_SCHEMA", 3)
    monkeypatch.setattr(
        migrations,
        "MIGRATIONS",
        {1: lambda v: order.append(1) or v, 2: lambda v: order.append(2) or v},
    )
    write(PHASE_9)
    records = InstallManifest.load(config.INSTALL_MANIFEST)
    assert order == [1, 2]
    assert records.migrated_from == 1


def test_future_schema_is_refused_without_touching_anything(machine):
    write({**PHASE_15, "schema": 99})
    before = config.INSTALL_MANIFEST.read_text(encoding="utf-8")

    with pytest.raises(ProvisionError, match=r"newer ImageHearth.*Update ImageHearth"):
        InstallManifest.load(config.INSTALL_MANIFEST)

    with pytest.raises(ProvisionError, match="newer ImageHearth"):
        maintenance.update(update_args())

    assert config.INSTALL_MANIFEST.read_text(encoding="utf-8") == before
    assert not list(config.INSTALL_MANIFEST.parent.glob("install.json.*"))


@pytest.mark.parametrize("schema", [0, -1, "1", None, True, 1.5])
def test_garbage_schema_is_unknown(machine, schema):
    write({**PHASE_15, "schema": schema})

    with pytest.raises(ProvisionError, match="Unknown install record format"):
        InstallManifest.load(config.INSTALL_MANIFEST)


def test_missing_migration_is_an_error(machine, monkeypatch):
    monkeypatch.setattr(migrations, "INSTALL_SCHEMA", 2)
    monkeypatch.setattr(migrations, "MIGRATIONS", {})
    write(PHASE_9)

    with pytest.raises(ProvisionError, match="no migration"):
        InstallManifest.load(config.INSTALL_MANIFEST)


def test_update_migrates_without_downloading_or_deleting_models(machine, monkeypatch, capsys):
    setup_command.run(setup_args())
    weights = list((machine.data / "comfyui" / "models").rglob("*.safetensors"))
    assert weights
    machine.downloads.clear()

    monkeypatch.setattr(migrations, "INSTALL_SCHEMA", 2)
    monkeypatch.setattr(migrations, "MIGRATIONS", {1: dict})
    capsys.readouterr()

    assert maintenance.update(update_args()) == 0
    output = capsys.readouterr().out

    assert machine.downloads == []
    assert all(path.exists() for path in weights)
    assert "format 1 -> 2" in output
    assert "install.json.bak-1" in output
    assert config.INSTALL_MANIFEST.with_name("install.json.bak-1").exists()
    saved = json.loads(config.INSTALL_MANIFEST.read_text(encoding="utf-8"))
    assert saved["schema"] == 2


def test_update_shows_origin_and_destination(machine, capsys):
    setup_command.run(setup_args())
    records = InstallManifest.load(config.INSTALL_MANIFEST)
    records.comfyui_version = "0.0.0"
    records.save()
    capsys.readouterr()

    maintenance.update(update_args())
    output = capsys.readouterr().out
    version = migrations.package_version()

    assert f"ImageHearth: {version} -> {version}" in output
    assert f"ComfyUI: 0.0.0 -> {manifest.load().comfyui.version}" in output


def test_update_shows_what_changes_in_the_models(machine, capsys):
    setup_command.run(setup_args())
    weights = machine.data / "comfyui" / "models" / "checkpoints" / "sd_xl_turbo_1.0_fp16.safetensors"
    weights.unlink()
    capsys.readouterr()

    maintenance.update(update_args())
    assert "Models that change:" in capsys.readouterr().out


def test_update_with_nothing_to_change_downloads_nothing(machine, capsys):
    setup_command.run(setup_args())
    machine.downloads.clear()
    capsys.readouterr()

    assert maintenance.update(update_args()) == 0
    output = capsys.readouterr().out

    assert machine.downloads == []
    assert "Nothing to change." in output
    assert "Models: no changes." in output
    assert not list(config.INSTALL_MANIFEST.parent.glob("install.json.bak-*"))


def test_update_asks_before_changing_unless_yes(machine, monkeypatch):
    setup_command.run(setup_args())
    records = InstallManifest.load(config.INSTALL_MANIFEST)
    records.comfyui_version = "0.0.0"
    records.save()
    questions = []
    monkeypatch.setattr(maintenance, "is_interactive", lambda args: True)
    monkeypatch.setattr(maintenance.menu, "confirm", lambda text: questions.append(text) or False)

    with pytest.raises(ProvisionError, match="Nothing was changed"):
        maintenance.update(update_args(accept_licenses=False, non_interactive=False))

    assert questions == ["Apply these changes?"]
    assert InstallManifest.load(config.INSTALL_MANIFEST).comfyui_version == "0.0.0"

    questions.clear()
    assert maintenance.update(update_args(accept_licenses=False, non_interactive=False, yes=True)) == 0
    assert questions == []
    assert InstallManifest.load(config.INSTALL_MANIFEST).comfyui_version == manifest.load().comfyui.version


def test_record_remembers_the_version_that_wrote_it(machine):
    setup_command.run(setup_args())
    records = InstallManifest.load(config.INSTALL_MANIFEST)
    assert records.written_by == migrations.package_version()


def test_doctor_reports_a_record_that_needs_migration(machine, current):
    write(PHASE_15)
    checks = {check.layer: check for check in doctor.collect()}
    config_check = checks["config"]

    assert config_check.status == doctor.WARN
    assert "needs migrating" in config_check.message
    assert "imagehearth-mcp update" in config_check.fix
    assert config_check.details["install_record"] == {
        "schema": 1,
        "current_schema": 2,
        "needs_migration": True,
        "written_by": None,
    }
    payload = doctor.to_json(list(checks.values()))
    assert payload["schema"] == migrations.REPORT_SCHEMA
    assert json.dumps(payload)


def test_schemas_are_defined_in_one_place():
    from imagehearth_mcp.provisioner import move

    assert move.SCHEMA == migrations.MOVE_SCHEMA
