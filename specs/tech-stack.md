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
   ├─ platform     procesos, bloqueos y memoria de GPU por sistema
   ├─ provisioner  detección, instalación, manifiesto, doctor
   └─ cli          setup, doctor, connect, models, update, uninstall
   │ HTTP local
   ▼
ComfyUI ─ entorno propio con PyTorch, gestionado o existente
   └─ nodo imageengine_status
   │ opcional
   ▼
Ollama ─ solo si ya está presente
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
| Instalar ComfyUI | Instalador propio con versión fijada | Reproducible, con control de ruta y sin Git. Hoy `comfy-cli` no documenta flags de ruta ni de GPU para instalar sin preguntas | `comfy-cli`: reevaluar en el spike de la fase 3 |
| ComfyUI existente | Se detecta y se ofrece **adjuntar** | Evita duplicar decenas de GB. Se comparten modelos con `extra_model_paths.yaml` | Forzar siempre una copia |
| Descarga de modelos | `huggingface_hub` con revisión fijada y SHA-256 propio | Reanuda descargas, admite `HF_TOKEN` y detecta corrupción | Alojar pesos: lo impiden las licencias y el coste |
| Bloqueos entre procesos | `filelock` | Multiplataforma y conserva el comportamiento de liberar el bloqueo si muere el proceso | `fcntl`/`msvcrt` a mano |
| Procesos | `psutil` y archivo de PID | Sustituye `/proc`; permite distinguir la instancia propia de una ajena | Comandos por sistema |
| Logs | Un archivo por proceso con limpieza por antigüedad | Evita renombrar archivos abiertos en Windows | Mantener la rotación compartida |
| Memoria de GPU | `/system_stats` de ComfyUI primero, `nvidia-smi` como apoyo | La API funciona con cualquier fabricante si ComfyUI está activo | Sondas por fabricante |
| Modelos en macOS | GGUF con `ComfyUI-GGUF` | Los fp8 no funcionan en MPS | Parchear ComfyUI: frágil ante actualizaciones. Pendiente de validar en un Mac real |
| Ollama | Opcional y autodetectado | No participa en la generación; solo se gestiona para liberar memoria | Instalarlo |
| Idioma | Inglés en la interfaz, la herramienta y el README principal, con README en español | Máximo alcance | Solo español |

## Matriz de PyTorch

Según la documentación de ComfyUI de octubre de 2026. Fijar los valores exactos en el manifiesto al implementar.

| Plataforma | Índice de PyTorch | Python | Nivel para la v1 |
|---|---|---|---|
| Linux o Windows, NVIDIA serie 20 o posterior | `cu130` | 3.13 | **1**: objetivo principal |
| Linux o Windows, NVIDIA serie 10 o anterior | `cu126` | 3.12 | 3: experimental |
| macOS con Apple Silicon | Nightly con Metal | 3.13 | 2: tras la validación en un Mac |
| Linux, AMD | `rocm7.2` | 3.13 | 3: experimental |
| Windows 11, AMD | Paquetes ROCm de AMD | 3.13, 64 bits | 3: experimental |
| Linux o Windows, Intel Arc | `xpu` | 3.13 | 3: experimental |
| Solo CPU | `cpu` | 3.13 | 3: solo SDXL Turbo, con aviso de lentitud |

- **Nivel 1:** se prueba en cada versión con hardware real y bloquea el lanzamiento.
- **Nivel 2:** probado con hardware real, con limitaciones documentadas.
- **Nivel 3:** se ofrece con aviso y depende de informes de la comunidad.

## Perfiles de modelos

Tamaños medidos. La VRAM es orientativa y debe medirse en la fase 4: solo hay datos de una RTX 4090.

| Perfil | Capacidades | Descarga | VRAM orientativa |
|---|---|---|---|
| `fast` | Generación rápida con SDXL Turbo | 6,9 GB | Desde 8 GB |
| `quality` | `fast` + FLUX Dev | 24,5 GB | Desde 16 GB |
| `full` | `quality` + edición con Kontext | 36,5 GB | Desde 16 GB |
| `mac-*` | Equivalentes en GGUF | Por definir | Por definir |

## Herramientas de desarrollo

- `pyproject.toml` con `hatchling`, `uv` y `uv.lock`.
- `pytest` sobre los tests actuales, `ruff` y GitHub Actions.
- CI en `ubuntu`, `windows` y `macos`.
- Prueba de contrato: arrancar ComfyUI en CPU en CI y comprobar con `/object_info` que existen todos los nodos que usan los workflows. No requiere descargar modelos.
- Publicación en PyPI con Trusted Publishing, sin tokens guardados.
