"""`update --move-to`: traslada el ComfyUI gestionado y los modelos propios a otra carpeta.

El orden protege la instalación. En el mismo disco se renombra. En otro disco se copia,
se verifica y se crea el entorno de Python de nuevo; hasta el cambio de rutas,
`install.json` y `config.toml` apuntan al origen, que sigue entero. Un traslado
interrumpido se repite con el mismo comando: `move.json` recuerda lo ya verificado.
"""

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from imagehearth_mcp.engine import config
from imagehearth_mcp.engine import state as session
from imagehearth_mcp.platform import files, locks, paths
from imagehearth_mcp.provisioner import (
    ProvisionError,
    agent_setup,
    comfyui,
    detect,
    locations,
    manifest,
    menu,
    migrations,
    models,
    preflight,
    quality,
    settings,
)
from imagehearth_mcp.provisioner.install_manifest import InstallManifest
from imagehearth_mcp.provisioner.manifest import format_size

SCHEMA = migrations.MOVE_SCHEMA
COPY_CHUNK = 8 * 1024 * 1024
TEMP_SUFFIX = ".imagehearth-move"
# Entre dos escrituras de `move.json` se copian como mucho tantos archivos pequeños.
SAVE_EVERY = 200
BIG_FILE = 100 * 1024 * 1024
# Lo que no se traslada: el entorno se crea de nuevo y las descargas a medias se repiten.
SKIP = ("venv", f"models/{models.STAGING_DIR}")

FILE = "file"
DIR = "dir"
LINK = "link"


def _normal(path):
    return os.path.normcase(os.path.abspath(path))


def _is_inside(path, folder):
    path, folder = _normal(path), _normal(folder)
    return path == folder or path.startswith(folder + os.sep)


def _same_device(source, destination):
    """True si renombrar basta: los dos están en el mismo sistema de archivos."""
    try:
        return (
            os.stat(locations.nearest_existing(source)).st_dev
            == os.stat(locations.nearest_existing(destination)).st_dev
        )
    except OSError:
        return False


