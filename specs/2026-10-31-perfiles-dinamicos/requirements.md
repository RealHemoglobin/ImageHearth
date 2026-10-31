# Fase 4: Perfiles dinámicos y macOS preparado

## Contexto

Fase 4 del [roadmap](../roadmap.md), cuyo objetivo es que el hardware decida qué se ofrece y que nada se anuncie sin haberlo probado. No hay Mac disponible ni previsto, así que macOS se deja preparado **sin probar** y no bloquea ninguna fase posterior. Probarlo queda para cuando haya un Mac o alguien de la comunidad informe.

Estado de partida, comprobado el 2026-10-31:

- `setup` permite instalar solo `fast`, `quality` o `full`, pero el motor no lo tiene en cuenta.
- `validation.available_workflows()` lista los JSON de `data/workflows`, que siempre están, tengan o no sus modelos.
- `image_router.create_image` y `kontext.generate` lanzan la generación sin comprobar los modelos. Si faltan, el fallo llega desde ComfyUI y no dice qué perfil instalar.
- `kontext.build_workflow` usa identificadores de nodo fijos, como `192:39` o `136`, también para enlazar el VAE y los nodos que añade.
- `provisioner/manifest.py` y `models.inspect` ya cruzan `models.toml` con el disco. `doctor` resuelve la carpeta de modelos con `records.models_dir` y, si no hay, con `config.COMFY_DIR / "models"`.
- `tech-stack.md` marca la VRAM como orientativa, con datos solo de una RTX 4090.
- `detect.py` clasifica macOS como `metal`, nivel 2 y sin soporte, y `setup` lo rechaza. `models.toml` no tiene `pytorch.metal`, perfiles `mac-*` ni modelos GGUF.

## Alcance

- **Catálogo dinámico:** `list_workflows`, `quality` y los errores se basan en lo instalado. Un error dice qué perfil instalar.
- **Separación del cargador:** `build_workflow` deja de depender de identificadores de nodo fijos y aísla el cargador de modelo.
- **Mediciones:** VRAM y tiempo reales por workflow y perfil, con un script reproducible, documentados en ambos README y en `tech-stack.md`.
- **macOS preparado sin probar:** PyTorch para Metal, nodo `ComfyUI-GGUF` fijado, modelos GGUF con hashes fijados, perfiles `mac-*`, workflows GGUF, y `setup`, `doctor` y motor funcionando en macOS con memoria unificada, todo tras un aviso explícito.

## Fuera de alcance

- Ejecutar nada en un Mac, medir en MPS o anunciar macOS como soportado.

Sigue pendiente en la fase 4 del roadmap:

- Perfil GGUF para NVIDIA con poca VRAM. Las mediciones de esta spec servirán para valorarlo, pero no se decide aquí.
- Origen más estable para FLUX Dev y evaluación de FLUX.1 Schnell.

Además:

- Cambios en `setup`, salvo que lo pida una incoherencia hallada al compartir la lógica.
- Reducir herramientas, `setup_status` y arranque del servidor sin ComfyUI: fase 5.

## Decisiones

