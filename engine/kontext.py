import json
import time
import uuid
from pathlib import Path

import requests
from PIL import Image

from engine.orchestrator import generation_session

BASE_DIR = Path(__file__).resolve().parent.parent
WORKFLOW_FILE = BASE_DIR / "workflows" / "flux_kontext_dev_basic.json"
OUTPUT_DIR = BASE_DIR / "output"

API = "http://127.0.0.1:8188"
MAX_REFERENCE_IMAGES = 6


def normalize_image_paths(image_path=None, image_paths=None):
    paths = []

    if image_path:
        paths.append(image_path)

    if image_paths:
        if isinstance(image_paths, (str, Path)):
            paths.append(image_paths)
        else:
            paths.extend(image_paths)

    unique = []
    seen = set()

    for path in paths:
        resolved = str(Path(path).expanduser().resolve())

        if resolved not in seen:
            seen.add(resolved)
            unique.append(Path(resolved))

    if not unique:
        raise ValueError("Debes proporcionar al menos una imagen.")

    if len(unique) > MAX_REFERENCE_IMAGES:
        raise ValueError(
            f"Kontext admite como máximo {MAX_REFERENCE_IMAGES} imágenes."
        )

    for path in unique:
        if not path.is_file():
            raise FileNotFoundError(path)

        try:
            with Image.open(path) as image:
                image.verify()
        except Exception as error:
            raise ValueError(f"Imagen no válida: {path}: {error}") from error

    return unique


def upload_image(image_path):
    image_path = Path(image_path)

    with image_path.open("rb") as image:
        response = requests.post(
            f"{API}/upload/image",
            files={"image": (image_path.name, image)},
            data={"overwrite": "true"},
            timeout=120,
        )

    response.raise_for_status()
    return response.json()["name"]


def output_dimensions(first_image, width=0, height=0):
    if not width or not height:
        with Image.open(first_image) as image:
            original_width, original_height = image.size

        width = width or original_width
        height = height or original_height

    # EmptySD3LatentImage requiere dimensiones múltiplos de 16.
    width = max(256, round(width / 16) * 16)
    height = max(256, round(height / 16) * 16)

    if width > 4096 or height > 4096:
        raise ValueError("Las dimensiones máximas de salida son 4096x4096.")

    return width, height


def build_workflow(uploaded_images, prompt, width, height, filename):
    workflow = json.loads(WORKFLOW_FILE.read_text())

    required_nodes = [
        "192:6",
        "192:35",
        "192:37",
        "192:38",
        "192:39",
        "192:135",
        "192:31",
        "192:8",
        "136",
    ]

    for node_id in required_nodes:
        if node_id not in workflow:
            raise RuntimeError(f"Falta el nodo requerido {node_id} en Kontext.")

    # Eliminar el antiguo camino basado en ImageStitch y VAEEncode único.
    for node_id in ("190", "192:146", "192:42", "192:124", "192:177"):
        workflow.pop(node_id, None)

    workflow["192:6"]["inputs"]["text"] = prompt

    # Crear un latente de salida independiente de las referencias.
    latent_id = "IMAGEENGINE_EMPTY_LATENT"

    workflow[latent_id] = {
        "class_type": "EmptySD3LatentImage",
        "inputs": {
            "width": width,
            "height": height,
            "batch_size": 1,
        },
    }

    workflow["192:31"]["inputs"]["latent_image"] = [latent_id, 0]

    # Encadenar referencias mediante ReferenceLatent.
    previous_conditioning = "192:6"

    for index, uploaded_name in enumerate(uploaded_images, start=1):
        load_id = f"IMAGEENGINE_LOAD_{index}"
        scale_id = f"IMAGEENGINE_SCALE_{index}"
        encode_id = f"IMAGEENGINE_ENCODE_{index}"
        reference_id = f"IMAGEENGINE_REFERENCE_{index}"

        workflow[load_id] = {
            "class_type": "LoadImage",
            "inputs": {"image": uploaded_name},
        }

        workflow[scale_id] = {
            "class_type": "FluxKontextImageScale",
            "inputs": {
                "image": [load_id, 0],
            },
        }

        workflow[encode_id] = {
            "class_type": "VAEEncode",
            "inputs": {
                "pixels": [scale_id, 0],
                "vae": ["192:39", 0],
            },
        }

        workflow[reference_id] = {
            "class_type": "ReferenceLatent",
            "inputs": {
                "conditioning": [previous_conditioning, 0],
                "latent": [encode_id, 0],
            },
        }

        previous_conditioning = reference_id

    # El condicionamiento final contiene todas las referencias.
    workflow["192:35"]["inputs"]["conditioning"] = [
        previous_conditioning,
        0,
    ]

    workflow["136"]["inputs"]["filename_prefix"] = filename

    return workflow


def generate(
    prompt,
    image_path=None,
    timeout=1800,
    image_paths=None,
    width=0,
    height=0,
):
    if not prompt or not prompt.strip():
        raise ValueError("El prompt no puede estar vacío.")

    paths = normalize_image_paths(image_path, image_paths)
    width, height = output_dimensions(paths[0], width, height)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with generation_session():
        uploaded_images = [upload_image(path) for path in paths]

        filename = f"kontext_{uuid.uuid4().hex[:12]}"

        workflow = build_workflow(
            uploaded_images=uploaded_images,
            prompt=prompt,
            width=width,
            height=height,
            filename=filename,
        )

        response = requests.post(
            f"{API}/prompt",
            json={"prompt": workflow},
            timeout=60,
        )
        response.raise_for_status()

        result = response.json()

        if "prompt_id" not in result:
            raise RuntimeError(f"ComfyUI rechazó el workflow: {result}")

        prompt_id = result["prompt_id"]

        print(f"Generación Kontext iniciada: {prompt_id}")
        print(f"Referencias independientes: {len(paths)}")
        print(f"Dimensiones de salida: {width}x{height}")

        deadline = time.time() + timeout

        while time.time() < deadline:
            history_response = requests.get(
                f"{API}/history/{prompt_id}",
                timeout=15,
            )
            history_response.raise_for_status()

            history = history_response.json().get(prompt_id)

            if history:
                status = history.get("status", {})

                if status.get("status_str") == "error":
                    raise RuntimeError(f"Error en ComfyUI: {status}")

                if status.get("completed"):
                    for node in history.get("outputs", {}).values():
                        for image in node.get("images", []):
                            if image.get("type") != "output":
                                continue

                            image_response = requests.get(
                                f"{API}/view",
                                params={
                                    "filename": image["filename"],
                                    "subfolder": image.get("subfolder", ""),
                                    "type": "output",
                                },
                                timeout=120,
                            )
                            image_response.raise_for_status()

                            destination = OUTPUT_DIR / f"{filename}.png"
                            destination.write_bytes(image_response.content)

                            print(f"Imagen guardada: {destination}")
                            return destination

            time.sleep(2)

        raise TimeoutError(
            f"ComfyUI no terminó en los {timeout} segundos disponibles."
        )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generación FLUX Kontext")
    parser.add_argument("image", nargs="+", help="Imágenes de referencia")
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--width", type=int, default=0)
    parser.add_argument("--height", type=int, default=0)

    args = parser.parse_args()

    generate(
        prompt=args.prompt,
        image_paths=args.image,
        width=args.width,
        height=args.height,
    )
