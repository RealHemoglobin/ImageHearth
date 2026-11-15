"""Compara cada LoRA del catálogo con y sin ella, con los mismos prompts y semilla.

Uso: uv run python scripts/measure_loras.py --images DIR [--lora NAME ...] [--output resultados.json]

Genera con SDXL 1.0 (y la LoRA de detalle fija) cada prompt: sin LoRA, con el mismo texto
(palabras de activación) pero sin LoRA, con la LoRA a su peso recomendado y con otro peso. Guarda las imágenes y una hoja de contacto por LoRA (columnas en ese orden) fuera del
repositorio (DIR). Arranca su propia ComfyUI en un puerto libre y la GPU se comparte: se
niega a medir con modelos de lenguaje cargados.
"""

import argparse
import dataclasses
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

import requests
from measure_profiles import (
    MEASURE_FOLDER,
    free_port,
    loaded_language_models,
    nvidia_query,
    start_comfy,
    submit_and_wait,
    used_vram,
)
from PIL import Image

from imagehearth_mcp.engine import config, loras
from imagehearth_mcp.engine.workflow_runner import prepare_generation
from imagehearth_mcp.platform import processes

PROMPTS = (
    "a red fox sitting in a snowy forest at dawn",
    "a lighthouse on a rocky coast at sunset",
    "a portrait of a young woman reading a book in a cafe",
)
SEED = 1234
SIZE = 1024
THUMB = 320
MAX_BASELINE_MIB = 4096


def alternative_weight(weight):
    """The other strength to try: half the recommended one."""
    return round(weight / 2, 2) or 0.5


def build(prompt, selected, seed):
    """The production workflow for that prompt and LoRAs, with a fixed seed."""
    prepared = prepare_generation(
        "sdxl_base.json", prompt, "", SIZE, SIZE, "auto", loras=selected
    )

    for node in prepared.workflow.values():
        if node.get("class_type") == "KSampler":
            node["inputs"]["seed"] = seed

        if node.get("class_type") == "SaveImage":
            node["inputs"]["filename_prefix"] = f"{MEASURE_FOLDER}/{prepared.image_id}"

    return prepared


def texts(workflow):
    """The text of each CLIPTextEncode node, by node id."""
    return {
        key: node["inputs"]["text"]
        for key, node in workflow.items()
        if node.get("class_type") == "CLIPTextEncode"
    }


def control(prompt, selected, seed):
    """The same request and text as with the LoRAs, but without them.

    Tells the effect of the LoRA from the effect of its activation words.
    """
    with_loras = build(prompt, selected, seed)
    prepared = build(prompt, [], seed)

    for key, text in texts(with_loras.workflow).items():
        prepared.workflow[key]["inputs"]["text"] = text

    return prepared


def generate(base, prompt, selected, seed, destination, only_text=False):
    prepared = control(prompt, selected, seed) if only_text else build(prompt, selected, seed)
    started = time.monotonic()
    entry = submit_and_wait(base, prepared.workflow)
    elapsed = time.monotonic() - started
    image = next(
        image for output in entry["outputs"].values() for image in output.get("images", [])
    )
    reply = requests.get(f"{base}/view", params=image, timeout=120)
    reply.raise_for_status()
    destination.write_bytes(reply.content)
    return elapsed


def difference(first, second):
    """Mean absolute difference between two images, 0 to 255."""
    with Image.open(first) as one, Image.open(second) as two:
        a = list(one.convert("L").resize((128, 128)).getdata())
        b = list(two.convert("L").resize((128, 128)).getdata())

    return sum(abs(x - y) for x, y in zip(a, b, strict=True)) / len(a)


def contact_sheet(rows, destination):
    """Rows of images side by side (one row per prompt), as a single PNG."""
    columns = max(len(row) for row in rows)
    sheet = Image.new("RGB", (columns * THUMB, len(rows) * THUMB), "white")

    for y, row in enumerate(rows):
        for x, path in enumerate(row):
            with Image.open(path) as image:
                thumb = image.convert("RGB").resize((THUMB, THUMB))
                sheet.paste(thumb, (x * THUMB, y * THUMB))

    sheet.save(destination)


def measure(base, lora, folder, seed):
    """Baseline (no LoRA), recommended weight and alternative weight for every prompt."""
    weights = [lora.weight, alternative_weight(lora.weight)]
    rows = []
    seconds = []
    differences = []

    for number, prompt in enumerate(PROMPTS, start=1):
        row = []
        runs = [("none", []), ("words", [loras.Selected(lora, weights[0])])] + [
            (f"w{weight:g}", [loras.Selected(lora, weight)]) for weight in weights
        ]

        for label, selected in runs:
            path = folder / f"{lora.name}-{number}-{label}.png"

            if label == "none":
                path = folder / f"baseline-{number}.png"

                if path.exists():
                    row.append(path)
                    continue

            if label == "words":
                path = folder / f"{lora.name}-{number}-words.png"
                generate(base, prompt, selected, seed, path, only_text=True)
                row.append(path)
                continue

            seconds.append(generate(base, prompt, selected, seed, path))
            row.append(path)

        rows.append(row)
        differences.append(
            [round(difference(row[1], other), 1) for other in row[2:]]
        )

    contact_sheet(rows, folder / f"{lora.name}-sheet.png")
    return {
        "name": lora.name,
        "category": lora.category,
        "weights": weights,
        # Mean pixel difference (0-255) of each weight against the same text without the LoRA,
        # one row per prompt: ~0 means the LoRA adds nothing beyond its activation words.
        "difference_from_words_only": differences,
        "sheet": str(folder / f"{lora.name}-sheet.png"),
        "seconds_per_image": round(sum(seconds) / len(seconds), 1),
    }


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", type=Path, required=True, help="Where to save the images.")
    parser.add_argument("--output", type=Path, help="Write the JSON here too.")
    parser.add_argument("--lora", action="append", help="Only this one. Repeat for several.")
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--comfy-arg", action="append", default=[])
    return parser.parse_args()


def main():
    args = parse_args()
    loaded = loaded_language_models()

    if loaded:
        sys.exit(f"Language models are loaded ({', '.join(loaded)}). Unload them first.")

    if used_vram() > MAX_BASELINE_MIB:
        sys.exit("The GPU is already in use: close what is using it and run this again.")

    found = loras.installed()
    names = args.lora or list(found)
    missing = [name for name in names if name not in found]

    if missing:
        sys.exit(
            f"Not installed: {', '.join(missing)}. Install them with "
            "`imagehearth-mcp setup --loras all`."
        )

    args.images.mkdir(parents=True, exist_ok=True)
    process, base, stats = start_comfy(free_port(), args.comfy_arg, None)
    results = []

    try:
        with tempfile.TemporaryDirectory():
            for name in names:
                print(f"Measuring {name}...", file=sys.stderr)
                results.append(measure(base, found[name], args.images, args.seed))
    finally:
        if not processes.terminate(process.pid, 30):
            processes.kill(process.pid)

        for kind in ("input", "output"):
            shutil.rmtree(config.COMFY_DIR / kind / MEASURE_FOLDER, ignore_errors=True)

    report = {
        "date": time.strftime("%Y-%m-%d"),
        "gpu": nvidia_query("name"),
        "comfyui_version": stats["system"]["comfyui_version"],
        "seed": args.seed,
        "prompts": PROMPTS,
        "results": results,
        "catalog": [dataclasses.asdict(found[name]) for name in names],
    }
    text = json.dumps(report, indent=2)
    print(text)

    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
