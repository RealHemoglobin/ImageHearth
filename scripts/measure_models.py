r"""Mide un modelo de generación o edición con una instancia propia de ComfyUI (fase 14).

Uso:
    uv run python scripts/measure_models.py --list
    uv run python scripts/measure_models.py --model qwen-image --precision fp8 --tier 16 \\
        --comfy-dir ~/measure-models/comfyui --weights-dir /mnt/NuevoVol/HF_Cache/measure

Por ejecución: descarga (si faltan) los pesos del registro `measure_models/registry.json`
verificando tamaño y SHA-256 contra Hugging Face, arranca ComfyUI en un puerto libre con
carpetas temporales y `--reserve-vram` según el nivel, hace una ejecución de calentamiento
y tres medidas con los prompts y la semilla fijos, y escribe un JSON por modelo, precisión
y nivel. No toca la instalación del usuario ni el ComfyUI gestionado. Niveles: 8, 16 y 24 GB
reservan el resto de la tarjeta de 24 GB; 32 usa la tarjeta completa y estima la VRAM que
pediría sin descarga a RAM (VRAM usada + lo descargado).
"""

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import psutil
import requests

from imagehearth_mcp.platform import processes, spawn

sys.path.insert(0, str(Path(__file__).parent))

import measure_profiles as base

HERE = Path(__file__).parent / "measure_models"
REPO = Path(__file__).parent.parent
EDIT_INPUT = REPO / "specs/2026-11-06-eleccion-modelo-quality/comparison/flux_dev-1.png"
TIERS = (8, 16, 24, 32)
SEED = 1234
SIZE = 1024
NEGATIVE = (
    "low quality, blurry, deformed, extra fingers, watermark, jpeg artifacts, text errors"
)
GENERATE_PROMPTS = [
    "a lighthouse on a rocky coast at sunset, detailed photograph",
    "portrait of an elderly fisherman with a weathered face, soft window light",
    (
        "a cozy cabin in a snowy forest at night, warm light in the windows, "
        "a wooden sign that reads OPEN"
    ),
    (
        "three astronauts playing chess with a robot inside a greenhouse full of tomato "
        "plants, a blue cup on the table to the left and a sleeping dog under the table"
    ),
    (
        "a watercolor painting of a red fox in an autumn forest, loose brush strokes, "
        "visible paper texture, muted palette"
    ),
]
EDIT_PROMPTS = [
    "change the sky to a starry night, keep everything else",
    "add a small wooden sign in the foreground that reads OPEN, keep everything else",
]
HF = "https://huggingface.co"
CHUNK = 8 * 1024 * 1024


def load_registry():
    return json.loads((HERE / "registry.json").read_text(encoding="utf-8"))


def hf_headers():
    token = os.environ.get("HF_TOKEN")
    return {"Authorization": f"Bearer {token}"} if token else {}


def remote_info(repo, path, cache={}):  # noqa: B006 - caché deliberada por proceso
    """Tamaño, SHA-256 y revisión de un fichero en Hugging Face."""
    if repo not in cache:
        entries, url = {}, f"{HF}/api/models/{repo}/tree/main?recursive=1"

        while url:
            reply = requests.get(url, headers=hf_headers(), timeout=60)
            reply.raise_for_status()

            for entry in reply.json():
                entries[entry["path"]] = entry

            url = reply.links.get("next", {}).get("url")

        revision = requests.get(f"{HF}/api/models/{repo}", headers=hf_headers(), timeout=60)
        revision.raise_for_status()
        cache[repo] = (entries, revision.json().get("sha", ""))

    entries, revision = cache[repo]

    if path not in entries:
        sys.exit(f"{repo} has no {path}.")

    entry = entries[path]
    sha = (entry.get("lfs") or {}).get("oid", "")
    return {"repo": repo, "path": path, "revision": revision, "bytes": entry["size"], "sha256": sha}


def sha256_of(path):
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        while block := handle.read(CHUNK):
            digest.update(block)

    return digest.hexdigest()


