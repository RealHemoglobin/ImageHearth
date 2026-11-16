# Fase 15: Nuevos modelos de generación

## Contexto

Fase 15 del [roadmap](../roadmap.md). Objetivo: añadir como opciones instalables los modelos elegidos en la [fase 14](../2026-11-15-analisis-modelos/analysis.md) (sección 9, decisión del 2026-11-16): Z-Image-Turbo, FLUX.2 Klein 4B (genera y edita), Chroma1-HD, Qwen-Image, HiDream-I1 Full y Qwen-Image-Edit-2511, con las precisiones medidas. Depende de la [fase 9](../2026-11-06-eleccion-modelo-quality/requirements.md) (modelo de `quality` intercambiable), la [fase 11](../2026-11-15-menus-por-numero/requirements.md) (menús), la [fase 13](../2026-11-15-loras-sdxl/requirements.md) (LoRAs de SDXL) y la [fase 14](../2026-11-15-analisis-modelos/requirements.md) (análisis y selector múltiple con flechas).

**Cambio de alcance respecto al roadmap (decisión del usuario, 2026-11-16):** el roadmap decía que solo hay un modelo de `quality` instalado y que la interfaz del agente no cambia. Ahora **cada capacidad admite varios modelos instalados a la vez**, el usuario los elige con selección múltiple y el agente puede escoger cuál usar con un parámetro nuevo y opcional `model`. Sin `model`, todo funciona como hoy con el modelo predeterminado de cada capacidad.

Estado de partida, comprobado el 2026-11-16:

- `data/models.toml` tiene `[[models]]` (pesos), `[[loras]]`, `[profiles.*]` (`fast`, `quality`, `full` y los `mac-*`), `[quality_models.*]` (`flux-dev`, `flux-schnell`, `sdxl`, cada uno con `[[options]]` por precisión: `precision`, `min_vram_mib`, `workflow`, `models`, `nodes`) y `[[edit.options]]` (Kontext fp8 y GGUF). `ComfyUI-GGUF` ya está en `[nodes.comfyui-gguf]`.
- `engine/catalog.py` tiene `VARIANTS` por capacidad (`fast`, `high`, `edit`) y `active_quality_model()`; solo hay un modelo de `quality` activo.
- `create_image` acepta `prompt` (cadena o lista de cadenas u objetos), `mode`, `quality`, `image_paths`, `workflow`, `width`, `height`, `negative_prompt`, `include_image`, `style` y `loras`.
- `list_workflows` devuelve los workflows instalados y marca el activo de `quality` con `quality_model`, `license`, `commercial_use` y, si es SDXL 1.0, `loras`.
- `setup` tiene `--profile`, `--quality-model`, `--loras`, `--variant`, `--yes`, etc.; `setup_start` acepta `profile`, `accept_licenses`, `existing_comfyui`, `quality_model`, `install_dir` y `loras`. `menu.choose_many` ya usa flechas, espacio y Enter.
- `quality.plan_change` y `quality.delete_old` cambian el modelo de `quality` descargando antes de borrar.
- `scripts/measure_models/` tiene un workflow probado por modelo (y `-gguf`) y `registry.json` con repositorio, ruta y carpeta de cada peso. Las mediciones (tiempo y VRAM por nivel) están en `specs/2026-11-15-analisis-modelos/measurements/*.json`.

## Alcance

1. **Catálogo por capacidad** con varios modelos por capacidad: `fast`, `quality` (`high`) y edición.
2. **Modelos nuevos** en `models.toml` con un workflow por modelo y cargador, solo en las precisiones medidas.
3. **Instalación múltiple** con `setup` (interactivo y no interactivo), `setup_status` y `setup_start`, con resumen de espacio en disco antes de confirmar.
4. **Elección en la generación**: parámetro `model` en `create_image` y en cada elemento de la lista, con predeterminado por capacidad.
5. **Descubrimiento**: el agente ve los modelos instalados, su capacidad, licencia, tiempo medido y si editan.
6. **Migración** de las instalaciones existentes (un modelo de `quality`, Kontext, SDXL Turbo) sin volver a descargar.
7. **Documentación** y **pruebas** simuladas y reales rápidas.

## Fuera de alcance

- Precisiones no medidas: HiDream fp16 y Qwen-Edit bf16 no se ofrecen.
- Modelos descartados en la fase 14 (FLUX.2 dev, Klein 9B, Qwen-Image 2.1, SD3.5, HunyuanImage 2.1) y los no revisados.
- Varias precisiones del mismo modelo instaladas a la vez.
- LoRAs para modelos distintos de SDXL 1.0.
- Cambios en los perfiles `mac-*` más allá de que sigan cargando (macOS sigue preparado sin probar).
- Mediciones nuevas: los tiempos y VRAM que muestra `setup` son los de `analysis.md`.
- Pruebas reales del asistente con los modelos grandes (las hace el usuario).

