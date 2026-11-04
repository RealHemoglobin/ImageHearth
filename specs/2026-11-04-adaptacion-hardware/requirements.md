# Fase 7: Adaptación al hardware

## Contexto

Fase 7 del [roadmap](../roadmap.md), cuyo objetivo es que cada equipo obtenga la mejor calidad que cabe en su hardware, aunque vaya más lento, y que los modelos de lenguaje del usuario se aparten y vuelvan sin intervención. Depende de las fases 4, 5 y 6.

Estado de partida, comprobado el 2026-11-04:

- En una AMD de 16 GB en Windows, FLUX Dev fp8 (12 GB de modelo y 5 GB de T5) va muy justo.
- `models.toml` tiene `quality` y `full` con `min_vram_mib = 16000` y solo FLUX Dev fp8 para Linux y Windows. Los workflows GGUF (`flux_dev_gguf`, `flux_kontext_dev_gguf`) existen, pero solo los usan los perfiles de Mac.
- `VARIANTS` en `engine/catalog.py` elige la primera variante del sistema que conoce, sin mirar memoria.
- `_check_free_memory` en `engine/orchestrator.py` rechaza la generación si la VRAM libre es menor que `min_vram_mib`, aunque ComfyUI pudiera cargar por partes.
- `LlamaCppProvider` descarga y restaura en modo router, verificado contra un servidor real. Con un solo modelo devuelve `unloadable: False` y el motor solo avisa.
- `install.sh` e `install.ps1` solo sugieren `uv tool update-shell` si el directorio de herramientas no está en el `PATH`.
- El spike de llama.cpp del roadmap ya validó el relanzado con `psutil` en Linux.

## Alcance

Los cuatro bloques del roadmap en una sola rama:

1. **Instalación:** `imagehearth-mcp` queda en el `PATH` tras instalar, y `doctor` lo comprueba.
2. **llama.cpp de un solo modelo:** parar y relanzar `llama-server` igual que estaba.
3. **Memoria de ComfyUI:** argumentos de arranque según hardware, `comfy_args` y comprobaciones de memoria que admiten descarga parcial a RAM.
4. **Variantes de `quality`:** escalera fp8 / GGUF Q5 / SDXL afinado elegida por VRAM y RAM.

## Fuera de alcance

- Validar en la AMD de 16 GB en Windows: llega después de fusionar y queda como criterio de cierre de la fase, no de fusión.
- Validar en una GPU real de 8 GB: se simula con `--reserve-vram` en la RTX 4090.
- macOS como soportado: lo propio de macOS se cubre con tests simulados y sigue tras `--experimental`.
- LM Studio y vLLM con relanzado de proceso: solo se valora y se documenta la conclusión.
- LoRAs elegidas por el usuario y otros modelos (después de la v1).
- Publicar una versión nueva en PyPI.

## Decisiones