def fetch(spec, weights_dir):
    """Descarga un fichero si falta, con reanudación, y verifica tamaño y SHA-256."""
    info = remote_info(spec["repo"], spec["path"])
    target = weights_dir / spec["folder"] / Path(spec["path"]).name
    target.parent.mkdir(parents=True, exist_ok=True)

    if not target.exists() or target.stat().st_size != info["bytes"]:
        part = target.with_suffix(target.suffix + ".part")
        done = part.stat().st_size if part.exists() else 0
        headers = {**hf_headers(), **({"Range": f"bytes={done}-"} if done else {})}
        url = f"{HF}/{spec['repo']}/resolve/{info['revision']}/{spec['path']}"
        print(f"Downloading {target.name} ({info['bytes'] / 1e9:.2f} GB)...", file=sys.stderr)

        with requests.get(url, headers=headers, stream=True, timeout=60) as reply:
            reply.raise_for_status()
            mode = "ab" if done and reply.status_code == 206 else "wb"

            with part.open(mode) as out:
                for block in reply.iter_content(CHUNK):
                    out.write(block)

        part.rename(target)

    if target.stat().st_size != info["bytes"]:
        sys.exit(f"{target} has {target.stat().st_size} bytes, expected {info['bytes']}.")

    if info["sha256"]:
        actual = sha256_of(target)

        if actual != info["sha256"]:
            target.unlink()
            sys.exit(f"SHA-256 mismatch in {target.name}: {actual} != {info['sha256']}.")

    return target, {**info, "file": target.name}


def resolve(registry, model, precision):
    entry = registry["models"][model]
    chosen = entry["precisions"][precision]
    common = registry["comun"]
    clips = [common[name] for name in chosen["clips"]] if "clips" in chosen else [common[chosen["clip"]]]
    return {
        "task": entry["task"],
        "workflow": chosen.get("workflow", entry.get("workflow")),
        "weights": chosen["weights"],
        "clips": clips,
        "vae": common[chosen["vae"]],
    }


def fill(node, values):
    """Sustituye los marcadores %NOMBRE% de un workflow."""
    if isinstance(node, dict):
        return {key: fill(value, values) for key, value in node.items()}

    if isinstance(node, list):
        return [fill(value, values) for value in node]

    if isinstance(node, str) and re.fullmatch(r"%[A-Z0-9]+%", node):
        return values[node.strip("%")]

    return node


def build(resolved, names, prompt, reference, seed=SEED):
    template = json.loads((HERE / f"{resolved['workflow']}.json").read_text(encoding="utf-8"))
    values = {
        "PROMPT": prompt,
        "NEGATIVE": NEGATIVE,
        "SEED": seed,
        "WIDTH": SIZE,
        "HEIGHT": SIZE,
        "PREFIX": f"measure/{uuid.uuid4().hex[:10]}",
        "IMAGE": reference,
        "UNET": names["unet"],
        "VAE": names["vae"],
    }

    if len(names["clips"]) == 1:
        values["CLIP"] = names["clips"][0]

    for number, name in enumerate(names["clips"], start=1):
        values[f"CLIP{number}"] = name

    return fill(template, values)


def run_once(comfy, workflow, pid):
    """Envía el workflow y devuelve (segundos, pico VRAM, pico RAM, error, imagen)."""
    with base.Sampler(pid) as sampler:
        started = time.monotonic()
        reply = requests.post(f"{comfy}/prompt", json={"prompt": workflow}, timeout=60)

        if not reply.ok:
            return time.monotonic() - started, sampler.vram, sampler.ram, reply.text[:1500], None

        prompt_id = reply.json()["prompt_id"]
        deadline = time.monotonic() + base.RUN_TIMEOUT

        while time.monotonic() < deadline:
            history = requests.get(f"{comfy}/history/{prompt_id}", timeout=30).json()

            if prompt_id in history:
                entry = history[prompt_id]
                elapsed = time.monotonic() - started
                status = entry.get("status", {})

                if status.get("status_str") == "error":
                    return elapsed, sampler.vram, sampler.ram, json.dumps(status)[:1500], None

                image = next(
                    (
                        image
                        for output in entry["outputs"].values()
                        for image in output.get("images", [])
                    ),
                    None,
                )
                return elapsed, sampler.vram, sampler.ram, None, image

            time.sleep(0.25)

    return base.RUN_TIMEOUT, sampler.vram, sampler.ram, "timeout", None


def staged_from_log(log_path):
    """MB que ComfyUI (VRAM dinámica) prepara por modelo: el mayor es el de la difusión."""
    if not log_path.exists():
        return []

    text = log_path.read_text(encoding="utf-8", errors="replace")
    return [int(value) for value in re.findall(r"dynamic VRAM loading\. (\d+)MB Staged", text)]


