"""Mide el ahorro de la generación por lotes con la GPU real (fase 8).

Uso:
    uv run python scripts/measure_batch.py [--ollama-model NOMBRE] [--reference foto.png]
        [--only generate|edit|cancel] [--output resultados.json]

Genera de verdad con el motor instalado y la configuración del usuario, así que
descarga y restaura los modelos de lenguaje que haya cargados. Compara:

- generate: 4 imágenes `fast` + 2 `high` en un lote frente a 6 llamadas sueltas.
- edit: 3 ediciones con Kontext en un lote frente a 3 llamadas sueltas (necesita
  --reference, una imagen cualquiera, y el perfil `full`).
- cancel: cancela un lote a mitad y comprueba GPU libre, modelo restaurado e
  imágenes en disco.

Con --ollama-model, el modelo se carga antes de cada medición (como lo tendría un
agente local) y se cuentan las veces que el motor lo descarga.
Las imágenes se guardan en la carpeta de salida configurada.
"""

import argparse
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import requests

from imagehearth_mcp.engine import batch, config, orchestrator, progress, state
from imagehearth_mcp.engine.image_router import create_image

FAST_PROMPTS = [f"a {thing}, detailed photograph" for thing in ("lighthouse", "fox", "castle", "bicycle")]
HIGH_PROMPTS = ["a medieval market at dawn, detailed", "a mountain lake, cinematic light"]
EDIT_PROMPTS = [
    "change the sky to a starry night",
    "make it look like a watercolor painting",
    "turn it into a snowy winter scene",
]


def used_vram():
    output = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
        capture_output=True,
        encoding="utf-8",
        timeout=10,
        check=True,
    ).stdout
    return int(output.splitlines()[0])


def ollama_loaded():
    try:
        response = requests.get(f"{config.OLLAMA_API}/api/ps", timeout=5)
        return [model["name"] for model in response.json().get("models", [])]
    except requests.RequestException:
        return []


def load_ollama(name):
    """Carga el modelo y lo mantiene, como lo dejaría un agente local."""
    if not name:
        return

    requests.post(
        f"{config.OLLAMA_API}/api/generate",
        json={"model": name, "prompt": "", "keep_alive": -1},
        timeout=600,
    ).raise_for_status()


class Cycles:
    """Cuenta las veces que el motor libera la memoria del servidor de modelos."""

    def __init__(self):
        self.count = 0
        self._real = orchestrator._free_server_memory

    def __enter__(self):
        def spy(session):
            self.count += 1
            return self._real(session)

        orchestrator._free_server_memory = spy
        return self

    def __exit__(self, *exc):
        orchestrator._free_server_memory = self._real


def measure(label, function, model):
    load_ollama(model)
    before = ollama_loaded()

    with Cycles() as cycles:
        start = time.monotonic()
        function()
        seconds = time.monotonic() - start

    after = ollama_loaded()
    result = {
        "label": label,
        "seconds": round(seconds, 1),
        "model_unload_cycles": cycles.count,
        "ollama_before": before,
        "ollama_after": after,
    }
    print(json.dumps(result))
    return result


def compare(name, singles, together, model):
    """Primero las llamadas sueltas y luego el lote, con una pasada de calentamiento."""
    print(f"\n== {name} ==")
    measure("warm-up (one image)", singles[0], model)
    separate = measure("separate calls", lambda: [call() for call in singles], model)
    grouped = measure("one batch", together, model)
    saved = separate["seconds"] - grouped["seconds"]
    summary = {
        "name": name,
        "separate": separate,
        "batch": grouped,
        "saved_seconds": round(saved, 1),
        "saved_percent": round(100 * saved / separate["seconds"], 1),
    }
    print(f"saved {summary['saved_seconds']} s ({summary['saved_percent']} %)")
    return summary


def run_generate(model):
    items = [{"prompt": p, "quality": "fast"} for p in FAST_PROMPTS] + [
        {"prompt": p, "quality": "high"} for p in HIGH_PROMPTS
    ]
    singles = [
        (lambda item=item: create_image(item["prompt"], quality=item["quality"]))
        for item in items
    ]
    return compare("4 fast + 2 high", singles, lambda: batch.run(items), model)


def run_edit(model, reference):
    singles = [
        (lambda prompt=prompt: create_image(prompt, image_paths=[reference]))
        for prompt in EDIT_PROMPTS
    ]
    return compare(
        "3 Kontext edits",
        singles,
        lambda: batch.run(EDIT_PROMPTS, image_paths=[reference]),
        model,
    )


def run_cancel(model):
    """Cancela cuando aparece la segunda imagen y comprueba cómo queda el sistema."""
    print("\n== cancel ==")
    load_ollama(model)
    baseline = used_vram()
    wanted = ollama_loaded()
    known = set(config.OUTPUT_DIR.glob("*.png")) if config.OUTPUT_DIR.exists() else set()
    tracker = progress.Tracker()
    outcome = {}

    def work():
        with progress.tracking(tracker):
            outcome["result"] = batch.run(
                [{"prompt": p, "quality": "fast"} for p in FAST_PROMPTS + HIGH_PROMPTS]
            )

    thread = threading.Thread(target=work)
    thread.start()

    while thread.is_alive():
        made = set(config.OUTPUT_DIR.glob("*.png")) - known if config.OUTPUT_DIR.exists() else set()

        if len(made) >= 2:
            tracker.cancelled.set()
            break

        time.sleep(0.5)

    thread.join(timeout=config.CANCEL_TIMEOUT + 120)
    time.sleep(5)

    made = set(config.OUTPUT_DIR.glob("*.png")) - known
    lines = str(outcome.get("result", "")).splitlines()
    result = {
        "finished": not thread.is_alive(),
        "images_on_disk": len(made),
        "response": lines,
        "vram_baseline_mib": baseline,
        "vram_after_mib": used_vram(),
        "ollama_expected": wanted,
        "ollama_after": ollama_loaded(),
        "session_state": state.read(),
    }
    result["ok"] = (
        result["finished"]
        and len(made) >= 2
        and any("cancelled" in line for line in lines)
        and result["session_state"] is None
        and set(wanted) <= set(result["ollama_after"])
        and result["vram_after_mib"] <= baseline + 512
    )
    print(json.dumps(result, indent=2, default=str))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--ollama-model", help="Modelo de Ollama a mantener cargado.")
    parser.add_argument("--reference", help="Imagen para las ediciones con Kontext.")
    parser.add_argument("--only", choices=("generate", "edit", "cancel"))
    parser.add_argument("--output", help="Guarda los resultados en este JSON.")
    args = parser.parse_args()

    if args.only == "edit" and not args.reference:
        sys.exit("--reference is needed for the edit comparison.")

    results = {}

    if args.only in (None, "generate"):
        results["generate"] = run_generate(args.ollama_model)

    if args.only == "edit" or (args.only is None and args.reference):
        results["edit"] = run_edit(args.ollama_model, str(Path(args.reference).resolve()))

    if args.only in (None, "cancel"):
        results["cancel"] = run_cancel(args.ollama_model)

    if args.output:
        Path(args.output).write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