## Decisiones

| Tema | Decisión |
|---|---|
| Modelos por capacidad | **fast:** SDXL Turbo, Z-Image-Turbo y FLUX.2 Klein 4B (menos de 5 s medidos). **quality:** SDXL 1.0, FLUX.1 Dev, FLUX.1 Schnell, Chroma1-HD, Qwen-Image e HiDream-I1 Full. **Edición:** FLUX.1 Kontext Dev, FLUX.2 Klein 4B y Qwen-Image-Edit-2511 |
| Nombres | Cortos en minúsculas con guiones, estables y usados en CLI, MCP y metadatos: `sdxl-turbo`, `z-image-turbo`, `klein-4b`, `sdxl`, `flux-dev`, `flux-schnell`, `chroma-hd`, `qwen-image`, `hidream-full`, `kontext`, `qwen-image-edit`. Los de la fase 9 no cambian |
| Precisiones ofrecidas | Z-Image-Turbo int8 y bf16; Klein 4B bf16; Chroma1-HD fp8 y bf16; Qwen-Image Q2_K, Q4_K_M, fp8 y bf16; HiDream-I1 Full Q4_K_M y fp8; Qwen-Image-Edit-2511 Q4_K_M y fp8. Las existentes (FLUX.1 fp8/GGUF, Kontext fp8/GGUF, SDXL fp16) se mantienen |
| Selección múltiple | En **cada** capacidad que incluya el perfil (`fast`, `quality`, `full`) el usuario marca uno o varios modelos con `menu.choose_many` (flechas, espacio, Enter). `full` añade la selección de edición. Al menos uno por capacidad incluida |
| Precisión | Una por modelo. Tras marcar los modelos, por cada uno con más de una precisión el usuario elige la precisión en un menú que muestra, por opción, tamaño de descarga, tiempo por imagen y VRAM medidos para su nivel, y marca la recomendada (la de más calidad que cabe sin descarga a RAM). Cambiar de precisión reemplaza la anterior: descarga antes de borrar |
| Predeterminado | Uno por capacidad. Si hay un solo modelo, es ese. Si hay varios, `setup` pregunta cuál es el predeterminado y propone el recomendado para la GPU. En no interactivo, el primero de la lista. `create_image` sin `model` usa el predeterminado de la capacidad pedida |
| Recomendación por nivel | Según `analysis.md` (sección 8) para los nuevos y la fase 9 para los existentes. fast: Klein 4B en 8 GB, Z-Image-Turbo bf16 desde 16 GB. quality: Chroma1-HD fp8 en 8 GB, Qwen-Image Q4_K_M en 16 GB, Qwen-Image fp8 en 24 y 32+ GB. Edición: Klein 4B en 8 y 16 GB, Qwen-Image-Edit-2511 fp8 en 24 y 32+ GB. La recomendación se marca y preselecciona, pero se puede elegir cualquier opción. Tabla confirmada por el usuario el 2026-11-16 |
| Preselección | En una instalación nueva sale marcado solo el recomendado de cada capacidad. En una existente salen marcados los instalados |
| Resumen de espacio | Antes de confirmar, `setup` muestra cada modelo y precisión elegidos con su tamaño, lo que se descarga, lo que se borra (y por qué) y el total frente al espacio libre en la carpeta de modelos; si no cabe, lo dice y no deja confirmar. Igual en `setup_status`/`setup_start` |
| Componentes compartidos | Los pesos compartidos (Klein 4B en `fast` y edición, codificador Qwen3-4B de Z-Image y Klein, T5/VAE de FLUX con Chroma, codificador de Qwen-Image con Qwen-Edit) se descargan una vez y solo se borran cuando ningún modelo instalado los usa |
| Conjunto fijo | Como `--loras` en la fase 13: sobre una instalación existente, lo elegido fija el conjunto de cada capacidad. Descarga lo que falta, borra lo que sobra (solo lo registrado por ImageHearth) y no toca las capacidades que no se pasan |
| CLI | `--fast-models`, `--quality-models` y `--edit-models`, cada uno con `nombre[:precisión]` separados por comas; el primero es el predeterminado. Sin precisión, la recomendada. `--quality-model` se mantiene como alias de `--quality-models` con un nombre. Nombre o precisión desconocidos: error con los válidos |
| MCP de instalación | `setup_status` devuelve, por capacidad, el catálogo (nombre, título, precisiones con tamaño, tiempo y VRAM medidos para el nivel de la GPU, licencia, uso comercial, recomendado, instalados y predeterminado). `setup_start` acepta `fast_models`, `quality_models` y `edit_models` (listas de `nombre[:precisión]`, el primero predeterminado); `quality_model` se mantiene. Lista vacía u omitida: no cambia esa capacidad |
| Parámetro `model` | Opcional en `create_image` y en cada objeto de la lista (el común se aplica a los elementos que no lo indiquen). Debe ser un modelo instalado de la capacidad que resulta de `quality`/`mode` (o de edición si hay `image_paths`). Error antes de tocar la GPU si no está instalado, si no tiene esa capacidad o si se combina con `workflow`; el error lista los instalados de esa capacidad y, si está en el catálogo, el comando para instalarlo |
| Descubrimiento | `list_workflows` devuelve un item por modelo instalado con `model`, `capability` (`fast`, `high`, `edit`), `precision`, `default`, `license`, `commercial_use`, `seconds` (tiempo medido para el nivel de la GPU) y, en SDXL 1.0, `loras`. Campos cortos y planos para modelos locales pequeños. Las instrucciones del servidor y la skill dicen que se llame si el usuario pide un modelo concreto o hay varios |
| LoRAs | Solo con `model` = `sdxl` (o `sdxl` predeterminado de `high`). `--loras` exige `sdxl` entre los modelos de `quality`; al quitar `sdxl` se borran las LoRAs, como al cambiar a FLUX en la fase 13 |
| Licencia de HiDream | Su codificador Llama 3.1 exige mostrar la licencia de Meta: aparece en el consentimiento de licencias y en no interactivo requiere `--accept-licenses`/`accept_licenses`. Si el repositorio exige aprobación o token, error claro con `HF_TOKEN` |
| Nodos | Preferir nodos nativos de ComfyUI 0.43.0; los GGUF usan `ComfyUI-GGUF` (ya fijado). Todo nodo nuevo entra en la prueba de contrato |
| Motor | Cada modelo es una entrada del manifiesto y uno o más workflows; el motor no tiene lógica por modelo más allá de `build_workflow`. `VARIANTS` pasa a derivarse del catálogo |
| Migración | Una instalación existente se lee como conjunto: SDXL Turbo en `fast`, su modelo de `quality` en `quality` y Kontext (si `full`) en edición, todos predeterminados. No se descarga ni se borra nada al actualizar |
| Metadatos PNG | Texto `ImageHearth-Model` con `nombre:precisión`; `ImageHearth-Quality-Model` se mantiene por compatibilidad cuando aplica |
| `doctor` | Lista los modelos instalados por capacidad con su precisión y el predeterminado, y avisa si falta o no coincide algún archivo |
| Idioma | Interfaz, mensajes y descripciones en inglés, como el resto de la CLI y el servidor |