def start_comfy(comfy_dir, weights_dir, temp, reserve_gb):
    python = comfy_dir / ".venv/bin/python"

    if sys.platform == "win32":
        python = comfy_dir / ".venv/Scripts/python.exe"

    if not python.exists() or not (comfy_dir / "main.py").exists():
        sys.exit(f"ComfyUI with a .venv not found in {comfy_dir} (use --comfy-dir).")

    (temp / "paths.yaml").write_text(
        f"measure:\n  base_path: {weights_dir}\n  diffusion_models: diffusion_models\n"
        "  text_encoders: text_encoders\n  vae: vae\n",
        encoding="utf-8",
    )
    log = temp / "comfyui.log"
    args = [
        str(python), "main.py", "--listen", "127.0.0.1", "--port", str(base.free_port()),
        "--extra-model-paths-config", str(temp / "paths.yaml"),
        "--input-directory", str(temp / "input"),
        "--output-directory", str(temp / "output"),
        "--temp-directory", str(temp / "temp"),
        "--user-directory", str(temp / "user"),
    ]  # fmt: skip

    if reserve_gb:
        args += ["--reserve-vram", str(reserve_gb)]

    port = args[args.index("--port") + 1]

    with log.open("w") as out:
        process = subprocess.Popen(
            args, cwd=comfy_dir, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
            **spawn.detached_options(),
        )  # fmt: skip

    comfy = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + base.START_TIMEOUT

    while True:
        if process.poll() is not None:
            sys.exit(f"ComfyUI exited at startup (code {process.returncode}). Log: {log}")

        try:
            stats = requests.get(f"{comfy}/system_stats", timeout=5).json()
            return process, comfy, stats, log
        except (requests.RequestException, ValueError):
            if time.monotonic() >= deadline:
                sys.exit("ComfyUI did not respond in time.")

            time.sleep(1)


def measure(args, registry):
    resolved = resolve(registry, args.model, args.precision)
    files, records = [], []

    for spec in [resolved["weights"], *resolved["clips"], resolved["vae"]]:
        path, record = fetch(spec, args.weights_dir)
        files.append(path)
        records.append(record)

    names = {
        "unet": files[0].name,
        "clips": [path.name for path in files[1:-1]],
        "vae": files[-1].name,
    }
    total_mib = int(base.nvidia_query("memory.total"))
    reserve = max(0, round(total_mib / 1024) - args.tier) if args.tier <= 24 else 0
    edit = resolved["task"] == "edit"
    prompts = EDIT_PROMPTS if edit else GENERATE_PROMPTS
    result = {
        "model": args.model,
        "precision": args.precision,
        "tier_gb": args.tier,
        "task": resolved["task"],
        "reserve_vram_gb": reserve,
        "size": f"{SIZE}x{SIZE}",
        "seed": SEED,
        "prompts": prompts,
        "files": records,
        "status": "ok",
    }
    temp = Path(tempfile.mkdtemp(prefix="measure-models-"))

    for folder in ("input", "output", "temp", "user"):
        (temp / folder).mkdir()

    shutil.copy(EDIT_INPUT, temp / "input" / "reference.png")
    process, comfy, stats, log = start_comfy(args.comfy_dir, args.weights_dir, temp, reserve)

    try:
        base.requests.post(f"{comfy}/free", json={"unload_models": True}, timeout=60)
        time.sleep(base.FREE_WAIT)
        baseline = base.used_vram()
        timings, peak_vram, peak_ram = [], 0, 0

        def one(prompt, seed=SEED):
            workflow = build(resolved, names, prompt, "reference.png", seed)
            return run_once(comfy, workflow, process.pid)

        # ComfyUI reutiliza lo ya calculado si el grafo es idéntico: cada medida cambia la
        # semilla para que muestree de verdad. Las imágenes de la comparativa usan SEED.
        cold, vram, ram, error, _ = one(prompts[0], SEED + 1000)
        peak_vram, peak_ram = vram, ram
        result["cold_seconds"] = round(cold, 1)

        for run in range(0 if error else args.runs):
            seconds, vram, ram, error, _ = one(prompts[0], SEED + 2000 + run)
            peak_vram, peak_ram = max(peak_vram, vram), max(peak_ram, ram)

            if error:
                break

            timings.append(seconds)

        if error:
            result["status"] = "oom" if "out of memory" in error.lower() else "error"
            result["error"] = error
        else:
            result["warm_seconds"] = round(statistics.mean(timings), 1)
            result["warm_runs"] = [round(value, 1) for value in timings]

            if args.images_dir:
                folder = args.images_dir / f"{args.model}-{args.precision}-{args.tier}"
                folder.mkdir(parents=True, exist_ok=True)

                for number, prompt in enumerate(prompts, start=1):
                    *_, error, image = one(prompt)

                    if error or image is None:
                        result["image_error"] = error or "no image"
                        break

                    picture = requests.get(f"{comfy}/view", params=image, timeout=120)
                    (folder / f"{number}.png").write_bytes(picture.content)

                result["images"] = str(folder)

        staged = staged_from_log(log)
        peak = max(0, peak_vram - baseline)
        # Con VRAM dinámica no hay un aviso de carga parcial: se deduce de que el pico real
        # no llega al tamaño del mayor modelo preparado (con un margen del 10 %).
        offloaded = max(0, max(staged, default=0) - peak) if peak < 0.9 * max(staged, default=0) else 0
        result.update(
            baseline_vram_mib=baseline,
            peak_vram_mib=peak,
            peak_ram_mib=peak_ram,
            staged_mib=staged,
            partial_offload=offloaded > 0,
            offloaded_mib=offloaded,
        )

        if args.tier == 32 and result["status"] == "ok":
            result["estimated_vram_without_offload_mib"] = result["peak_vram_mib"] + offloaded
            result["estimated"] = offloaded > 0
    finally:
        if not processes.terminate(process.pid, 30):
            processes.kill(process.pid)

        shutil.copy(log, args.output_dir / f"{args.model}-{args.precision}-{args.tier}.log")
        shutil.rmtree(temp, ignore_errors=True)

    result["comfyui_version"] = stats["system"]["comfyui_version"]
    result["custom_nodes"] = sorted(
        path.name for path in (args.comfy_dir / "custom_nodes").iterdir() if path.is_dir() and path.name != "__pycache__"
    )  # fmt: skip
    result.update(
        date=time.strftime("%Y-%m-%d"),
        gpu=base.nvidia_query("name"),
        driver=base.nvidia_query("driver_version"),
        system=f"{platform.system()} {platform.release()}",
        ram_total_mib=psutil.virtual_memory().total // (1024 * 1024),
    )

    if args.delete_weights:
        files[0].unlink(missing_ok=True)

    return result


