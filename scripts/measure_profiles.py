"""Mide VRAM, RAM y tiempo de cada workflow instalado, con una instancia propia de ComfyUI.

Uso: uv run python scripts/measure_profiles.py [--output resultados.json] [--runs 3]

Arranca ComfyUI en un puerto libre, así que no toca el que esté en uso, pero la GPU
sí se comparte: la memoria que ya está ocupada se resta, y con modelos de lenguaje
cargados se niega a medir. No genera a través del motor, que los descargaría.
"""

import argparse
import json
import platform
import shutil
import socket
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

import psutil
import requests
from PIL import Image

from imagehearth_mcp.engine import catalog, config, kontext
from imagehearth_mcp.engine.workflow_runner import prepare_workflow
from imagehearth_mcp.platform import paths, processes, spawn

WIDTH = HEIGHT = 1024
PROMPT = "a lighthouse on a rocky coast at sunset, detailed photograph"
EDIT_PROMPT = "change the sky to a starry night, keep everything else"
START_TIMEOUT = 300
RUN_TIMEOUT = 1800
SAMPLE_INTERVAL = 0.25
FREE_WAIT = 5
MEASURE_FOLDER = "imagehearth-measure"
# Por encima de esto, otro proceso ocupa tanta GPU que las cifras no sirven.
MAX_BASELINE_MIB = 4096


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def nvidia_query(field):
    output = subprocess.run(
        ["nvidia-smi", f"--query-gpu={field}", "--format=csv,noheader,nounits"],
        capture_output=True,
        encoding="utf-8",
        timeout=10,
        check=True,
    ).stdout
    return output.splitlines()[0].strip()


def used_vram():
    return int(nvidia_query("memory.used"))


def tree_rss(pid):
    try:
        process = psutil.Process(pid)
        members = [process, *process.children(recursive=True)]
        return sum(member.memory_info().rss for member in members) // (1024 * 1024)
    except psutil.Error:
        return 0


class Sampler:
    """Picos de VRAM y RAM en un hilo aparte mientras dura el bloque."""

    def __init__(self, pid):
        self.pid = pid
        self.vram = 0
        self.ram = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while not self._stop.wait(SAMPLE_INTERVAL):
            self.vram = max(self.vram, used_vram())
            self.ram = max(self.ram, tree_rss(self.pid))

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join()


def loaded_language_models():
    try:
        reply = requests.get(f"{config.OLLAMA_API}/api/ps", timeout=3)
        return [model["name"] for model in reply.json().get("models", [])]
    except (requests.RequestException, ValueError, KeyError):
        return []


def submit_and_wait(base, workflow):
    reply = requests.post(f"{base}/prompt", json={"prompt": workflow}, timeout=60)

    if not reply.ok:
        sys.exit(f"ComfyUI rejected the workflow: {reply.text}")

    prompt_id = reply.json()["prompt_id"]
    deadline = time.monotonic() + RUN_TIMEOUT

    while time.monotonic() < deadline:
        history = requests.get(f"{base}/history/{prompt_id}", timeout=30).json()

        if prompt_id in history:
            status = history[prompt_id].get("status", {})

            if status.get("status_str") == "error":
                sys.exit(f"The generation failed: {json.dumps(status)[:2000]}")

            return

        time.sleep(0.25)

    sys.exit(f"The generation did not finish within {RUN_TIMEOUT} seconds.")


def upload_reference(base, folder):
    path = Path(folder) / "reference.png"
    Image.effect_noise((WIDTH, HEIGHT), 64).convert("RGB").save(path)

    with path.open("rb") as image:
        reply = requests.post(
            f"{base}/upload/image",
            files={"image": ("reference.png", image)},
            data={"type": "input", "subfolder": MEASURE_FOLDER},
            timeout=120,
        )

    reply.raise_for_status()
    uploaded = reply.json()
    return f"{uploaded['subfolder']}/{uploaded['name']}"


def build(name, base, folder):
    filename = f"{MEASURE_FOLDER}/{uuid.uuid4().hex[:12]}"

    if name in config.INTERNAL_WORKFLOWS:
        return kontext.build_workflow(
            [upload_reference(base, folder)],
            EDIT_PROMPT,
            WIDTH,
            HEIGHT,
            filename,
            workflow_name=name,
        )

    template = json.loads(
        (config.WORKFLOWS_DIR / f"{name}.json").read_text(encoding="utf-8")
    )
    return prepare_workflow(template, PROMPT, "", WIDTH, HEIGHT, filename)