| Tema | Decisión |
|---|---|
| Qué está instalado | Un workflow está disponible si todos sus modelos en `models.toml` existen en la carpeta de modelos con el tamaño esperado. Sin hash y sin ComfyUI activo |
| Carpeta de modelos | La misma resolución que `doctor`, compartida en una sola función |
| `list_workflows` | Solo lo instalado, con la misma forma `{name, file}`. Kontext sigue siendo interno y no aparece |
| Falta lo pedido | Error con el perfil mínimo y el comando `imagehearth-mcp setup --profile <perfil>`. Nunca se cambia de modelo en silencio |
| Momento de la comprobación | Antes de abrir la sesión de generación, para no descargar modelos de Ollama ni arrancar ComfyUI en vano |
| Workflow sin entrada en el manifiesto | No se ofrece: el catálogo sale de `models.toml` y de los JSON a la vez |
| Separación del cargador | Localizar nodos por `class_type` o rol y aislar el cargador en una función. El workflow enviado debe quedar idéntico al actual salvo los identificadores que se decida conservar, comprobado con un test. La búsqueda admite también los cargadores GGUF, y cada variante es un JSON propio |
| Nivel de macOS | Nivel 3: experimental y sin probar. Solo sube a nivel 2 cuando se pruebe con hardware real |
| Entrada en macOS | `setup` exige `--experimental` y explica que no se ha probado, antes de descargar nada |
| Perfiles de Mac | `mac-fast` (SDXL Turbo, el mismo archivo), `mac-quality` (FLUX Dev GGUF) y `mac-full` (más Kontext GGUF). `setup` solo ofrece los de la plataforma detectada |
| Cuantización | `Q5_K_M` para Kontext y T5, y `Q5_K_S` para FLUX Dev porque su repositorio no publica `Q5_K_M`, sin medir en MPS: equilibra memoria y calidad en equipos de 32 GB. Cambiarla solo requiere editar el manifiesto |
| PyTorch en Mac | Versión estable fijada desde PyPI, que ya incluye MPS, en lugar de la nightly que cita `tech-stack.md`: una nightly no se puede fijar de forma reproducible. Si falla en un Mac real, se cambia en el manifiesto |
| `quality` en Mac | La misma interfaz: `high` y la edición resuelven a la variante GGUF del perfil, sin parámetros nuevos |
| Memoria en Mac | La memoria unificada hace de VRAM en las comprobaciones previas, y `/system_stats` en el motor. Nunca se llama a `nvidia-smi` en macOS |
| Comprobación sin Mac | Los workflows GGUF se ejecutan de verdad en la RTX 4090, que valida el grafo y los archivos aunque no MPS. Lo específico de macOS solo se cubre con tests simulados |
| Hardware de medición | RTX 4090 en Linux y el equipo NVIDIA con Windows. La tabla indica el equipo medido |
| Mínimos de VRAM | Los de otras GPU siguen marcados como orientativos: no se anuncia lo que no se ha medido |

## Restricciones

- Las 7 herramientas conservan nombres y parámetros. `list_workflows` conserva su forma y solo cambia qué elementos incluye; las descripciones de las herramientas pueden actualizarse.
- El servidor MCP sigue arrancando sin PyTorch ni ComfyUI, y sin importar `huggingface_hub` al arrancar.
- El catálogo se evalúa en cada llamada, para que un `setup` posterior se note sin reiniciar el servidor.
- Comprobar lo instalado no debe leer los modelos enteros: solo metadatos del archivo.
- La interfaz es en inglés; los documentos de `specs/` siguen en español.
- No hay `git commit` por parte del asistente: el usuario revisa y confirma los cambios.

## Entregables

- Módulo del motor con el catálogo de lo instalado y su integración en `validation`, `image_router`, `kontext` y `server`.
- `kontext.build_workflow` sin identificadores de cargador fijos.
- `scripts/measure_profiles.py` y resultados en una tabla de ambos README y en `tech-stack.md`.
- `models.toml` con `pytorch.metal`, `ComfyUI-GGUF`, modelos GGUF y perfiles `mac-*`, y workflows GGUF en `data/workflows`.
- `THIRD_PARTY_NOTICES.md` con `ComfyUI-GGUF` y los orígenes de los GGUF.
- Tests con carpetas de modelos simuladas para cada perfil y con macOS simulado.
- Ambos README y `tech-stack.md` indicando que macOS está preparado, sin probar y sin soporte anunciado.
- Roadmap con las tareas hechas marcadas cuando estén verificadas.

## Supuestos abiertos

- **Modelos fuera de la carpeta principal:** si un ComfyUI adjunto o de desarrollo tiene modelos en rutas de `extra_model_paths.yaml` que `install.json` no registra, se considerarían ausentes. Comprobado: la resolución de `doctor` no bastaba, así que catálogo y `doctor` leen también `extra_model_paths.yaml` de la carpeta de ComfyUI, siempre por archivo y tamaño. `setup` no lo lee y descargaría una copia en la carpeta principal. Un archivo indicado con `--extra-model-paths-config` no se detecta.
- **macOS en real:** nada garantiza que ComfyUI, `ComfyUI-GGUF`, FLUX y Kontext funcionen en MPS. El plan B del roadmap sigue vigente si algún informe lo descarta.
- **Repositorios GGUF:** confirmados con su licencia al fijar revisión, tamaño y SHA-256: `city96/FLUX.1-dev-gguf`, `city96/t5-v1_1-xxl-encoder-gguf` (el nombre inicial era incorrecto) y `QuantStack/FLUX.1-Kontext-dev-GGUF`.
- **Equipo Windows:** se asume que sigue disponible con NVIDIA. Su modelo y VRAM se anotan en la evidencia al medir.
