# Plan: Fase 13

Rama: `feature/loras-sdxl`. Sin commits del asistente: los cambios se dejan en el árbol de trabajo para revisión. Los pasos marcados como **mantenedor** no los ejecuta el asistente.

Orden: primero la selección del catálogo, porque fija los datos reales. Después el catálogo en código y la generación (el motor no depende de la instalación: los tests usan archivos simulados). Luego la instalación y el MCP de instalación, y por último agentes, documentación y pruebas reales.

## 1. Selección de LoRAs (`seleccion-loras.md`)

1. Buscar en Hugging Face LoRAs de SDXL 1.0 para fotorrealismo, ilustración, anime, pixel art, acuarela y detalle (y otras categorías si hay buenas candidatas), con licencia declarada en el repositorio.
2. Descartar las que no tengan licencia OpenRAIL++, CreativeML OpenRAIL-M, Apache-2.0 o MIT, las de origen inestable y las que exijan aprobación o token.
3. Medir cada candidata en la RTX 4090 con `scripts/measure_loras.py` (nuevo): mismos 3 prompts y semilla, sin LoRA y con la LoRA a su peso recomendado y a otro peso, sobre SDXL 1.0 con la LoRA de detalle fija. Guardar las imágenes fuera del repositorio.
4. Elegir entre 6 y 10. Fijar para cada una revisión, archivo, tamaño, SHA-256, licencia, palabras de activación y peso recomendado.
5. Documentar en `seleccion-loras.md`: tabla de candidatas, motivo de cada descarte, la elección y los prompts usados.

## 2. Catálogo en código