def unload(base):
    requests.post(
        f"{base}/free", json={"unload_models": True, "free_memory": True}, timeout=60
    ).raise_for_status()
    time.sleep(FREE_WAIT)


def timed_run(name, base, folder, pid):
    workflow = build(name, base, folder)

    with Sampler(pid) as sampler:
        started = time.monotonic()
        submit_and_wait(base, workflow)
        elapsed = time.monotonic() - started

    return elapsed, sampler


def measure(name, base, folder, pid, runs):
    unload(base)
    baseline = used_vram()
    cold, sampler = timed_run(name, base, folder, pid)
    peak_vram, peak_ram = sampler.vram, sampler.ram
    warm = []

    for _ in range(runs):
        elapsed, sampler = timed_run(name, base, folder, pid)
        warm.append(elapsed)
        peak_vram = max(peak_vram, sampler.vram)
        peak_ram = max(peak_ram, sampler.ram)

    return {
        "workflow": name,
        "width": WIDTH,
        "height": HEIGHT,
        "references": 1 if name in config.INTERNAL_WORKFLOWS else 0,
        "baseline_vram_mib": baseline,
        "peak_vram_mib": peak_vram - baseline,
        "peak_ram_mib": peak_ram,
        "cold_seconds": round(cold, 1),
        "warm_seconds": round(statistics.mean(warm), 1),
        "warm_runs": [round(value, 1) for value in warm],
    }


def start_comfy(port, extra_args, env):
    python = paths.find_venv_python(config.COMFY_DIR)

    if not python.exists() or not (config.COMFY_DIR / "main.py").exists():
        sys.exit(f"ComfyUI not found in {config.COMFY_DIR} (set IMAGEHEARTH_COMFY_DIR).")

    process = subprocess.Popen(
        [str(python), "main.py", "--listen", "127.0.0.1", "--port", str(port), *extra_args],
        cwd=config.COMFY_DIR,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
        **spawn.detached_options(),
    )
    base = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + START_TIMEOUT

    while True:
        if process.poll() is not None:
            sys.exit(f"ComfyUI exited at startup (code {process.returncode}).")

        try:
            stats = requests.get(f"{base}/system_stats", timeout=5).json()
            return process, base, stats
        except (requests.RequestException, ValueError):
            if time.monotonic() >= deadline:
                sys.exit(f"ComfyUI did not respond within {START_TIMEOUT} seconds.")

            time.sleep(1)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Write the JSON here too.")
    parser.add_argument("--runs", type=int, default=3, help="Warm generations.")
    parser.add_argument(
        "--workflow",
        action="append",
        help="Measure only this workflow. Repeat it for several.",
    )
    parser.add_argument(
        "--comfy-arg",
        action="append",
        default=[],
        help="Extra argument for ComfyUI, such as --comfy-arg=--base-directory=DIR.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    loaded = loaded_language_models()

    if loaded:
        sys.exit(f"Language models are loaded ({', '.join(loaded)}). Unload them first.")

    baseline = used_vram()

    if baseline > MAX_BASELINE_MIB:
        sys.exit(
            f"{baseline} MiB of GPU memory are already in use. Close what is using "
            "them, such as a running ComfyUI with models loaded."
        )

    entries = catalog.entries()
    selected = []

    for name in args.workflow or entries:
        entry = entries.get(name)

        if entry is None:
            continue

        if entry.installed:
            selected.append(name)
        else:
            print(
                f"WARNING: skipping {name}: not installed "
                f"(needs --profile {entry.profile}).",
                file=sys.stderr,
            )

    if not selected:
        sys.exit("No workflow to measure is installed.")

    process, base, stats = start_comfy(free_port(), args.comfy_arg, None)
    results = []

    try:
        with tempfile.TemporaryDirectory() as folder:
            for name in selected:
                print(f"Measuring {name}...", file=sys.stderr)
                results.append(measure(name, base, folder, process.pid, args.runs))
    finally:
        if not processes.terminate(process.pid, 30):
            processes.kill(process.pid)

        for kind in ("input", "output"):
            shutil.rmtree(config.COMFY_DIR / kind / MEASURE_FOLDER, ignore_errors=True)

    report = {
        "date": time.strftime("%Y-%m-%d"),
        "gpu": nvidia_query("name"),
        "vram_total_mib": int(nvidia_query("memory.total")),
        "driver": nvidia_query("driver_version"),
        "system": f"{platform.system()} {platform.release()}",
        "ram_total_mib": psutil.virtual_memory().total // (1024 * 1024),
        "comfyui_version": stats["system"]["comfyui_version"],
        "results": results,
    }
    text = json.dumps(report, indent=2)
    print(text)

    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