## Restricciones

- Sin `model`, la generación usa el predeterminado de cada capacidad y, en una instalación migrada, el resultado es idéntico al de hoy.
- Antes de la confirmación final, `setup` no escribe nada en disco.
- Los errores de `model` se dan antes de tocar la GPU, de parar modelos de lenguaje o de arrancar ComfyUI; en un lote se valida todo antes de generar.
- Nunca se borra un archivo que ImageHearth no registró como propio, ni un componente que use otro modelo instalado.
- Funciona en Linux y Windows; macOS preparado sin probar.
- Solo biblioteca estándar más las dependencias actuales.
- Los tests simulados no tocan el `HOME` real ni descargan nada.
- Sin commits del asistente.

## Entregables

- `data/models.toml`: pesos nuevos (`[[models]]` con revisión, SHA-256, tamaño, licencia), catálogo por capacidad con opciones por precisión y datos medidos (tiempo y VRAM por nivel), licencias nuevas (Llama 3.1 y las que falten).
- `data/workflows/`: un workflow por modelo y cargador (`*_gguf` cuando cambia), a partir de `scripts/measure_models/`.
- `provisioner/manifest.py`, `quality.py` (o un módulo de selección por capacidad), `setup.py`, `cli.py`, `install_manifest.py`, `maintenance.py`, `doctor.py` y `agent_setup.py` actualizados.
- `engine/catalog.py`, `engine/image_router.py`, `engine/batch.py`, `engine/workflow_runner.py` y `engine/loras.py`: catálogo por capacidad, `model`, predeterminados y metadatos.
- `server.py`: `model` en `create_image`, `list_workflows`, `setup_status`, `setup_start`, instrucciones y docstrings.
- Skill `imagehearth`, `README.md`, `README.es.md`, `llms-install.md`, `THIRD_PARTY_NOTICES.md`.
- `scripts/contract.py` con los nodos nuevos.
- Tests nuevos y ampliados.
- Roadmap: fase 15 actualizada con el cambio de alcance (varios modelos por capacidad y `model`) y tareas marcadas.
- Evidencia en [validation.md](validation.md).

## Supuestos abiertos

- Revisiones y SHA-256 exactos se fijan al descargar, como en la fase 14; si un repositorio cambió desde la medición, se usa la revisión medida.