@dataclass
class State:
    """Lo que `move.json` recuerda de un traslado a medias."""

    path: Path
    source: str = ""
    destination: str = ""
    previous: str = ""
    roots: list = field(default_factory=list)
    verified: list = field(default_factory=list)
    created: list = field(default_factory=list)
    venv: bool = False

    @classmethod
    def load(cls, path):
        path = Path(path)

        try:
            values = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as error:
            raise ProvisionError(
                f"Can't read {path}: {error}. If no move is under way, delete that file."
            ) from error

        if not isinstance(values, dict) or values.get("schema") != SCHEMA:
            raise ProvisionError(f"Unknown move record format in {path}.")

        return cls(
            path,
            values.get("source", ""),
            values.get("destination", ""),
            values.get("previous", ""),
            [list(pair) for pair in values.get("roots", [])],
            [list(pair) for pair in values.get("verified", [])],
            list(values.get("created", [])),
            bool(values.get("venv", False)),
        )

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {
                    "schema": SCHEMA,
                    "source": self.source,
                    "destination": self.destination,
                    "previous": self.previous,
                    "roots": self.roots,
                    "verified": self.verified,
                    "created": self.created,
                    "venv": self.venv,
                    "updated_at": time.time(),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        files.replace(temporary, self.path)

    def delete(self):
        self.path.unlink(missing_ok=True)


@dataclass
class Tree:
    """Un árbol que se traslada de `source` a `destination`.

    `only`: si no es None, solo esos archivos (los modelos propios de una carpeta ajena).
    """

    source: Path
    destination: Path
    skip: tuple = ()
    only: frozenset | None = None
    same_device: bool = False
    entries: list = field(default_factory=list)

    @property
    def total(self):
        return sum(size for kind, _, size in self.entries if kind == FILE)

    @property
    def count(self):
        return sum(1 for kind, _, _ in self.entries if kind == FILE)


@dataclass
class Plan:
    install_dir: Path
    current_dir: Path
    source_comfy: Path
    new_comfy: Path
    source_models: Path
    new_models: Path
    models_inside: bool
    trees: list
    kept_behind: list

    @property
    def comfy(self):
        return self.trees[0]

    @property
    def same_device(self):
        return all(tree.same_device for tree in self.trees)


def walk(root, skip=(), only=None):
    """Entradas (tipo, ruta relativa en posix, tamaño) bajo `root`, sin entrar en enlaces."""
    root = Path(root)
    found = []

    for directory, names, filenames in os.walk(root, followlinks=False):
        here = Path(directory)
        relative = here.relative_to(root)
        kept = []

        for name in names:
            rel = (relative / name).as_posix()

            if rel in skip:
                continue

            if (here / name).is_symlink():
                if only is None:
                    found.append((LINK, rel, 0))
            else:
                kept.append(name)

                if only is None:
                    found.append((DIR, rel, 0))

        names[:] = kept

        for name in filenames:
            rel = (relative / name).as_posix()
            path = here / name

            if rel in skip:
                continue

            if path.is_symlink():
                if only is None:
                    found.append((LINK, rel, 0))
            elif only is None or rel in only:
                found.append((FILE, rel, path.stat().st_size))

    return found


def _relative(path, root):
    return Path(os.path.relpath(path, root)).as_posix()


def _model_files(folder):
    """Archivos de modelos de una carpeta: sin marcadores de ComfyUI ni descargas a medias."""
    if not folder.is_dir():
        return set()

    return {
        _relative(item, folder)
        for item in folder.rglob("*")
        if item.is_file()
        and not item.name.startswith("put_")
        and models.STAGING_DIR not in item.relative_to(folder).parts
    }


def make_plan(records, target):
    """Qué se traslada y adónde. No toca el disco."""
    install_dir = locations.resolve(target)
    source_comfy = Path(records.comfy_dir)
    new_comfy = install_dir / "comfyui"
    source_models = models.resolve_dir(records, source_comfy)
    inside = _is_inside(source_models, source_comfy)
    new_models = new_comfy / "models" if inside else install_dir / "models"
    trees = [Tree(source_comfy, new_comfy, SKIP, None, _same_device(source_comfy, new_comfy))]
    kept_behind = []

    if not inside:
        owned = {
            _relative(entry["path"], source_models)
            for entry in records.owned("model")
            if _is_inside(entry["path"], source_models) and Path(entry["path"]).is_file()
        }
        kept_behind = sorted(_model_files(source_models) - owned)
        trees.append(
            Tree(
                source_models, new_models, (models.STAGING_DIR,), frozenset(owned),
                _same_device(source_models, new_models),
            )
        )

    for tree in trees:
        if tree.source.is_dir():
            tree.entries = walk(tree.source, tree.skip, tree.only)

    return Plan(
        install_dir, current_install_dir(records), source_comfy, new_comfy, source_models,
        new_models, inside, trees, kept_behind,
    )


def current_install_dir(records):
    return Path(records.install_dir) if records.install_dir else Path(records.comfy_dir).parent


def _preconditions(records):
    if not records.mode:
        raise ProvisionError("There is no installation to move. Run `imagehearth-mcp setup`.")

    if records.mode == "attached":
        raise ProvisionError(
            "This installation uses a ComfyUI of yours, which ImageHearth doesn't move: "
            "only the managed ComfyUI can be moved."
        )


def _require_idle():
    quality.require_idle()

    if locks.is_locked(config.SETUP_JOB_LOCK) or agent_setup._job_alive(agent_setup._read_job()):
        raise ProvisionError(
            "An installation started from an agent is running. Nothing was moved: wait "
            "for it to finish and run the command again."
        )


def _install_bytes():
    catalog = manifest.load()
    platform = detect.detect(disk_path=config.DATA_DIR).platform
    return catalog.install_bytes(catalog.pytorch.get(platform.index))


def _check_destination(plan, resuming):
    """Lanza si el destino no sirve; devuelve los avisos."""
    if _is_inside(plan.new_comfy, plan.source_comfy) or _is_inside(plan.source_comfy, plan.new_comfy):
        raise ProvisionError(
            f"{plan.install_dir} overlaps the current ComfyUI folder ({plan.source_comfy}). "
            "Choose a folder outside of it."
        )

    if not resuming:
        for destination in (plan.new_comfy, plan.new_models):
            if destination.exists() and any(destination.iterdir()):
                raise ProvisionError(
                    f"{destination} already exists and is not empty, so nothing is moved "
                    "into it. Choose another folder or empty that one."
                )

    sizes = [size for tree in plan.trees for kind, _, size in tree.entries if kind == FILE]
    install_bytes = 0 if plan.comfy.same_device else _install_bytes()
    issues = locations.check(plan.install_dir, sizes, install_bytes)

    if plan.same_device or resuming:
        # Renombrar no necesita espacio, y reanudar ya tiene parte copiada.
        issues = [issue for issue in issues if issue.code != "disk_space"]

    errors, warnings = locations.split(issues)

    if errors:
        raise ProvisionError("\n".join(errors) + "\nNothing was moved.")

    return warnings


def show_plan(plan, warnings, resuming):
    print(f"\nMove ImageHearth from {plan.current_dir} to {plan.install_dir}")

    if resuming:
        print("This continues a move that was interrupted: what was verified is not copied again.")

    for tree in plan.trees:
        label = "ComfyUI (the Python environment is created again)" if tree is plan.comfy else "Models"
        print(f"  {label}: {format_size(tree.total)} in {tree.count} files")
        print(f"    {tree.source} -> {tree.destination}")

    if plan.kept_behind:
        print(
            f"  Not moved: {len(plan.kept_behind)} models in {plan.source_models} that "
            "ImageHearth did not download. setup or update will download them again if a "
            "profile needs them."
        )

    if plan.same_device:
        print("  Same disk: the folders are renamed, nothing is copied.")
    else:
        print(
            "  Another disk: the files are copied and checked (size and SHA-256), and the old "
            "ones are deleted at the end. "
            f"{format_size(locations.free_bytes(plan.install_dir))} free in the destination."
        )

    for warning in warnings:
        print(f"WARNING: {warning}")

    print("ComfyUI is stopped, and image generation waits, while it moves.")


def _confirm(args, interactive):
    if getattr(args, "yes", False):
        return True

    if not interactive:
        raise ProvisionError(
            "Nothing was moved. Non-interactive mode needs --yes to move the installation."
        )

    return bool(menu.confirm("Move it now?"))


# Transferencia


def _declared_hashes(catalog):
    return {model.dest: model.sha256 for model in catalog.models.values()}


def _models_path(tree, plan, rel):
    """La ruta de `rel` dentro de la carpeta de modelos, o None si no es un modelo."""
    if tree is plan.comfy:
        prefix = _relative(plan.source_models, plan.source_comfy) + "/"
        return rel[len(prefix):] if plan.models_inside and rel.startswith(prefix) else None

    return rel


def _copy_file(source, destination, declared, models_path):
    """Copia a un temporal, comprueba tamaño y SHA-256 declarado, y lo deja en su sitio."""
    temporary = destination.with_name(destination.name + TEMP_SUFFIX)
    destination.parent.mkdir(parents=True, exist_ok=True)

    with open(source, "rb") as origin, open(temporary, "wb") as target:
        while chunk := origin.read(COPY_CHUNK):
            target.write(chunk)

    shutil.copystat(source, temporary)

    if temporary.stat().st_size != Path(source).stat().st_size:
        temporary.unlink()
        raise ProvisionError(
            f"{destination} came out with a different size than {source}. Nothing was "
            "deleted: check the disk and run the command again."
        )

    wanted = declared.get(models_path) if models_path else None

    if wanted and models.sha256(temporary) != wanted:
        temporary.unlink()
        raise ProvisionError(
            f"{Path(source).name} does not match its SHA-256 after copying it to "
            f"{destination.parent}. Nothing was deleted and ImageHearth still works from "
            "the old folder: run `imagehearth-mcp doctor --verify-hashes` and try again."
        )

    files.replace(temporary, destination)


def _copy_tree(tree, plan, state, declared):
    done = {tuple(pair) for pair in state.verified}
    unsaved = 0

    try:
        for kind, rel, size in tree.entries:
            target = tree.destination / rel
            key = (str(tree.destination), rel)

            if kind == DIR:
                target.mkdir(parents=True, exist_ok=True)
                continue

            if key in done and (kind == LINK or (target.is_file() and target.stat().st_size == size)):
                continue

            source = tree.source / rel

            if kind == LINK:
                target.parent.mkdir(parents=True, exist_ok=True)

                if target.is_symlink() or target.exists():
                    target.unlink()

                os.symlink(os.readlink(source), target, target_is_directory=source.is_dir())
            else:
                if size >= BIG_FILE:
                    print(f"  {rel} ({format_size(size)})", flush=True)

                _copy_file(source, target, declared, _models_path(tree, plan, rel))

            state.verified.append(list(key))
            unsaved += 1

            if size >= BIG_FILE or unsaved >= SAVE_EVERY:
                state.save()
                unsaved = 0
    finally:
        state.save()


def _rename_tree(tree):
    """Renombra el árbol, o solo sus archivos propios si es una carpeta de modelos ajena."""
    if tree.only is None:
        if not tree.source.exists() and tree.destination.is_dir():
            return

        tree.destination.parent.mkdir(parents=True, exist_ok=True)

        if tree.destination.exists():
            if any(tree.destination.iterdir()):
                raise ProvisionError(f"{tree.destination} is not empty.")

            tree.destination.rmdir()

        files.replace(tree.source, tree.destination)
        return

    for _, rel, _ in tree.entries:
        source, target = tree.source / rel, tree.destination / rel

        if source.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            files.replace(source, target)


def _venv_works(comfy_dir, run):
    python = paths.find_venv_python(comfy_dir)

    if not python.exists():
        return False

    try:
        return run([str(python), "-c", "import sys"], capture_output=True, timeout=60).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _make_environment(comfy_dir, run):
    catalog = manifest.load()
    platform = detect.detect(disk_path=comfy_dir).platform
    print("Creating the Python environment in the new folder...")
    comfyui.install_environment(comfy_dir, catalog.pytorch.get(platform.index), run)


def _transfer(plan, state, run):
    """Deja los archivos en el destino, verificados. El origen no se toca (salvo al renombrar)."""
    declared = _declared_hashes(manifest.load())

    for tree in plan.trees:
        if tree.same_device:
            print(f"Renaming {tree.source} to {tree.destination}...")
            _rename_tree(tree)
        else:
            print(f"Copying {tree.source} ({format_size(tree.total)})...")
            _copy_tree(tree, plan, state, declared)

    if not plan.comfy.same_device:
        if not state.venv:
            _make_environment(plan.new_comfy, run)
            state.venv = True
            state.save()
    elif not _venv_works(plan.new_comfy, run):
        print("The Python environment did not survive the rename: creating it again.")
        shutil.rmtree(plan.new_comfy / "venv", ignore_errors=True)
        _make_environment(plan.new_comfy, run)


# Cambio de rutas


def _rewrite(path, plan):
    """La ruta nueva de algo que estaba en el origen, o None si no se traslada."""
    for old, new in ((plan.source_comfy, plan.new_comfy), (plan.source_models, plan.new_models)):
        if _is_inside(path, old):
            return str(Path(new) / os.path.relpath(path, old))

    return None


def _switch(plan, records):
    """Apunta la instalación al destino, en orden: yaml de modelos, nodo, registro, configuración."""
    if not plan.models_inside:
        yaml_path = plan.new_comfy / comfyui.EXTRA_PATHS_FILE
        ours = records.is_owned(plan.source_comfy / comfyui.EXTRA_PATHS_FILE)

        if yaml_path.exists() and ours:
            yaml_path.write_text(comfyui.extra_paths_block(plan.new_models), encoding="utf-8")
        elif yaml_path.exists() and json.dumps(str(plan.source_models)) in yaml_path.read_text(
            encoding="utf-8"
        ):
            print(
                f"WARNING: change base_path in {yaml_path} so ComfyUI finds the models:\n"
                f"{comfyui.extra_paths_block(plan.new_models)}"
            )

    entries = []

    for entry in records.entries:
        moved = _rewrite(entry["path"], plan)

        if entry["kind"] == "staging" and moved is not None:
            continue

        entries.append({**entry, "path": moved or entry["path"]})

    records.entries = entries
    records.comfy_dir = str(plan.new_comfy)
    records.models_dir = str(plan.new_models)
    records.install_dir = str(plan.install_dir)
    comfyui.install_node(plan.new_comfy, records, allowed=False)
    records.save()
    write_config(plan.new_comfy, plan.new_models, records)


def write_config(comfy_dir, models_dir, records):
    values = {"comfy_dir": str(comfy_dir)}
    _, current = settings._read(config.CONFIG_FILE)

    if "models_dir" in current or Path(models_dir) != Path(comfy_dir) / "models":
        values["models_dir"] = str(models_dir)

    settings.apply(config.CONFIG_FILE, values, records)

    if os.environ.get("IMAGEHEARTH_COMFY_DIR"):
        print(
            "WARNING: IMAGEHEARTH_COMFY_DIR is set and overrides the folder written to "
            f"{config.CONFIG_FILE}."
        )


# Limpieza y cancelación


def _remove_empty_dirs(folder, keep_root=False):
    """Borra las carpetas vacías de `folder` (y `folder`, salvo `keep_root`); ningún archivo."""
    folder = Path(folder)

    if not folder.is_dir():
        return

    for directory, _, _ in os.walk(folder, topdown=False):
        if keep_root and Path(directory) == folder:
            continue

        try:
            Path(directory).rmdir()
        except OSError:
            continue


def _clean_source(state):
    """Borra del origen lo verificado en el destino, el entorno viejo y las carpetas vacías."""
    from imagehearth_mcp.provisioner import maintenance

    failures = []
    pairs = {destination: source for source, destination in state.roots}

    for destination, rel in state.verified:
        source = Path(pairs.get(destination, "")) / rel
        target = Path(destination) / rel

        try:
            if (source.is_file() or source.is_symlink()) and (target.exists() or target.is_symlink()):
                source.unlink()
        except OSError as error:
            failures.append(f"{source}: {error}")

    source_comfy = Path(state.source)

    for leftover in (source_comfy / "venv", source_comfy / "models" / models.STAGING_DIR):
        try:
            maintenance._remove(leftover)
        except OSError as error:
            failures.append(f"{leftover}: {error}")

    for index, (source, _) in enumerate(state.roots):
        # La carpeta de modelos ajena es del usuario: solo se vacía, no se borra.
        _remove_empty_dirs(source, keep_root=index > 0)

    return failures


def _undo_renames(state):
    """Si se llegó a renombrar, devuelve al origen lo que se movió."""
    for index, (source, destination) in enumerate(state.roots):
        source, destination = Path(source), Path(destination)

        if index == 0:
            if not source.exists() and destination.is_dir():
                source.parent.mkdir(parents=True, exist_ok=True)
                files.replace(destination, source)

            continue

        for _, rel, _ in walk(destination) if destination.is_dir() else ():
            if (destination / rel).is_file() and not (source / rel).exists():
                (source / rel).parent.mkdir(parents=True, exist_ok=True)
                files.replace(destination / rel, source / rel)


def _cancel(state, records):
    """Deshace un traslado a medias: lo copiado al destino se borra y el origen no se toca."""
    removed = 0
    destinations = {destination for _, destination in state.roots}
    _undo_renames(state)

    for destination, rel in state.verified:
        path = Path(destination) / rel

        if path.is_file() or path.is_symlink():
            path.unlink()
            removed += 1

    for destination in destinations:
        root = Path(destination)

        if state.venv and root.name == "comfyui":
            shutil.rmtree(root / "venv", ignore_errors=True)

        if root.is_dir():
            for temporary in root.rglob(f"*{TEMP_SUFFIX}"):
                temporary.unlink()

        _remove_empty_dirs(root)

    for created in state.created:
        _remove_empty_dirs(created)

    state.delete()
    print(f"Move cancelled: {removed} copied files were deleted from {state.destination}.")
    print(f"ImageHearth keeps working from {records.comfy_dir}.")
    return 0


def _finish(state, records):
    """Lo que queda tras el cambio de rutas: configuración, limpieza del origen y registro."""
    from imagehearth_mcp.provisioner import maintenance

    write_config(Path(records.comfy_dir), Path(records.models_dir), records)
    failures = _clean_source(state)

    if state.previous:
        maintenance._prune_install_dir(records, state.previous)

    records.save()
    state.delete()
    return failures


# Orden principal


def relocate(args, run=None):
    run = run or subprocess.run
    records = InstallManifest.load(config.INSTALL_MANIFEST)
    _preconditions(records)
    target = locations.resolve(args.move_to)
    state = State.load(config.MOVE_STATE)
    resuming = state is not None

    if resuming and _normal(state.destination) != _normal(target):
        if _normal(target) == _normal(current_install_dir(records)):
            return _cancel(state, records)

        raise ProvisionError(
            f"A move to {state.destination} was interrupted. Finish it with `imagehearth-mcp "
            f"update --move-to {state.destination}`, or cancel it with `imagehearth-mcp "
            f"update --move-to {current_install_dir(records)}`."
        )

    if resuming and _normal(records.comfy_dir) == _normal(Path(state.destination) / "comfyui"):
        # El cambio de rutas ya se hizo; solo faltaba la limpieza.
        failures = _finish(state, records)
        _report(target, failures)
        return 0

    if _normal(target) == _normal(current_install_dir(records)):
        raise ProvisionError(f"ImageHearth is already installed in {target}.")

    if not Path(records.comfy_dir).is_dir() and not (resuming and state.roots):
        raise ProvisionError(
            f"ComfyUI is not in {records.comfy_dir}, so there is nothing to move. "
            "Run `imagehearth-mcp doctor`."
        )

    interactive = _interactive(args)
    plan = make_plan(records, target)
    warnings = _check_destination(plan, resuming)
    _require_idle()
    show_plan(plan, warnings, resuming)

    if not _confirm(args, interactive):
        print("Nothing was moved.")
        return 0

    try:
        engine = locks.acquire(config.LOCK_FILE, 1)
    except TimeoutError:
        raise ProvisionError(
            "An image is being generated. Nothing was moved: wait for it to finish and "
            "run the command again."
        ) from None

    try:
        if session.read():
            raise ProvisionError(
                "A session needs `recover_engine`. Nothing was moved: recover it and run "
                "the command again."
            )

        return _execute(plan, records, state, run)
    finally:
        engine.release()


def _interactive(args):
    from imagehearth_mcp.provisioner.setup import is_interactive

    return is_interactive(args)


def _report(target, failures):
    if failures:
        print("Moved, but these old files could not be deleted (delete them by hand):")

        for failure in failures:
            print(f"  {failure}")

    print(f"\nMoved to {target}.")
    print(
        "Restart your agent sessions (Claude Code, Codex...) so their ImageHearth server "
        "reads the new folder."
    )


def _execute(plan, records, state, run):
    from imagehearth_mcp.provisioner import maintenance

    if not plan.comfy.same_device:
        problems = preflight.check_uv()

        if problems:
            raise ProvisionError(problems[0].message)

    if state is None:
        top = locations.first_missing(plan.install_dir)
        state = State(
            config.MOVE_STATE,
            str(plan.source_comfy),
            str(plan.install_dir),
            str(plan.current_dir),
            [[str(tree.source), str(tree.destination)] for tree in plan.trees],
            created=[str(top)] if top else [],
        )

    maintenance._stop_managed()
    state.save()

    if state.created:
        records.claim_verified("install_dir", state.created[0])

    _transfer(plan, state, run)
    _switch(plan, records)
    failures = _finish(state, records)
    _report(plan.install_dir, failures)
    return 0
