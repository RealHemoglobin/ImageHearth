# Stack técnico y decisiones

## Arquitectura objetivo

```
Agente (Claude Code, Codex, Cursor, VS Code, Gemini CLI...)
   │ MCP por stdio
   ▼
imagehearth-mcp ─ paquete Python ligero, entorno propio gestionado por uv
   ├─ server       herramientas e instrucciones MCP
   ├─ engine       núcleo actual: sesiones, recuperación, validación
   ├─ data         workflows, skill y nodo de ComfyUI como datos de paquete
   ├─ platform     procesos (psutil), bloqueos (filelock), rutas del venv y arranque desacoplado por sistema
   ├─ provisioner  detección, instalación, manifiesto, doctor
   └─ cli          setup, doctor, connect, models, update, uninstall
   │ HTTP local
   ▼
ComfyUI ─ entorno propio con PyTorch, gestionado o existente
   └─ nodo imagehearth_status (ruta /imagehearth/status, versionada)
   │ opcional
   ▼
Ollama, LM Studio, llama.cpp, vLLM ─ opcionales (memory_mode = auto | off | manual), detrás de la interfaz MemoryProvider
```

El punto clave es que el **servidor MCP no depende de PyTorch**. Arranca en segundos en cualquier sistema, aunque ComfyUI no esté instalado, y puede explicar qué falta en lugar de fallar.

## Rutas por defecto

Se resuelven con `platformdirs` desde `src/imagehearth_mcp/` (paquete `imagehearth_mcp`, módulo `engine/config.py`). Prioridad: variable de entorno, después `config.toml`, después valor por defecto.

