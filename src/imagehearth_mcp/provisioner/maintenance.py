"""Subcomandos `update` y `uninstall`, basados en el registro de lo instalado."""

import os
import shutil
import stat
import sys
from pathlib import Path

from imagehearth_mcp.engine import comfyui_manager, config
from imagehearth_mcp.platform import locks, processes
from imagehearth_mcp.provisioner import (
    ProvisionError,
    agent_scan,
    comfyui,
    connect,
    detect,
    manifest,
    menu,
    migrations,
    models,
    preflight,
    quality,
    settings,
)
from imagehearth_mcp.provisioner.install_manifest import InstallManifest
from imagehearth_mcp.provisioner.setup import (
    ATTACHED,
    is_interactive,
    show_summary,
)

STOP_TIMEOUT = 30
PLACEHOLDER_PREFIX = "put_"


def _show_changes(records, catalog, pending):
    """Dice de dónde viene y a dónde va la actualización. True si cambia algo."""
    current = migrations.package_version()
    origin = records.written_by or "a version before 1.0"
    target_comfy = catalog.comfyui.version
    changed = False

    print(f"ImageHearth: {origin} -> {current or 'unknown'}")

    if records.needs_migration:
        changed = True
        print(
            f"Install record: format {records.migrated_from} -> {migrations.INSTALL_SCHEMA} "
            f"(the old one is kept as {records.path.name}.bak-{records.migrated_from})"
        )

    if records.mode != ATTACHED:
        before = records.comfyui_version or "none"
        note = "" if before == target_comfy else "  (changes)"
        changed = changed or bool(note)
        print(f"ComfyUI: {before} -> {target_comfy}{note}")

    if pending:
        changed = True
        print("Models that change:")

        for item in pending:
            print(f"  {item.model.name} ({manifest.format_size(item.model.bytes)})")
    else:
        print("Models: no changes.")

    if not changed:
        print("Nothing to change.")

    return changed


def _update(args):
    if getattr(args, "move_to", None):
        from imagehearth_mcp.provisioner import move

        return move.relocate(args)

    records = InstallManifest.load(config.INSTALL_MANIFEST)

    if not records.mode:
        raise ProvisionError(
            "There is no installation to update. Run `imagehearth-mcp setup`."
        )

    catalog = manifest.load()
    comfy_dir = Path(records.comfy_dir)
    models_dir = Path(records.models_dir)
    profile = quality.resolve_installed(catalog, records, models_dir) or catalog.profiles["fast"]
    pending = [
        item
        for item in models.inspect(profile.models, models_dir)
        if item.state != models.PRESENT
    ]

    interactive = is_interactive(args)
    changes = _show_changes(records, catalog, pending)

    if (
        changes
        and not pending
        and not getattr(args, "yes", False)
        and not args.accept_licenses
        and interactive
        and not menu.confirm("Apply these changes?")
    ):
        raise ProvisionError("Nothing was changed.")

    if records.needs_migration:
        # Una sola escritura, con copia del registro anterior (`install.json.bak-<esquema>`).
        records.save()

    if pending:
        pending_bytes = sum(item.model.bytes for item in pending)
        show_summary(
            catalog,
            profile,
            records.mode,
            comfy_dir,
            models_dir,
            pending_bytes,
        )

        if not args.accept_licenses:
            if not interactive:
                raise ProvisionError(
                    "Nothing was changed. Non-interactive mode needs "
                    "--accept-licenses to download the models listed above."
                )

            if not menu.confirm("Accept these licenses and start downloading?"):
                raise ProvisionError("Nothing was changed.")

        issues = preflight.check_disk({models_dir: pending_bytes})

        if issues:
            raise ProvisionError("\n".join(issue.message for issue in issues))

    if records.mode == ATTACHED:
        # De un ComfyUI ajeno solo se actualiza el nodo, y solo si es propio.
        comfyui.install_node(comfy_dir, records, allowed=False)
    else:
        platform = detect.detect(disk_path=comfy_dir).platform
        torch = catalog.pytorch.get(platform.index)

        if comfyui_manager.managed_pid() is not None and (
            records.comfyui_version != catalog.comfyui.version
        ):
            raise ProvisionError(
                "ComfyUI is running. Stop your agent's generation and close ComfyUI "
                "before updating it."
            )

        comfyui.install_managed(catalog.comfyui, torch, comfy_dir, records)

    for node in profile.nodes:
        # Sin permiso para un ComfyUI ajeno: solo se actualiza el nodo propio.
        comfyui.install_custom_node(
            node, comfy_dir, records, allowed=records.mode != ATTACHED
        )

    models.ensure_models(profile.models, models_dir, records)
    print(f"Up to date: ComfyUI {records.comfyui_version or 'attached'}, profile {profile.name}.")
    return 0


