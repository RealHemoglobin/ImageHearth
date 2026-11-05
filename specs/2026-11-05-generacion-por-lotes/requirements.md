# Fase 8: Generación por lotes

## Contexto

Fase 8 del [roadmap](../roadmap.md), cuyo objetivo es que un agente con una lista de imágenes por hacer las pida todas de una vez y el motor las genere en una sola sesión de GPU: descarga los modelos de lenguaje una vez, genera todas las imágenes seguidas en ComfyUI y libera la memoria y restaura los modelos al final. Depende de las fases 5 y 7.

Estado de partida, comprobado el 2026-11-05:

- `create_image` en `server.py` llama a `engine/image_router.create_image`, que valida y delega en `workflow_runner.run_workflow` (generación) o en `kontext.generate` (edición).
- Tanto `run_workflow` como `kontext.generate` abren su propio `generation_session(workflow)` (`engine/orchestrator.py`). Cada imagen repite descarga de modelos de lenguaje, arranque de ComfyUI, `_finish` y restauración.
- `generation_session` ya agrupa el ciclo completo: bloqueo del motor, `_reconcile`, estado de sesión (`state.write`), `_free_server_memory`, arranque de ComfyUI y `_finish`. `session.required_mib` sale de `catalog.required_vram_mib(workflow)`.
- La cancelación usa `engine/progress.py` (`tracker.cancelled`, `raise_if_cancelled`, `GenerationCancelled`); el progreso se envía cada 5 s desde `server.py` con `ctx.report_progress` y el texto de `tracker.stage`.
- `RecoveryRequired` y `recover_engine` funcionan con el estado de sesión de una sola imagen.
- La configuración se lee en `engine/config.py` (variable de entorno, `config.toml`, valor por defecto); `setup` ya acepta `--port`.

## Alcance

Todo lo del roadmap para la fase 8 en una sola rama:

1. **Herramienta:** `create_images` nueva con `items` y valores comunes del lote; `create_image` sin cambios.
2. **Validación previa:** lote homogéneo, límite de elementos, prompts, tamaños, referencias y workflows instalados, todo antes de tocar la GPU.
3. **Configuración:** límite del lote (20 por defecto) en `config.toml`, `setup --batch-limit N` y visible en `doctor`.
4. **Motor:** una sola `generation_session` para el lote, agrupación por workflow, fallos por elemento, cancelación y recuperación.
5. **Respuesta y progreso:** una línea por elemento en el orden pedido y progreso con el número de imagen.
6. **Agentes y documentación:** instrucciones del servidor MCP, skill `imagehearth` y README con el ahorro medido.
7. **Pruebas:** simuladas y reales etiquetadas.

## Fuera de alcance

- `include_image` en `create_images`: no se admite ni con miniaturas. El agente recibe las rutas y abre las que necesite.
- Lotes mezclados de generación y edición: se rechazan.
- Cadenas de ediciones dentro de un lote (un elemento que edita el resultado de otro): siguen siendo llamadas sucesivas.
- Cambios en la firma o el comportamiento de `create_image`.
- Generación paralela dentro de ComfyUI (varias imágenes en la misma cola a la vez o `batch_size` en el latente): las imágenes van una tras otra.
- Trabajos asíncronos (`start_image_job`, `get_job`): ya descartados en `tech-stack.md`.
- Publicar una versión nueva en PyPI.

## Decisiones

