# Plan: Fase 7

Rama: `feature/adaptacion-hardware`. Sin commits del asistente: los cambios se dejan en el árbol de trabajo para revisión. Los pasos marcados como **mantenedor** no los ejecuta el asistente.

Orden por riesgo: los bloques pequeños y ya explorados primero; la escalera de variantes al final, porque depende de las mediciones.

## 1. `imagehearth-mcp` en el PATH

1. `install.sh`: si el directorio de `uv tool dir --bin` no está en el `PATH`, avisar y ejecutar `uv tool update-shell`.
2. Comprobar en un shell nuevo del usuario (`$SHELL -lc 'command -v imagehearth-mcp'`) que el comando se encuentra; si no, imprimir la orden exacta para su shell (zsh, bash o fish).
3. `install.ps1`: lo mismo con `uv tool update-shell` y una nueva sesión de PowerShell (`Get-Command`).
4. Cubrir `uv` instalado por el instalador oficial, por el gestor del sistema y ya presente.
5. `doctor`: nueva comprobación que dice si el comando está en el `PATH` y, si no, da la orden exacta. Incluirla en `--json`.
6. Tests: ningún `sudo`, aparición de `update-shell` en ambos scripts, `sh -n install.sh` y la comprobación de `doctor` con `PATH` simulado.

## 2. llama-server de un solo modelo que se para y vuelve

1. Módulo de proceso en `platform/`: localizar con `psutil` el proceso que escucha en el puerto de `llamacpp_url`, del mismo usuario y con ejecutable `llama-server`.
2. Descartar servicios del sistema, contenedores y procesos de otro usuario; en ese caso, avisar como ahora.
3. Guardar `exe()`, `cmdline()[1:]`, `cwd()` y `environ()`. Si `environ()` da `AccessDenied`, usar el entorno propio y avisar.
4. En `LlamaCppProvider`, con un solo modelo y `memory_mode = "auto"`: marcarlo como descargable, `terminate()` y esperar a que libere VRAM; `kill()` tras un plazo.
5. Restaurar con `spawn.detached_options()`, salida a un log propio en el directorio de logs, sin consola en Windows. Esperar a que `/props` responda con el mismo modelo.
6. Guardar la línea de arranque en el estado de sesión y relanzar desde `recover_engine` si el motor cayó a mitad.
7. Añadir el `WARNING:` al resultado de la generación.
8. Tests simulados: identificación por `/props`, otro usuario, `AccessDenied`, servicio o contenedor, fallo al relanzar, recuperación tras caída, y `manual`/`off` sin tocar nada.
9. Prueba real en Linux con un `llama-server` y un modelo pequeño. **Mantenedor:** la misma prueba en Windows con el binario oficial.
10. Valorar el mismo enfoque para LM Studio sin API de descarga y vLLM sin modo de reposo, y anotar la conclusión en la evidencia, sin implementarlo.

## 3. Mediciones de memoria de ComfyUI

1. Medir con `scripts/measure_profiles.py` (ampliado si hace falta) cómo carga ComfyUI FLUX fp8 y GGUF en la RTX 4090: nativa y con `--reserve-vram` simulando 16 y 8 GB.
2. Registrar por variante y tamaño: VRAM máxima, RAM máxima, tiempo y si termina o se queda sin memoria, con `NORMAL_VRAM`, `--lowvram` y `--novram`.
3. Fijar con esas cifras los umbrales de la escalera y los `min_vram_mib` de cada perfil, y anotarlas en la evidencia.

## 4. Argumentos de ComfyUI y comprobaciones de memoria

1. Función que elige los argumentos de arranque según VRAM, RAM y sistema (`--reserve-vram`, `--lowvram`, `--novram`), con el caso de ROCm en Windows por separado.
2. Opción `comfy_args` en `config.toml` y variable de entorno, añadida al final de los argumentos elegidos.
3. `doctor` muestra los argumentos efectivos.
4. Revisar `_check_free_memory` y `required_vram_mib`: generar con aviso cuando no cabe en VRAM pero sí en VRAM más RAM libre; rechazar solo si tampoco cabe así. El mensaje dice cuánto falta y de qué.
5. Tests: elección de argumentos por hardware simulado, `comfy_args` que prevalece, y los tres casos de memoria (cabe, cabe con RAM, no cabe).

## 5. SDXL afinado y LoRAs

1. Buscar en Hugging Face checkpoints SDXL 1.0 afinados y LoRAs de detalle con licencia OpenRAIL++ o similar que permita uso comercial y repositorio estable.
2. Elegir uno y anotar en la evidencia candidatos, licencias y motivo.
3. Añadirlos a `models.toml` con revisión, tamaño, SHA-256 y licencia, y a `THIRD_PARTY_NOTICES.md`.
4. Crear `data/workflows/sdxl_quality.json`: checkpoint, LoRAs, más pasos y 1024 de resolución nativa. Añadir sus nodos a la prueba de contrato.

## 6. Escalera de variantes

1. Reorganizar los perfiles `quality` y `full` de Linux y Windows para que sus modelos dependan del tramo de VRAM: fp8, GGUF Q5 con T5 GGUF, o SDXL afinado.
2. `setup`: detectar VRAM y RAM, proponer la variante que cabe, mostrar tamaño y licencias de esa variante y descargar solo esa. Permitir forzar otra con una opción.
3. `VARIANTS["high"]` pasa a `("flux_dev", "flux_dev_gguf", "sdxl_quality")` y `catalog.choose` elige la mejor variante instalada que quepa.
4. `full` por debajo de 12 GB: la edición queda no disponible y el error explica por qué.
5. `list_workflows`, `setup_status` y los errores reflejan la variante instalada.
6. Tests: elección por tramo en `setup` y en `choose`, perfiles por hardware simulado, y edición no disponible en poca VRAM.

## 7. Comparación de calidad y documentación

1. Generar con las tres variantes los mismos prompts y semillas, en la RTX 4090.
2. Documentar en `README.md` y `README.es.md` la escalera, los requisitos medidos (marcando lo simulado) y la comparación.
3. Actualizar `docs/troubleshooting.md` (PATH, poca memoria, llama-server relanzado) y `tech-stack.md`.
4. Actualizar la skill y `FastMCP(instructions=...)` si cambia algún mensaje que el agente deba interpretar.

## 8. Validación en Windows NVIDIA

1. **Mantenedor:** ejecutar `scripts\check.ps1` y `scripts\contract.ps1`.
2. **Mantenedor:** ejecutar `install.ps1` y comprobar el `PATH` en una PowerShell nueva.
3. **Mantenedor:** mediciones de Windows con `scripts/measure_profiles.py` y relanzado de `llama-server` con el binario oficial.
4. Trasladar las cifras al README y a la evidencia.

## 9. Validación local y fusión

1. Ejecutar `scripts/check.sh` y `scripts/contract.sh`.
2. Rellenar la evidencia en [validation.md](validation.md) y marcar en el roadmap lo verificado.
3. **Mantenedor:** revisar, hacer commit y fusionar en `main`.

## 10. Cierre con la AMD de 16 GB

Después de fusionar, cuando esté disponible:

1. **Mantenedor:** en la AMD de 16 GB en Windows, `setup` debe proponer la variante GGUF y `quality` debe generar sin quedarse sin memoria.
2. Ajustar argumentos o umbrales si hace falta, en una rama nueva.
3. Marcar la fase en el roadmap (el usuario revisa antes).