def _force_remove(function, path, _error):
    # En Windows, los archivos de solo lectura no se dejan borrar.
    os.chmod(path, stat.S_IWRITE)
    function(path)


def _remove(path):
    path = Path(path)

    if not path.exists() and not path.is_symlink():
        return

    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, onexc=_force_remove)
    else:
        path.unlink()


def _is_safe(path):
    """Una entrada dañada del registro nunca debe llevarse la carpeta del usuario."""
    path = Path(path).absolute()
    protected = {Path.home().absolute(), Path(path.anchor), config.DATA_DIR.absolute()}
    return path not in protected and path not in Path.home().absolute().parents


def _remove_comfy_dir(path):
    """Borra el ComfyUI propio salvo `models`, que tiene su propia confirmación."""
    if not path.exists():
        return

    for item in path.iterdir():
        if item.name != "models":
            _remove(item)


def _is_shipped_config(item, models_dir):
    """Los `models/configs/*.yaml` vienen con el código de ComfyUI: no son de nadie más."""
    relative = item.relative_to(models_dir).parts
    return len(relative) == 2 and relative[0] == "configs" and item.suffix == ".yaml"


def _prune_models_dir(path):
    """Borra la carpeta de modelos solo si quedan únicamente carpetas y marcadores."""
    if not path.is_dir():
        return

    leftovers = [
        item
        for item in path.rglob("*")
        if item.is_file()
        and not item.name.startswith(PLACEHOLDER_PREFIX)
        and not _is_shipped_config(item, path)
    ]

    if not leftovers:
        _remove(path)


def _prune_install_dir(records, install_dir=None):
    """Borra la carpeta de instalación y las que setup creó hasta ella, solo si quedan vacías.

    `install_dir`: otra carpeta que ya no es la actual (tras un traslado).
    """
    folder = install_dir or records.install_dir
    path = Path(folder) if folder else None
    entry = next(
        (
            e
            for e in records.owned("install_dir")
            if path is not None and Path(e["path"]) in (path, *path.parents)
        ),
        None,
    )

    if entry is None:
        return

    top = Path(entry["path"])

    if not _is_safe(top):
        return

    while path.is_dir() and not any(path.iterdir()):
        path.rmdir()

        if path == top:
            break

        path = path.parent

    if not top.exists():
        records.forget(top)

        if install_dir is None:
            records.install_dir = None


def _stop_managed():
    pid = comfyui_manager.managed_pid()

    if pid is None:
        return

    print(f"Stopping the ComfyUI started by ImageHearth (pid {pid})...")

    if not processes.terminate(pid, STOP_TIMEOUT):
        processes.kill(pid)

    config.PID_FILE.unlink(missing_ok=True)


def _decide_models(args, owned_models, interactive):
    if not owned_models or args.keep_models:
        return False

    if args.remove_models:
        return True

    if not interactive:
        return False

    size = sum(
        Path(entry["path"]).stat().st_size
        for entry in owned_models
        if Path(entry["path"]).exists()
    )
    return menu.confirm(
        f"Also remove the {len(owned_models)} downloaded models "
        f"({manifest.format_size(size)})?"
    )