def parse_args():
    parser = argparse.ArgumentParser(
        description="Measure one model and precision at one VRAM tier. See the module docstring."
    )
    parser.add_argument("--list", action="store_true", help="List models and precisions.")
    parser.add_argument("--model", help="Model name from the registry (see --list).")
    parser.add_argument("--precision", help="Precision of that model (see --list).")
    parser.add_argument("--tier", type=int, choices=TIERS, help="VRAM tier in GB (32 = whole card).")
    parser.add_argument("--comfy-dir", type=Path, help="ComfyUI with a .venv (default: managed one).")
    parser.add_argument("--weights-dir", type=Path, help="Where weights are kept (outside the repo).")
    parser.add_argument("--output-dir", type=Path, default=Path("measurements"), help="JSON and log output.")
    parser.add_argument("--images-dir", type=Path, help="Save the PNG of every prompt here (outside the repo).")
    parser.add_argument("--runs", type=int, default=3, help="Measured runs after the warm-up.")
    parser.add_argument("--delete-weights", action="store_true", help="Delete the main weights file afterwards.")
    return parser.parse_args()


def main():
    args = parse_args()
    registry = load_registry()

    if args.list:
        for name, entry in registry["models"].items():
            print(f"{name} ({entry['task']}): {', '.join(entry['precisions'])}")

        return

    if not (args.model and args.precision and args.tier and args.weights_dir):
        sys.exit("--model, --precision, --tier and --weights-dir are required (or use --list).")

    if args.model not in registry["models"] or args.precision not in registry["models"][args.model]["precisions"]:
        sys.exit("Unknown model or precision. Use --list.")

    if args.comfy_dir is None:
        from imagehearth_mcp.engine import config

        args.comfy_dir = config.COMFY_DIR

    loaded = base.loaded_language_models()

    if loaded:
        sys.exit(f"Language models are loaded ({', '.join(loaded)}). Unload them first.")

    if base.used_vram() > base.MAX_BASELINE_MIB:
        sys.exit("Too much GPU memory is already in use. Close what is using it.")

    args.comfy_dir = args.comfy_dir.expanduser().resolve()
    args.weights_dir = args.weights_dir.expanduser().resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    result = measure(args, registry)
    text = json.dumps(result, indent=2)
    print(text)
    (args.output_dir / f"{args.model}-{args.precision}-{args.tier}.json").write_text(
        text + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
