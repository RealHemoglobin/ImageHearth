# Fase 13: LoRAs para SDXL 1.0

## Contexto

Fase 13 del [roadmap](../roadmap.md). Objetivo: que el agente pueda consultar qué LoRAs hay instaladas para SDXL 1.0 y aplicarlas para conseguir imágenes de ciertas características (fotorrealismo, ilustración, anime, pixel art, acuarela, detalle…), a partir de un catálogo curado que instala ImageHearth. Depende de la [fase 9](../2026-11-06-eleccion-modelo-quality/requirements.md) (modelo de `quality` intercambiable) y de la [fase 11](../2026-11-15-menus-por-numero/requirements.md) (menús por número, incluida la selección múltiple).

Estado de partida, comprobado el 2026-11-15:

- `models.toml` tiene `[[models]]` con `name`, `repo`, `revision`, `filename`, `dest`, `bytes`, `sha256`, `license`, `workflows` y `requires`. No hay sección de LoRAs.
- `sdxl_base` (SDXL 1.0) declara `requires = ["sdxl_offset_lora"]`, y los workflows `sdxl_base.json` y `sdxl_quality.json` (RealVisXL, `legacy`) cargan siempre `sd_xl_offset_example-lora_1.0.safetensors` con un `LoraLoader` a 0,5 (nodo `"2"`), del que cuelgan los `CLIPTextEncode`.
- `create_image` es la única herramienta de generación: `prompt` puede ser una cadena o una lista de cadenas u objetos por elemento (`batch.run`, `batch._merge`). Los campos por elemento son `prompt`, `quality`, `width`, `height`, `negative_prompt`, `style` e `image_paths`.
- `list_workflows` devuelve los workflows instalados y marca el activo de `quality` con `quality_model`, `license` y `commercial_use` (`catalog.active_quality_model`).
- `workflow_runner.prepare_workflow` rellena prompt, negativo, tamaño y nombre; `stamp_png` añade `ImageHearth-Workflow` e `ImageHearth-Quality-Model` como texto PNG.
- `menu.choose_many` existe (fase 11). `quality.plan_change` y `quality.delete_old` borran los pesos del modelo de `quality` anterior al cambiarlo.
- `setup_start` (MCP) acepta `profile`, `accept_licenses`, `existing_comfyui`, `quality_model` e `install_dir`.

## Alcance

Todo lo que pide el roadmap para la fase:

1. **Catálogo** `[[loras]]` en `models.toml` con entre 6 y 10 LoRAs de SDXL 1.0 elegidas y medidas en la implementación.
2. **Instalación** con `setup` (interactivo y `--loras`), `setup_status` y `setup_start`, verificada, registrada y borrada con `uninstall` y al cambiar de modelo de `quality`.
3. **Descubrimiento** desde `list_workflows`.
4. **Generación** con `loras` en `create_image` y en cada elemento de la lista, encadenadas en el workflow, con palabras de activación y metadatos PNG.
5. **Agentes y documentación**: instrucciones del servidor, skill `imagehearth`, README con tabla e imágenes de ejemplo.
6. **Pruebas** simuladas y reales en la RTX 4090.

## Fuera de alcance

- LoRAs elegidas por el usuario (sus archivos en `models/loras`): después de la v1.
- LoRAs para FLUX, SDXL Turbo (`fast`) o RealVisXL (`legacy`).
- LoRAs en la edición (Kontext).
- Una herramienta MCP `list_loras`.
- LoRAs con licencia no comercial o dudosa.
- Quitar o hacer opcional la LoRA de detalle fija (`sdxl_offset_lora`).
- Combinar LoRAs con `workflow` personalizado distinto de `sdxl_base`.

## Decisiones

