# Plan: Fase 15

Orden: primero generalizar catálogo, elección y edición sin modelos nuevos (todo sigue igual con los modelos de hoy); después añadir los modelos de uno en uno, del más pequeño al más grande; después instalación y MCP; al final documentación y validación.

## 1. Catálogo por capacidad

1.1. Diseñar en `models.toml` el catálogo por capacidad: cada modelo con `name`, `title`, `capabilities` (`fast`, `high`, `edit`), `license` y `[[options]]` por precisión (`precision`, `min_vram_mib`, `workflow` por capacidad, `models`, `nodes`, y datos medidos: `bytes` total, `seconds` y `vram_mib` por nivel 8/16/24/32). Migrar a este formato SDXL Turbo, SDXL 1.0, FLUX.1 Dev/Schnell y Kontext, manteniendo `[quality_models.*]`/`[[edit.options]]` solo si hace falta para leer instalaciones antiguas.
1.2. Cargar y validar el catálogo en `provisioner/manifest.py`: nombres únicos, capacidades válidas, precisiones únicas por modelo, workflows y pesos existentes, licencia declarada. Tests de rechazos.
1.3. `Manifest.resolve` compone pesos, nodos y licencias de un conjunto `{capacidad: [(modelo, precisión)], default}` y deduplica los componentes compartidos (Klein en `fast` y edición, codificadores).
1.4. `engine/catalog.py`: derivar `VARIANTS` del catálogo, listar modelos instalados por capacidad con su precisión y predeterminado, y `default_model(capability)`. `active_quality_model()` pasa a ser el predeterminado de `high`.

## 2. Registro, migración y predeterminados

2.1. `install_manifest.py`: registrar por capacidad los modelos instalados, su precisión y el predeterminado; los componentes compartidos con referencia a quién los usa.
2.2. Migración al leer una instalación antigua: SDXL Turbo → `fast`, modelo de `quality` → `high`, Kontext → `edit`, todos predeterminados. Sin descargas ni borrados. Tests con manifiestos de las fases 9–13.
2.3. Plan de cambio generalizado a partir de `quality.plan_change`: conjunto actual frente a pedido → descargas, borrados (solo registrados, sin componentes en uso), cambios de precisión (descargar antes de borrar), espacio necesario frente a libre.

## 3. Generación con `model`

3.1. `image_router.py`: resolver la capacidad (`fast`, `high`, `edit`) y el modelo (`model` o predeterminado); errores de modelo no instalado, sin esa capacidad o combinado con `workflow`, con instalados y comando de instalación. Antes de tocar la GPU.
3.2. `batch.py`: `model` común y por elemento; validación de todo el lote antes de generar.
3.3. `workflow_runner.py`: `build_workflow` elige el workflow de la opción instalada; metadatos `ImageHearth-Model` (y `ImageHearth-Quality-Model` donde aplica).
3.4. `loras.py`: LoRAs solo con `sdxl` como modelo resuelto; mensajes actualizados.
3.5. Tests: sin `model` idéntico a hoy con una instalación migrada; `model` válido, inválido, de otra capacidad, con `workflow`; lote mixto; LoRAs con modelo no SDXL.

## 4. Modelos nuevos (uno a uno)

Por cada modelo, en este orden: FLUX.2 Klein 4B (generación y edición), Z-Image-Turbo, Chroma1-HD, Qwen-Image, HiDream-I1 Full, Qwen-Image-Edit-2511.

4.1. Pesos en `[[models]]` (repositorio, revisión, ruta, `dest`, `bytes`, `sha256`, licencia) a partir de `scripts/measure_models/registry.json` y los JSON de mediciones; componentes compartidos una sola vez.
4.2. Workflow en `data/workflows/` a partir de `scripts/measure_models/<modelo>.json`, con los parámetros recomendados y los marcadores que rellena `prepare_workflow` (prompt, negativo, tamaño, semilla, imágenes de entrada en edición). Uno por cargador (`*_gguf`).
4.3. Opciones por precisión con `min_vram_mib`, tamaño, tiempos y VRAM por nivel de `analysis.md` (sección 6) y recomendación por nivel.
4.4. Nodos: comprobar que todos son nativos en ComfyUI 0.43.0 o de `ComfyUI-GGUF`; añadirlos a `scripts/contract.py`.
4.5. Licencias nuevas en `[licenses.*]`; HiDream añade la de Llama 3.1 con aviso.
4.6. Tests simulados del workflow construido (nodos, conexiones, marcadores rellenos) y de la entrada del catálogo.

## 5. Instalación

5.1. `setup` interactivo: por cada capacidad del perfil, `menu.choose_many` con los modelos (título, tamaño de la precisión recomendada, tiempo medido para su nivel, licencia y uso comercial, marca de recomendado); después la precisión de cada modelo con más de una; después el predeterminado si hay varios; 0 vuelve atrás en cada paso y `Step N of M` se ajusta.
5.2. Resumen de espacio antes de confirmar (descargas, borrados con motivo, total frente a libre); sin espacio, no se puede confirmar.
5.3. CLI: `--fast-models`, `--quality-models`, `--edit-models` con `nombre[:precisión]`; `--quality-model` como alias; errores con nombres y precisiones válidos; `--loras` exige `sdxl`.
5.4. Consentimiento de licencias con las de lo que se descarga, incluida la de Llama 3.1 para HiDream.
5.5. `uninstall`, `update --move-to` y `doctor` con varios modelos por capacidad y componentes compartidos.
5.6. Tests: selección múltiple nueva y existente, precisión, predeterminado, conjunto fijo, alias, espacio insuficiente, nada escrito antes de confirmar, borrado de compartidos solo cuando nadie los usa, migración.

## 6. MCP y agentes

6.1. `server.py`: `model` en `create_image` (y en los objetos de la lista) con docstring; `list_workflows` con un item por modelo instalado (`model`, `capability`, `precision`, `default`, `license`, `commercial_use`, `seconds`, `loras`).
6.2. `setup_status` con el catálogo por capacidad y datos medidos para el nivel; `setup_start` con `fast_models`, `quality_models`, `edit_models` (y `quality_model` compatible).
6.3. Instrucciones del servidor y skill `imagehearth`: cuándo llamar a `list_workflows`, cómo pasar `model`, preguntar al usuario qué modelos instalar mostrando tamaño y licencia.
6.4. Tests de `test_agent_setup.py` y del esquema de herramientas.

## 7. Documentación

7.1. `README.md` y `README.es.md`: tabla de modelos por capacidad con licencia, uso comercial, tamaño y tiempos; tabla de requisitos por nivel de VRAM; cómo elegir varios y usar `model`.
7.2. `llms-install.md` con los parámetros nuevos de `setup`/`setup_start`.
7.3. `THIRD_PARTY_NOTICES.md` con las licencias nuevas (Apache-2.0 de Z-Image, Klein, Chroma y Qwen; Llama 3.1 y la de HiDream).
7.4. Roadmap: actualizar la fase 15 con el cambio de alcance y marcar las tareas hechas.

## 8. Validación

8.1. `scripts/check.sh` y `scripts/contract.sh` en verde.
8.2. Pruebas reales rápidas del asistente en la RTX 4090 con `HOME` temporal y solo los modelos pequeños (ver [validation.md](validation.md)).
8.3. Dejar preparada para el usuario la lista de pruebas con los modelos grandes y anotar la evidencia.