def _uninstall(args):
    records = InstallManifest.load(config.INSTALL_MANIFEST)

    if config.MOVE_STATE.exists():
        raise ProvisionError(
            "A move to another folder was interrupted. Nothing was removed: finish it with "
            "`imagehearth-mcp update --move-to` (the same folder), or cancel it with "
            "`update --move-to` and the current folder, and then run uninstall."
        )

    # Sin registro, ImageHearth puede seguir en los agentes: se buscan igualmente.
    if not records.exists and agent_scan.scan(records).empty:
        print("No install record found: nothing was removed.")
        return 0

    interactive = sys.stdin.isatty()
    owned = records.owned("comfyui", "node", "config", "staging", "cache")
    owned_models = records.owned("model")

    print("Will remove:")

    for entry in owned:
        note = " (keeping its models folder)" if entry["kind"] == "comfyui" else ""
        print(f"  {entry['path']}{note}")

    for setting in records.settings:
        print(f"  {setting['key']} in {config.CONFIG_FILE} (restoring the previous value)")

    for connection in records.connections:
        print(f"  The ImageHearth entry of {connection['client']} ({connection['path']})")

    for entry in records.owned("install_dir"):
        print(f"  {entry['path']} (the install folder, only if it ends up empty)")

    print("  Any other ImageHearth entry or skill in your agents (it asks first, or use --yes)")

    if not owned and not records.settings and not records.connections:
        print("  Nothing besides, optionally, the downloaded models.")

    print("Will not touch anything setup did not install.")

    if not args.yes:
        if not interactive:
            raise ProvisionError(
                "Nothing was removed. Non-interactive mode needs --yes."
            )

        if not menu.confirm("Continue?"):
            print("Nothing was removed.")
            return 0

    remove_models = _decide_models(args, owned_models, interactive)

    if records.exists:
        _stop_managed()

    failures = []

    def attempt(entry, remover):
        path = Path(entry["path"])

        if not _is_safe(path):
            failures.append(f"{path}: refused, it is a protected folder")
            return

        try:
            remover(path)
        except OSError as error:
            failures.append(f"{path}: {error}")
        else:
            records.forget(path)
            records.save()

    for entry in owned_models if remove_models else ():
        attempt(entry, _remove)

    for entry in owned:
        attempt(entry, _remove_comfy_dir if entry["kind"] == "comfyui" else _remove)

    report = connect.disconnect_all(records, args.yes, interactive)
    failures.extend(report.failures)
    connect.print_report(report)

    if not failures:
        try:
            settings.restore(config.CONFIG_FILE, records)
        except ProvisionError as error:
            failures.append(str(error))

    for entry in owned:
        if entry["kind"] != "comfyui":
            continue

        comfy_dir = Path(entry["path"])

        _prune_models_dir(comfy_dir / "models")

        if comfy_dir.is_dir() and not any(comfy_dir.iterdir()):
            comfy_dir.rmdir()

    if not failures:
        _prune_install_dir(records)

    if failures:
        records.save()
        print("Could not remove (close any program using them and run uninstall again):")

        for failure in failures:
            print(f"  {failure}")

        return 1

    for entry in records.owned("settings_file"):
        path = Path(entry["path"])

        # Si el usuario ha añadido algo, el archivo ya es suyo.
        if path.exists() and not path.read_text(encoding="utf-8").strip():
            path.unlink()

        records.forget(path)

    # `setup_status` no debe informar de una instalación que ya no existe.
    config.SETUP_JOB_FILE.unlink(missing_ok=True)
    kept = records.owned("model")

    if kept:
        records.mode = None
        records.comfyui_version = None
        records.save()
        print(f"Removed. Kept {len(kept)} downloaded models in {records.models_dir}.")
    else:
        config.INSTALL_MANIFEST.unlink(missing_ok=True)
        print("Removed.")

    print("To remove the program itself, run `uv tool uninstall imagehearth-mcp`.")
    return 0


def _locked(function, args):
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)

    try:
        with locks.held(config.SETUP_LOCK, timeout=1):
            return function(args)
    except TimeoutError:
        raise ProvisionError(
            "Another setup, update or uninstall is running. Wait for it to finish."
        ) from None


def update(args):
    return _locked(_update, args)


def uninstall(args):
    return _locked(_uninstall, args)
