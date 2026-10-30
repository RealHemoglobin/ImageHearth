import time
import requests

OLLAMA = "http://127.0.0.1:11434"


def get_loaded_models():
    response = requests.get(f"{OLLAMA}/api/ps", timeout=10)
    response.raise_for_status()
    return response.json().get("models", [])


def unload_model(name):
    response = requests.post(
        f"{OLLAMA}/api/generate",
        json={"model": name, "prompt": "", "keep_alive": 0},
        timeout=180,
    )
    response.raise_for_status()


def unload_all(timeout=120):
    original = get_loaded_models()
    names = [model["name"] for model in original]

    try:
        for name in names:
            print(f"Descargando modelo Ollama: {name}")
            unload_model(name)

        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            remaining = get_loaded_models()

            if not remaining:
                print("Todos los modelos de Ollama están descargados.")
                return original

            print(
                "Esperando descarga de Ollama:",
                [model["name"] for model in remaining],
            )
            time.sleep(2)

        raise TimeoutError(
            "Ollama no liberó todos los modelos. "
            f"Siguen activos: {[m['name'] for m in get_loaded_models()]}"
        )

    except Exception as unload_error:
        print("ERROR durante la descarga de Ollama.")
        print("Intentando restaurar el estado original...")

        recovery = restore_models(original)

        if recovery["failed"]:
            raise RuntimeError(
                "Falló la descarga de Ollama y también su recuperación. "
                f"Restaurados: {recovery['restored']}. "
                f"Fallidos: {recovery['failed']}"
            ) from unload_error

        print("Estado original de Ollama restaurado.")
        raise

def restore_models(models):
    restored = []
    failed = []

    for model in models:
        name = model["name"]

        try:
            requests.post(
                f"{OLLAMA}/api/generate",
                json={
                    "model": name,
                    "prompt": "",
                    "keep_alive": -1,
                },
                timeout=600,
            ).raise_for_status()

            deadline = time.monotonic() + 600

            while time.monotonic() < deadline:
                active = {
                    item["name"] for item in get_loaded_models()
                }
                if name in active:
                    restored.append(name)
                    break
                time.sleep(2)
            else:
                failed.append(name)

        except requests.RequestException as error:
            failed.append(name)
            print(f"Error restaurando {name}: {error}")

    return {"restored": restored, "failed": failed}


if __name__ == "__main__":
    print("Modelos activos:", [m["name"] for m in get_loaded_models()])
