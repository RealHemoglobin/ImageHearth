# Plan: Fase 8

Rama: `feature/generacion-por-lotes`. Sin commits del asistente: los cambios se dejan en el árbol de trabajo para revisión. Los pasos marcados como **mantenedor** no los ejecuta el asistente.

Orden: motor primero. La validación y la configuración no tocan la GPU y se prueban solas; después la sesión única, que es el cambio con más riesgo; la herramienta MCP encima, y al final documentación y pruebas reales.

## 1. Configuración del límite

1. `engine/config.py`: `BATCH_LIMIT` con `batch_limit` en `config.toml`, `IMAGEHEARTH_BATCH_LIMIT` y 20 por defecto. Entero mayor o igual que 1; un valor no válido da `ConfigError` como el resto de opciones.
2. `cli.py`: `setup --batch-limit N` junto a `--port`, con su ayuda.
3. Provisioner: `setup` escribe `batch_limit` en `config.toml` igual que el puerto, conservando el resto de claves.
4. `doctor`: muestra el límite en uso y su origen (variable, archivo o defecto), también en `--json`.
5. Tests en `tests/test_config.py` y `tests/test_provisioner.py`: defecto, archivo, variable que prevalece, valor no válido, `setup --batch-limit` y salida de `doctor`.

## 2. Validación del lote

1. Módulo nuevo `engine/batch.py` con la normalización: aplicar los valores comunes del lote a cada elemento sin pisar los propios.
2. Resolver el modo de cada elemento (`auto` según `image_paths`) y el tipo de lote. Si hay mezcla, rechazar con la lista de índices de cada tipo.
3. Rechazar lotes vacíos o por encima de `config.BATCH_LIMIT`, indicando el límite y cómo cambiarlo.
4. Validar cada elemento reutilizando `validation.py` (`validate_prompt`, `validate_dimensions`, `resolve_workflow`) y las mismas reglas de `image_router.create_image`: `quality`, `mode`, `MAX_REFERENCES`, rutas existentes, `negative_prompt` en edición (aviso, no error).
5. Comprobar que cada workflow resuelto está instalado antes de tocar la GPU.
6. Errores con el índice en base 1 (`Item 3: ...`) y todos los fallos juntos, no solo el primero.
7. Tests: lote mezclado, vacío, por encima del límite, prompt vacío, tamaño no válido, referencia inexistente, workflow no instalado, valores comunes sobrescritos y ningún acceso a la GPU ni al orquestador en el rechazo.

## 3. Generar dentro de una sesión abierta

1. `workflow_runner.run_workflow`: extraer el cuerpo que genera con una `session` recibida (p. ej. `run_in_session(session, ...)`). `run_workflow` abre la sesión y llama a esa función, sin cambiar su comportamiento.
2. `kontext.generate`: lo mismo para la edición.
3. Comprobar que los tests de `create_image` (`tests/test_session.py`, `tests/test_requests.py`) siguen en verde sin modificarlos.

## 4. Sesión única para el lote

1. `generation_session`: aceptar varios workflows o un `required_mib` explícito; el del lote es el máximo de `catalog.required_vram_mib`. La comprobación de memoria se hace una vez.
2. `state.write`: registrar el lote (`batch_total`, `batch_index`) y el `prompt_id` de la imagen en curso. `recover_engine` y `_reconcile` funcionan igual con estos campos.
3. Bucle del lote en `engine/batch.py`: agrupar por workflow conservando el orden relativo, generar una tras otra con `run_in_session` y guardar el resultado en la posición original.
4. Fallos: capturar los errores de un elemento y seguir. Abortar el resto ante ComfyUI caído o `RecoveryRequired`, marcando los no intentados.
5. Cancelación: comprobar `progress.raise_if_cancelled()` entre imágenes; ante `GenerationCancelled` devolver lo hecho, marcar lo pendiente como cancelado y dejar que `_finish` limpie.
6. Progreso: `progress.stage("Generating image 3 of 10")` antes de cada imagen; las etapas de descarga, arranque y restauración se mantienen.
7. Tests simulados con el arnés de `tests/harness.py`: con N elementos, descarga, restauración y arranque de ComfyUI una sola vez; agrupación y orden de la respuesta; fallo intermedio que no impide los siguientes; ComfyUI caído que aborta el resto; cancelación que conserva lo hecho y restaura modelos; estado de sesión con el lote; `recover_engine` tras una caída a mitad de lote.

## 5. Herramienta MCP y respuesta

1. `server.py`: `create_images(items, quality, width, height, negative_prompt)` con el mismo mecanismo de hilo, progreso cada 5 s y cancelación que `create_image`. Sin `include_image`.
2. Formato de respuesta: una línea por elemento en el orden pedido (`1: /ruta.png`, `1: ERROR: motivo`), advertencias de elemento en su línea y advertencias del lote al final con `WARNING:`.
3. Descripción de la herramienta para el agente: cuándo usarla, independencia de los elementos, lotes separados para generar y editar, límite.
4. Tests: formato de respuesta con éxitos, errores y advertencias; rechazo previo devuelto como error de la herramienta; `create_image` intacta.

## 6. Agentes y documentación

1. `FastMCP(instructions=...)`: si el agente ya sabe que va a crear varias imágenes independientes, usar `create_images`; cómo leer la respuesta línea a línea.
2. `data/skill/SKILL.md`: misma guía, independencia de elementos, cadenas de edición como llamadas sucesivas y generaciones y ediciones en lotes separados.
3. `README.md` y `README.es.md`: sección con un ejemplo y el ahorro medido en la tarea 7.
4. `tech-stack.md`: fila de decisión para `create_images`.
5. `docs/troubleshooting.md`: lote rechazado por mezcla o límite, y cómo cambiar el límite.

## 7. Pruebas reales etiquetadas

1. Prueba etiquetada (marcador de pytest como las reales existentes): lote de cuatro `fast` y dos `high` con un modelo de Ollama cargado frente a seis `create_image`; registrar tiempos y descargas del modelo.
2. Prueba etiquetada: lote de tres ediciones con Kontext frente a tres llamadas sueltas.
3. Cancelar un lote real a mitad: GPU libre, modelo restaurado e imágenes hechas en disco.
4. **Mantenedor:** probar con Claude Code y con un modelo local de la fase 5 que el agente elige `create_images` con una lista y `create_image` con una sola imagen.
5. Trasladar las cifras al README y a la evidencia.

## 8. Validación local y fusión

1. Ejecutar `scripts/check.sh` y `scripts/contract.sh`.
2. Rellenar la evidencia en [validation.md](validation.md) y marcar en el roadmap lo verificado.
3. **Mantenedor:** revisar, hacer commit y fusionar en `main`.

## 9. Cierre de la fase

1. Completar las pruebas reales de la tarea 7 que falten, incluida la del agente real.
2. Marcar la fase como completada en el roadmap.