| Tema | Decisión |
|---|---|
| Orden | Por riesgo: PATH y llama-server primero (pequeños y con spike hecho), luego memoria de ComfyUI y al final la escalera de variantes, que depende de las mediciones |
| Elección de variante | `setup` propone y descarga solo la variante de `quality` que cabe según VRAM y RAM. El perfil `quality` (y `full`) sigue siendo uno, con modelos según hardware. Al generar se usa la mejor variante instalada que quepa |
| Umbrales de la escalera | 20 GB o más: FLUX Dev fp8. De 12 a 20 GB: FLUX Dev GGUF Q5 con T5 GGUF y descarga parcial si hace falta. De 8 a 12 GB: SDXL 1.0 afinado con LoRAs de detalle, sin T5. Los límites se ajustan con las mediciones de la tarea de memoria |
| Edición en poca VRAM | `full` usa Kontext GGUF en el tramo de 12 a 20 GB. Por debajo de 12 GB la edición se marca como no disponible, con un error que lo explica |
| SDXL y LoRAs | Se eligen durante la implementación: licencia que permita uso comercial (OpenRAIL++ o similar), calidad y origen estable en Hugging Face, con revisión y SHA-256 fijados en `models.toml`. La elección y su motivo se anotan en la evidencia |
| Parar llama-server | Activo por defecto en `memory_mode = "auto"`, con un `WARNING:` en el resultado. Nunca en `manual` ni `off` |
| Qué se puede parar | Solo un proceso del mismo usuario, identificado como `llama-server` por nombre de ejecutable y por `/props` en el puerto configurado. Si es un servicio del sistema, un contenedor, de otro usuario o no se puede leer su arranque, se avisa como ahora |
| Cómo se relanza | `exe()`, `cmdline()[1:]`, `cwd()` y `environ()` guardados; relanzado con `spawn.detached_options()` y salida a un log propio. En Windows sin consola visible. Si `environ()` da `AccessDenied`, se usa el entorno propio y se avisa |
| Persistencia | La línea de arranque se guarda en el estado de sesión, para que `recover_engine` relance el servidor tras una caída del motor |
| Argumentos de ComfyUI | El motor elige `--reserve-vram`, `--lowvram` o `--novram` según VRAM, RAM y sistema. `comfy_args` en `config.toml` se añade al final y prevalece. `doctor` muestra los argumentos efectivos |
| Límite de memoria | Si la VRAM libre no basta pero VRAM libre más RAM libre sí, se genera con aviso de que irá más lento. Solo se rechaza si tampoco cabe con la RAM |
| PATH | `install.sh` e `install.ps1` ejecutan `uv tool update-shell` avisando antes, y comprueban en un shell nuevo que `imagehearth-mcp` se encuentra. Si no, imprimen la orden exacta |
| Idioma | Código, mensajes, README y docs en inglés; `specs/` en español |

## Restricciones

- Según la [misión](../mission.md), solo se anuncia como soportado lo probado con hardware real. Las variantes de 8 y 16 GB constan como simuladas hasta probarlas en tarjetas reales.
- Nunca se para ni se mata un proceso ajeno al usuario, ni un ComfyUI no gestionado, tal como exige la fase 2.
- Los instaladores no piden `sudo` ni elevación, y no aceptan licencias por el usuario.
- `setup` sigue mostrando espacio y licencias antes de descargar, también para los modelos nuevos.
- El servidor sigue arrancando sin PyTorch ni ComfyUI.
- Los pesos de modelos no se redistribuyen.
- Sin `git commit` por parte del asistente: el usuario revisa y confirma los cambios.

## Entregables

- `install.sh` e `install.ps1` que dejan `imagehearth-mcp` en el `PATH` en zsh, bash, fish y PowerShell.
- Comprobación de `PATH` en `doctor`, con la orden exacta para arreglarlo.
- Relanzado de `llama-server` de un solo modelo en `LlamaCppProvider` (o un módulo de proceso en `platform/`), con estado persistido y recuperación.
- Elección de argumentos de ComfyUI según hardware y opción `comfy_args`.
- Comprobaciones de memoria revisadas (`min_vram_mib`, `_check_free_memory`) con la RAM como segundo límite.
- `models.toml` con modelos y perfiles por tramo de VRAM, incluidos el checkpoint SDXL y las LoRAs.
- Workflow `sdxl_quality.json` e inclusión en `VARIANTS["high"]`.
- `setup` y `catalog.choose` que eligen la variante por hardware.
- Mediciones de tiempo y memoria por variante en la RTX 4090 (nativa y simulando 16 y 8 GB) y en Windows NVIDIA.
- Comparación de calidad de las tres variantes con los mismos prompts, en el README.
- Tests de todo lo anterior y docs actualizadas (`README.md`, `README.es.md`, `docs/troubleshooting.md`, `tech-stack.md`).
- Roadmap con las tareas hechas marcadas cuando estén verificadas.

## Supuestos abiertos

- **Descarga parcial en ROCm Windows:** no se puede comprobar hasta tener la AMD. Se implementa por los mismos argumentos que en CUDA y se valida al cerrar la fase.
- **Umbrales exactos:** 12 y 20 GB son orientativos y pueden moverse con las mediciones de la tarea 3 del [plan](plan.md).
- **Simulación de 8 y 16 GB:** se supone que `--reserve-vram` en la RTX 4090 reproduce el comportamiento de una tarjeta de ese tamaño. El ancho de banda y la velocidad no se reproducen, así que los tiempos medidos no valen para el README.
