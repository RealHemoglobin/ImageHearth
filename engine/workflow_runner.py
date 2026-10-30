import json
import random
import time
import uuid
from pathlib import Path

import requests

from engine.orchestrator import generation_session

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / "workflows"
OUTPUT = ROOT / "output"

API = "http://127.0.0.1:8188"


def run_workflow(
    workflow_name: str,
    prompt: str,
    timeout: int = 1200,
    negative_prompt: str = "",
    width: int = 1024,
    height: int = 1024,
):
    if not prompt.strip():
        raise ValueError("El prompt no puede estar vacío.")

    if width < 64 or height < 64:
        raise ValueError("Las dimensiones mínimas son 64x64.")

    workflow_file = WORKFLOWS / workflow_name

    if not workflow_file.is_file():
        raise FileNotFoundError(workflow_file)

    workflow = json.loads(workflow_file.read_text())

    # Sustituir prompts.
    for node in workflow.values():
        if not isinstance(node, dict):
            continue

        if node.get("class_type") != "CLIPTextEncode":
            continue

        current_text = node.get("inputs", {}).get("text", "")
        node["inputs"]["text"] = negative_prompt if current_text == "" else prompt

    # Ajustar dimensiones para SDXL y FLUX.
    for node in workflow.values():
        if not isinstance(node, dict):
            continue

        class_type = node.get("class_type")
        inputs = node.get("inputs", {})

        if class_type in ("EmptyLatentImage", "EmptySD3LatentImage"):
            multiple = 16 if class_type == "EmptySD3LatentImage" else 8

            inputs["width"] = max(multiple, round(width / multiple) * multiple)
            inputs["height"] = max(multiple, round(height / multiple) * multiple)

        if class_type == "KSampler":
            inputs["seed"] = random.randint(0, 2**64 - 1)

    filename = f"imageengine/{uuid.uuid4().hex[:12]}"

    for node in workflow.values():
        if isinstance(node, dict) and node.get("class_type") == "SaveImage":
            node["inputs"]["filename_prefix"] = filename

    OUTPUT.mkdir(parents=True, exist_ok=True)

    with generation_session():
        response = requests.post(
            f"{API}/prompt",
            json={"prompt": workflow},
            timeout=60,
        )
        response.raise_for_status()

        result = response.json()

        if "prompt_id" not in result:
            raise RuntimeError(f"ComfyUI no aceptó el workflow: {result}")

        prompt_id = result["prompt_id"]
        print(f"Generación iniciada: {prompt_id}")

        deadline = time.time() + timeout

        while time.time() < deadline:
            response = requests.get(
                f"{API}/history/{prompt_id}",
                timeout=15,
            )
            response.raise_for_status()

            history = response.json().get(prompt_id)

            if history:
                status = history.get("status", {})

                if status.get("status_str") == "error":
                    raise RuntimeError(f"Error ComfyUI: {status}")

                if status.get("completed"):
                    for node in history.get("outputs", {}).values():
                        for image in node.get("images", []):
                            if image.get("type") != "output":
                                continue

                            result = requests.get(
                                f"{API}/view",
                                params={
                                    "filename": image["filename"],
                                    "subfolder": image.get("subfolder", ""),
                                    "type": "output",
                                },
                                timeout=120,
                            )
                            result.raise_for_status()

                            destination = OUTPUT / f"{uuid.uuid4().hex[:12]}.png"
                            destination.write_bytes(result.content)
                            return str(destination)

                    raise RuntimeError("ComfyUI terminó sin producir imágenes.")

            time.sleep(2)

    raise TimeoutError(f"Workflow no terminado después de {timeout}s.")