1. `models.toml`: sección `[[loras]]` con los campos de [requirements](requirements.md#decisiones).
2. Carga y validación (en `provisioner/manifest.py` junto a `[[models]]`, o `engine/loras.py` si así lo comparten mejor motor y provisión): nombres únicos, `base = "sdxl"`, `dest` bajo `loras/`, peso entre 0 y 2, campos obligatorios.
3. Funciones de consulta: catálogo completo, instaladas (según el registro de instalación y los archivos presentes) y búsqueda por nombre.
4. Tests en `tests/test_loras.py`: catálogo válido, catálogo con errores (nombre repetido, `dest` fuera de `loras/`, peso fuera de rango) y detección de instaladas.

## 3. Generación

1. Normalizar `loras` (cadena u objeto `{name, weight}`) a una lista de `(nombre, peso)`; validar máximo 3, sin repetir, peso entre 0 y 2.
2. `image_router.plan_request`: rechazar `loras` sin `quality: "high"`, con edición, con un workflow distinto de `sdxl_base` o con un modelo de `quality` que no es SDXL 1.0, con mensaje que dice por qué. Nombre desconocido o no instalado: error con las instaladas y el comando para instalar.
3. `batch`: `loras` como campo por elemento y común (`_merge`), validado en la comprobación previa de toda la lista.
4. `workflow_runner`: insertar `LoraLoader` encadenados detrás del nodo `"2"` y reconectar los `CLIPTextEncode` y el muestreador a la última; sin LoRAs, workflow idéntico.
5. Palabras de activación: añadir al principio del prompt las que falten; integrar con `apply_style` para que no se añadan pistas fotográficas con LoRAs de otro medio.
6. `stamp_png`: texto `ImageHearth-LoRAs`.
7. `server.create_image`: parámetro `loras` y docstring (formato, máximo 3, solo `quality: "high"` con SDXL 1.0, consultar `list_workflows`).
8. `server.list_workflows`: campo `loras` en el item activo de `sdxl_base` y docstring.
9. Tests en `tests/test_loras.py` y `tests/test_batch.py`: workflow con 0, 1 y 3 LoRAs (nodos y conexiones), 4 LoRAs rechazadas, nombre repetido, peso fuera de rango, nombre desconocido y no instalado, rechazo con FLUX, `fast`, edición y RealVisXL, lotes con LoRAs distintas por elemento y común, palabras de activación (presentes y ausentes), metadatos PNG y `list_workflows` con y sin LoRAs. Comprobar que ningún rechazo arranca ComfyUI ni toca memoria.

## 4. Instalación

1. `cli.py`: `setup --loras` (`all`, `none` o lista separada por comas); error si el modelo de `quality` elegido o instalado no es SDXL 1.0 o si un nombre no existe.
2. `setup.py`, paso interactivo `LoRAs` tras elegir SDXL 1.0: `menu.choose_many` con nombre, categoría, tamaño y licencia, sin marcar en instalación nueva y con las instaladas marcadas en una existente; 0 vuelve; el indicador `Step N of M` lo incluye. La confirmación final muestra las LoRAs y su tamaño, y el espacio necesario las incluye.
3. Conjunto fijo sobre una instalación existente: descargar las que faltan y borrar las que sobran, con el resumen de qué se añade y qué se borra; sin `--loras`, nada cambia.
4. Descarga con el mecanismo de modelos (reanudable, verificada) y registro en el manifiesto de instalación como propias.
5. `quality.plan_change` y `delete_old`: al cambiar de SDXL 1.0 a FLUX, incluir las LoRAs en lo que se borra y en el resumen.
6. `uninstall` y `update --move-to`: las LoRAs registradas se tratan como el resto de modelos propios (comprobar que ya lo hacen por el registro).
7. `doctor`: LoRAs instaladas y aviso si falta o no coincide algún archivo registrado; en `--json` dentro de `details`.
8. Tests en `tests/test_provisioner.py`, `tests/test_quality_model.py` y `tests/test_setup_steps.py`: `--loras` con lista, `all` y `none`, nombre desconocido, con FLUX, paso interactivo (instalación nueva y existente, 0 vuelve), añadir y quitar sobre una existente, nada escrito antes de confirmar, cambio de SDXL a FLUX borra las LoRAs, `uninstall` las borra y no toca archivos ajenos en `models/loras`, y `doctor`.

## 5. MCP de instalación

1. `agent_setup.status`: catálogo con nombre, descripción, categoría, tamaño y licencia, e instaladas.
2. `agent_setup.start` y `server.setup_start` con `loras: list[str] | None = None` (`["all"]` admitido); mismas validaciones y errores devueltos al agente.
3. Instrucciones del servidor y docstrings de `setup_status`/`setup_start`: al elegir SDXL, preguntar al usuario si quiere LoRAs y cuáles, con tamaño y licencia.
4. Tests en `tests/test_agent_setup.py`: con lista válida, `all`, vacía, nombre desconocido y con FLUX.

## 6. Agentes y documentación

1. Instrucciones del servidor (`server.py`) y skill `data/skill/SKILL.md`: cuando el usuario pida un estilo, consultar `list_workflows` y usar una LoRA instalada si encaja; no inventar nombres; solo con `quality: "high"` y SDXL 1.0.
2. Generar las imágenes de ejemplo con el mismo prompt y semilla, con y sin cada LoRA, en JPG de unos 512 px y menos de 100 KB en `docs/images/loras/`.
3. `README.md` y `README.es.md`: sección de LoRAs con tabla (nombre, categoría, licencia, imagen sin y con LoRA), `--loras` y el parámetro `loras`.
4. `llms-install.md`: preguntar por las LoRAs al elegir SDXL.
5. `THIRD_PARTY_NOTICES.md`: licencia y origen de cada LoRA.
6. `CHANGELOG.md` si el proyecto lo mantiene por fase.
7. Marcar en el roadmap las tareas hechas.

## 7. Pruebas reales

1. Linux, por el asistente, con `HOME` temporal: `setup --profile quality --quality-model sdxl --loras all`, generar cada LoRA del catálogo con el mismo prompt y semilla en la RTX 4090, y comprobar metadatos PNG.
2. Añadir y quitar LoRAs con `setup --loras` sobre esa instalación; `doctor`; cambiar a FLUX Schnell y comprobar que se borran; `uninstall`.
3. Agente sin ayuda: con un agente conectado (y un modelo local pequeño si está disponible), pedir una imagen de un estilo cubierto y comprobar que consulta `list_workflows` y llama a `create_image` con la LoRA correcta. Pedir una LoRA con FLUX o con `fast` y comprobar el error antes de tocar la GPU.
4. Prueba de contrato (`scripts/contract.sh`): no hay nodos nuevos (`LoraLoader` ya se usa), pero se ejecuta para confirmar el workflow con LoRAs encadenadas.
5. **Mantenedor:** instalar con `--loras` y generar con una LoRA en Windows.

## 8. Validación local y cierre

1. Ejecutar `scripts/check.sh`.
2. Rellenar la evidencia en [validation.md](validation.md).
3. **Mantenedor:** revisar, hacer commit y fusionar en `main`.
4. Marcar la fase como completada en el roadmap cuando la lista de cierre esté completa.