| Tema | Decisión |
|---|---|
| Selección del catálogo | Se hace en la implementación (tarea 1 del plan): candidatas de Hugging Face con revisión fija, medidas en la RTX 4090 con los mismos prompts y semillas, con y sin LoRA. La elección y lo descartado, con motivo, se documentan en [selección de LoRAs](seleccion-loras.md) dentro de esta carpeta |
| Licencias | Solo con uso comercial y texto claro: OpenRAIL++, CreativeML OpenRAIL-M, Apache-2.0 o MIT. Se descarta cualquier LoRA sin licencia declarada en el repositorio, no comercial o con restricciones dudosas |
| Cobertura | Entre 6 y 10 LoRAs con estilos distintos; como mínimo fotorrealismo, ilustración, anime, pixel art, acuarela y detalle, si existe una candidata válida para cada una. Si alguna categoría no tiene candidata válida, se documenta y no se rellena con otra dudosa |
| Formato del catálogo | `[[loras]]` en `models.toml`: `name` (corto, en minúsculas con guiones), `description` (inglés, una línea), `category`, `trigger_words` (lista, puede ser vacía), `weight` (recomendado), `base = "sdxl"`, `repo`, `revision`, `filename`, `dest` (`loras/...`), `bytes`, `sha256` y `license` |
| Modelo compatible | Solo con el modelo de `quality` SDXL 1.0 (workflow `sdxl_base`) y `quality: "high"`. Con FLUX, `fast`, edición o RealVisXL `legacy`: error claro antes de tocar la GPU que dice por qué y qué modelo las admite |
| Instalación por defecto | Ninguna salvo que se elijan. Interactivo: selección múltiple (`menu.choose_many`) sin marcar al instalar SDXL, con categoría, tamaño y licencia de cada una. No interactivo y `setup_start`: ninguna si no se pasa `--loras`/`loras` |
| `--loras` | `--loras a,b`, `--loras all` o `--loras none`. Sobre una instalación existente con SDXL 1.0, **fija el conjunto**: descarga las que faltan y borra las que sobran, sin tocar nada más. Sin `--loras` no se cambian. En interactivo sobre una instalación existente, la selección sale con las instaladas ya marcadas. Nombre desconocido: error con los nombres válidos. Con un modelo de `quality` que no es SDXL 1.0: error de argumentos |
| Descarga y registro | Mismo mecanismo que el resto de modelos (reanudable, `HF_TOKEN`, tamaño y SHA-256), con comprobación de espacio previa, y registradas en el manifiesto de instalación como modelos propios para que `uninstall`, `update --move-to` y `doctor` las traten igual |
| Cambio de modelo de `quality` | Al pasar de SDXL 1.0 a FLUX se borran las LoRAs del catálogo instaladas, y el resumen del cambio lo dice |
| MCP de instalación | `setup_status` devuelve el catálogo (nombre, descripción, categoría, tamaño, licencia) y cuáles están instaladas. `setup_start(loras=[])` acepta la lista o `["all"]`; vacía no instala ninguna (y en una instalación existente, no cambia nada). Las instrucciones piden al agente que pregunte al usuario si quiere LoRAs al elegir SDXL |
| Descubrimiento | Campo `loras` en el item de `list_workflows` del workflow `sdxl_base` cuando es el activo: lista de `{name, description, category, trigger_words, weight}` de las instaladas. Sin herramienta nueva. Sin LoRAs instaladas, lista vacía. Con FLUX activo no aparece el campo |
| Parámetro `loras` | En `create_image` y en cada objeto de la lista: `loras=["pixel-art", {"name": "watercolor", "weight": 0.6}]`. Un nombre solo usa el peso recomendado. Peso entre 0 y 2 (fuera de rango: error). Máximo 3 por imagen, sin repetir nombre. La LoRA de detalle fija no cuenta. Con lista de prompts, el `loras` común se aplica a los elementos que no lo indiquen, igual que el resto de campos |
| Errores de nombre | Nombre desconocido o no instalado: error que lista las instaladas y, si la pedida existe en el catálogo, el comando `imagehearth-mcp setup --loras ...` para instalarla. En lote se valida todo antes de generar, como hoy |
| Construcción del workflow | `LoraLoader` encadenados detrás del nodo `"2"` (detalle fija) y antes de los `CLIPTextEncode` y el muestreador, con `strength_model` y `strength_clip` iguales al peso. Sin LoRAs, el workflow es idéntico al de hoy |
| Palabras de activación | Se añaden al principio del prompt las que no estén ya (comparación sin distinguir mayúsculas). Se aplica después de `style`; si la LoRA es de un medio no fotográfico, `style: "auto"` no añade pistas fotográficas (las palabras de activación cuentan como petición de otro medio) |
| Metadatos PNG | Texto `ImageHearth-LoRAs` con `nombre:peso` separados por comas, solo si se usó alguna |
| `doctor` | Lista las LoRAs instaladas y avisa si falta o no coincide algún archivo registrado |
| Imágenes del README | JPG de unos 512 px y menos de 100 KB cada una en `docs/images/loras/`, generadas en la RTX 4090 con el mismo prompt y semilla, con y sin LoRA, versionadas en el repositorio |
| Idioma | Interfaz, descripciones del catálogo y mensajes en inglés, como el resto de la CLI y del servidor |

## Restricciones

- Sin `loras` el comportamiento y los workflows son idénticos a hoy, y `setup` sin `--loras` no instala ni borra ninguna.
- Antes de la confirmación final, `setup` no escribe nada en disco.
- Los errores de LoRA se dan antes de tocar la GPU, de parar modelos de lenguaje o de arrancar ComfyUI.
- Nunca se borra un archivo de `models/loras` que ImageHearth no registró como propio.
- Las descripciones y la forma de `list_workflows` deben ser comprensibles para modelos locales pequeños: campos cortos y sin anidar más de lo necesario.
- Funciona en Linux y Windows; macOS preparado sin probar.
- Solo biblioteca estándar más las dependencias actuales.
- Los tests simulados no tocan el `HOME` real ni descargan nada.
- Sin commits del asistente.

## Entregables

- `data/models.toml`: sección `[[loras]]` con el catálogo elegido.
- Carga y validación del catálogo de LoRAs (en `provisioner/manifest.py` o módulo nuevo `engine/loras.py` compartido por motor y provisión).
- `setup.py`, `cli.py`, `quality.py`, `install_manifest.py`, `maintenance.py` (`uninstall`), `doctor.py` y `agent_setup.py` actualizados.
- `server.py`: `loras` en `create_image`, campo `loras` en `list_workflows`, instrucciones y docstrings.
- `engine/image_router.py`, `engine/batch.py` y `engine/workflow_runner.py`: validación, cadena de `LoraLoader`, palabras de activación y metadatos.
- Skill `imagehearth` actualizada.
- Tests nuevos en `tests/test_loras.py` y ampliaciones de `tests/test_batch.py`, `tests/test_provisioner.py`, `tests/test_quality_model.py` y `tests/test_agent_setup.py`.
- `README.md`, `README.es.md`, `llms-install.md`, `THIRD_PARTY_NOTICES.md` y `docs/images/loras/`.
- [Selección de LoRAs](seleccion-loras.md) con candidatas, mediciones y decisión.
- Evidencia en [validation.md](validation.md).