| Tema | Decisión |
|---|---|
| Herramienta | `create_images` aparte. `create_image` mantiene su firma simple para los modelos pequeños |
| Campos por elemento | Los mismos que `create_image`: `prompt` (obligatorio), `quality`, `width`, `height`, `negative_prompt`, `image_paths`, `workflow`, `mode` |
| Valores comunes | `quality`, `width`, `height` y `negative_prompt` al nivel del lote; cada elemento los sobrescribe |
| Tipo de lote | Solo generaciones o solo ediciones con Kontext. El tipo se deduce de `mode` y de `image_paths` como en `create_image` (`auto`). Un lote mezclado se rechaza entero, diciendo qué elementos no encajan |
| Validación | Todo el lote antes de tocar la GPU: tipo, límite, prompts, tamaños, rutas de referencia y workflows instalados. Cualquier fallo rechaza el lote entero sin descargar nada, con el índice del elemento (base 1) |
| Límite | 20 elementos por defecto. Clave `batch_limit` en `config.toml` y variable `IMAGEHEARTH_BATCH_LIMIT`, con la prioridad habitual. `setup --batch-limit N` lo escribe junto a `--port`. `doctor` muestra el valor en uso, también en `--json`. Mínimo 1 |
| Sesión | Una sola `generation_session` para el lote. `run_workflow` y `kontext.generate` se separan en una parte que abre la sesión y otra que genera dentro de una sesión ya abierta, para reutilizar el mismo código en `create_image` y en el lote |
| VRAM | `required_mib` del lote = máximo de `catalog.required_vram_mib` de los workflows que contiene. Comprobación de memoria libre una sola vez al principio |
| Orden de ejecución | En generación se agrupa por workflow resuelto (SDXL Turbo, FLUX Dev y sus variantes, SDXL afinado) conservando el orden relativo dentro del grupo; la respuesta sigue el orden pedido. Edición siempre con el workflow de Kontext instalado |
| Semilla y plazo | Cada imagen con su semilla aleatoria y su propio plazo, como ahora |
| Fallos | Un fallo en una imagen se registra en su línea y se sigue. Se aborta el resto si el motor queda inutilizable (ComfyUI caído, `RecoveryRequired`); los elementos no intentados constan como `ERROR: not attempted` con el motivo |
| Cancelación | Se detiene tras la imagen en curso, se conservan y devuelven las ya hechas y `_finish` se ejecuta igual. Los elementos pendientes constan como cancelados |
| Estado de sesión | Registra el lote en curso (total y elemento actual) además de lo que ya guarda, para que `recover_engine` funcione igual que con una imagen |
| Respuesta | Una línea por elemento en el orden pedido: `1: /ruta/imagen.png` o `1: ERROR: motivo`. Advertencias del lote al final con `WARNING:`. Las advertencias de un elemento van en su línea tras la ruta, separadas por ` | WARNING: ` |
| Progreso | `Generating image 3 of 10 (45s)`, con la etapa actual cuando no se está generando (descarga de modelos, arranque de ComfyUI, restauración) |
| `include_image` | Fuera del lote |
| Idioma | Código, mensajes, README y docs en inglés; `specs/` en español |

## Restricciones

- Según la [misión](../mission.md) y `tech-stack.md`, el servidor sigue arrancando sin PyTorch ni ComfyUI, y no se gestiona ningún servidor de modelos fuera de `memory_mode`.
- El lote no puede dejar la GPU ocupada ni los modelos de lenguaje descargados en ningún camino de salida: éxito, fallo parcial, cancelación o excepción.
- El bloqueo del motor se mantiene durante todo el lote; el límite existe para no retenerlo demasiado frente a otros clientes. `LOCK_TIMEOUT` (1800 s) no cambia.
- Progreso al menos cada 5 s, como en `create_image`, para respetar los plazos de los clientes.
- `create_image` debe seguir pasando todos sus tests sin cambios de comportamiento.
- Sin `git commit` por parte del asistente: el usuario revisa y confirma los cambios.

## Entregables

- `create_images` en `server.py`, con su descripción para el agente.
- Router de lotes en `engine/` (validación, agrupación, bucle y respuesta), reutilizando `validation.py`.
- `run_workflow` y `kontext.generate` divididos para poder generar dentro de una sesión abierta.
- `generation_session` que acepta varios workflows (o un `required_mib` calculado) y estado de sesión con el lote en curso.
- Progreso con número de imagen en `engine/progress.py` y `server.py`.
- `batch_limit` en `engine/config.py`, `setup --batch-limit` en `cli.py` y el provisioner, y comprobación en `doctor`.
- Instrucciones de `FastMCP(instructions=...)` y `data/skill/SKILL.md` actualizadas.
- Sección en `README.md` y `README.es.md` con un ejemplo y el ahorro medido; `docs/troubleshooting.md` si hace falta.
- `tech-stack.md` con la decisión de la herramienta de lotes.
- Tests simulados en `tests/` y pruebas reales etiquetadas.
- Roadmap con las tareas hechas marcadas cuando estén verificadas.

## Supuestos abiertos

- **Ahorro esperado:** se supone que el grueso del ahorro está en descargar y restaurar los modelos de lenguaje y en arrancar ComfyUI. Si la medición muestra que la carga de pesos domina, se documenta así en el README.
- **Cambio de pesos entre grupos:** se supone que ComfyUI libera los pesos del grupo anterior al cambiar de workflow sin desbordar la VRAM. Se comprueba en la prueba real `fast` más `high`.