| Dato | Linux | macOS | Windows |
|---|---|---|---|
| Configuración | `~/.config/imagehearth/` | `~/Library/Application Support/imagehearth/` | `%APPDATA%\imagehearth\` |
| ComfyUI, modelos, estado | `~/.local/share/imagehearth/` | `~/Library/Application Support/imagehearth/` | `%LOCALAPPDATA%\imagehearth\` |
| Logs | `~/.local/state/imagehearth/log/` | `~/Library/Logs/imagehearth/` | `%LOCALAPPDATA%\imagehearth\Logs\` |
| Imágenes | `~/Pictures/ImageHearth/` | `~/Pictures/ImageHearth/` | `%USERPROFILE%\Pictures\ImageHearth\` |

## Decisiones

| Tema | Decisión | Motivo | Descartado |
|---|---|---|---|
| Distribución | PyPI más `uv tool install` | uv también instala Python, así que el usuario no necesita tenerlo. La herramienta queda con una ruta estable | Binario con PyInstaller: pesado y difícil de firmar. npm: añade Node sin aportar nada. Docker: no da acceso a la GPU en macOS |
| Arranque de agentes | Ruta absoluta del ejecutable instalado | Evita descargas al arrancar, que podrían superar el plazo del cliente, y los problemas de `PATH` en aplicaciones gráficas | `uvx` como vía principal; queda como opción avanzada |
| Instalar ComfyUI | Instalador propio con versión fijada (v0.43.0, archivo `tar.gz` de la versión en GitHub con SHA-256 fijado) | Reproducible, con control de ruta, sin Git y con uv y Python gestionado. Ver [spike](#spike-de-la-fase-3) | `comfy-cli`: ya admite instalar sin preguntas, pero exige Git |
| ComfyUI existente | Se detecta y se ofrece **adjuntar** | Evita duplicar decenas de GB. Se comparten modelos con `extra_model_paths.yaml` | Forzar siempre una copia |
| Descarga de modelos | HTTP de `huggingface_hub` (`http_get`) con revisión fijada, archivo `.part` propio y SHA-256 propio | Reanuda entre ejecuciones, admite `HF_TOKEN` y detecta corrupción | `hf_hub_download`: desde la versión 2 borra el parcial al interrumpirse y empieza de cero. Alojar pesos: lo impiden las licencias y el coste |
| Bloqueos entre procesos | `filelock` | Multiplataforma y conserva el comportamiento de liberar el bloqueo si muere el proceso | `fcntl`/`msvcrt` a mano |
| Procesos | `psutil` y archivo de PID | Sustituye `/proc`; permite distinguir la instancia propia de una ajena | Comandos por sistema |
| Logs | Un archivo por proceso con limpieza por antigüedad | Evita renombrar archivos abiertos en Windows | Mantener la rotación compartida |
| Memoria de GPU | `/system_stats` de ComfyUI primero, `nvidia-smi` como apoyo | La API funciona con cualquier fabricante si ComfyUI está activo | Sondas por fabricante |
| Modelos en macOS | GGUF con `ComfyUI-GGUF` | Los fp8 no funcionan en MPS | Parchear ComfyUI: frágil ante actualizaciones. Preparado sin probar: falta validar en un Mac real, y no bloquea nada |
| Servidores de modelos | Opcionales y autodetectados; solo se actúa sobre un servidor que se identifica como tal | No participan en la generación; solo se gestionan para liberar memoria | Instalarlos |
| Herramientas MCP | `create_image` como única vía de generación y edición; sin `generate_image` ni `edit_image` | Medido con 9B: ~750 tokens más por petición y nunca elegidas | Mantenerlos como alias |
| Plazos de los clientes | Progreso cada 5 s y plazo de 1800 s en la entrada de Codex y Hermes | Medido con una herramienta de 330 s: basta para todos los clientes probados | `start_image_job` y `get_job` |
| Idioma | Inglés en la interfaz, la herramienta y el README principal, con README en español | Máximo alcance | Solo español |

## Matriz de PyTorch

Según la documentación de ComfyUI de octubre de 2026. Los valores exactos están fijados en `data/models.toml`.

| Plataforma | Índice de PyTorch | Python | Nivel para la v1 |
|---|---|---|---|
| Linux o Windows, NVIDIA serie 20 o posterior | `cu130` | 3.13 | **1**: objetivo principal |
| Linux o Windows, NVIDIA serie 10 o anterior | `cu126` | 3.12 | 3: experimental |
| macOS con Apple Silicon | Estable fijada desde PyPI (incluye MPS) | 3.13 | 3: preparado sin probar, tras `--experimental` |
| Linux, AMD | `rocm7.2` | 3.13 | 3: experimental |
| Windows 11, AMD | Paquetes ROCm de AMD | 3.13, 64 bits | 3: experimental |
| Linux o Windows, Intel Arc | `xpu` | 3.13 | 3: experimental |
| Solo CPU | `cpu` | 3.13 | 3: solo SDXL Turbo, con aviso de lentitud |

- **Nivel 1:** se prueba en cada versión con hardware real y bloquea el lanzamiento.
- **Nivel 2:** probado con hardware real, con limitaciones documentadas.
- **Nivel 3:** se ofrece con aviso y depende de informes de la comunidad.

## Spike de la fase 3

Fecha: 2026-10-31. Decisión: **instalador propio**. Solo se ha ejecutado en Linux: en Windows únicamente se ha comprobado que existen los mismos paquetes de PyTorch, y queda pendiente de la validación manual.

| Punto | `comfy-cli` 1.24.0 | Instalador propio |
|---|---|---|
| Sin preguntas, con ruta y GPU | Sí: `--skip-prompt`, `--workspace`, `--nvidia`, `--cuda-version 13.0`. La nota anterior de este documento ha quedado obsoleta | Sí |
| Versión fijada | `--commit`, mediante `git checkout` | Archivo de la versión con SHA-256 |
| Git | **Obligatorio** | No hace falta |
| Python del entorno | El de quien lo ejecuta | 3.13 gestionado por uv, verificado con `uv venv --managed-python` |
| Efectos fuera de la instalación | Escribe `~/.config/comfy-cli/` | Ninguno |

- **`uv`:** se confirma el supuesto de encontrarlo en `PATH`. `uvx` puede no estar, así que solo se usa `uv`. Si falta, setup falla antes de descargar y explica cómo instalarlo.
- **Origen de ComfyUI:** archivo de la etiqueta `v0.43.0`, publicada el 2026-10-27. GitHub no garantiza por contrato que el SHA-256 de estos archivos sea estable: si cambiara, setup falla con un error y hay que actualizar el valor fijado.
- **PyTorch:** dos pasos, porque el índice de PyTorch no tiene el resto de dependencias: primero los paquetes fijados con ese índice como predeterminado y después `requirements.txt` desde PyPI.
- **Repositorios renombrados:** `Comfy-Org/flux1-kontext-dev_ComfyUI` es ahora `Comfy-Org/Flux-1-Kontext-Dev` y `Comfy-Org/Lumina_Image_2.0_Repackaged` es `Comfy-Org/Lumina-Image-2`. El manifiesto usa los nombres nuevos; tamaños y SHA-256 coinciden con el análisis.

## Perfiles de modelos

Tamaños medidos. La VRAM mínima sigue siendo orientativa: los picos son de una RTX 4090 de 24 GB (`scripts/measure_profiles.py`, 1024x1024, Linux, 2026-10-31), donde ComfyUI usa la memoria que encuentra. Falta medir en Windows.

| Perfil | Capacidades | Descarga | VRAM orientativa | Pico medido | Tiempo por imagen |
|---|---|---|---|---|---|
| `fast` | Generación rápida con SDXL Turbo | 6,9 GB | Desde 8 GB | 7,0 GB | 1,0 s |
| `quality` | `fast` + FLUX Dev | 24,6 GB | Desde 16 GB | 17,8 GB | 10,4 s |
| `full` | `quality` + edición con Kontext | 36,5 GB | Desde 16 GB | 19,3 GB | 18,6 s |
| `mac-fast` | SDXL Turbo, sin probar | 6,9 GB | Sin medir en MPS | — | — |
| `mac-quality` | `mac-fast` + FLUX Dev GGUF `Q5_K_S`, sin probar | 19,2 GB | Sin medir en MPS | 14,4 GB en NVIDIA | 23,8 s en NVIDIA |
| `mac-full` | `mac-quality` + Kontext GGUF `Q5_K_M`, sin probar | 27,6 GB | Sin medir en MPS | 12,9 GB en NVIDIA | 30,1 s en NVIDIA |

`city96/FLUX.1-dev-gguf` no publica `Q5_K_M`: FLUX Dev usa `Q5_K_S`, la más cercana. Kontext y T5 usan `Q5_K_M`.

## Herramientas de desarrollo

- `pyproject.toml` con `hatchling`, `uv` y `uv.lock`.
- `pytest` sobre los tests actuales y `ruff`, ejecutados en local con `scripts/check.sh`. No se usan GitHub Actions.
- Verificación manual en `ubuntu`, `windows` y `macos` antes de cada versión.
- Prueba de contrato: arrancar ComfyUI en CPU en local y comprobar con `/object_info` que existen todos los nodos que usan los workflows. No requiere descargar modelos.
- Publicación en PyPI con `uv publish` y un token del mantenedor, sin Trusted Publishing porque no hay CI.
