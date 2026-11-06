# Validación: Fase 8

La validación tiene dos puertas: fusionar la rama (tests simulados y comprobaciones locales) y cerrar la fase (pruebas reales con GPU y con agentes, que pueden completarse después de fusionar).

## Criterios de finalización

- Un agente pide diez imágenes en una llamada a `create_images` y el modelo de lenguaje se descarga y se restaura una sola vez, con un solo arranque de ComfyUI.
- Un lote de generaciones y otro de ediciones tardan claramente menos que las mismas imágenes en llamadas separadas, y la diferencia está medida en el README.
- Un lote que mezcla generaciones y ediciones, que está vacío o que supera el límite se rechaza antes de tocar la GPU con un error que lo explica e indica los elementos afectados.
- Cambiar el límite con `imagehearth-mcp setup --batch-limit N` se refleja en `create_images` y en `doctor`.
- Si una imagen del lote falla, el resto se genera y la respuesta indica cuál falló y por qué, en el orden pedido.
- Cancelar a mitad deja la GPU libre, el modelo de lenguaje restaurado y las imágenes hechas en disco y en la respuesta.
- `create_image` se comporta exactamente igual que antes.

## Validaciones automáticas

Desde la raíz del repositorio, en Linux:

```bash
scripts/check.sh
```

Ejecuta `uv sync --locked`, `ruff`, `pytest` y los tests contra el wheel instalado en un entorno aparte.

```bash
scripts/contract.sh
```

Prueba de contrato con `/object_info`; no cambian los workflows, pero debe seguir en verde.

La puerta de calidad obligatoria de [tech-stack](../tech-stack.md) es `scripts/check.sh` más la prueba de contrato.

Los tests deben cubrir:

- [ ] `batch_limit`: defecto 20, `config.toml`, variable de entorno que prevalece, valor no válido.
- [ ] `setup --batch-limit N` escribe el valor y conserva el resto de `config.toml`.
- [ ] `doctor` muestra el límite y su origen, también en `--json`.
- [ ] Valores comunes del lote aplicados y sobrescritos por elemento.
- [ ] Rechazo sin tocar la GPU ni el orquestador: lote mezclado, vacío, por encima del límite, prompt vacío, tamaño no válido, referencia inexistente, workflow no instalado; con índices en base 1 y todos los fallos juntos.
- [ ] Con N elementos, descarga y restauración de modelos de lenguaje y arranque de ComfyUI una sola vez.
- [ ] `required_mib` del lote igual al del workflow más exigente, comprobado una vez.
- [ ] Agrupación por workflow con la respuesta en el orden pedido.
- [ ] Fallo intermedio que no impide los siguientes.
- [ ] ComfyUI caído o `RecoveryRequired` que aborta el resto y marca los no intentados.
- [ ] Cancelación que conserva las imágenes hechas, marca las pendientes y restaura los modelos.
- [ ] Estado de sesión con el lote y `recover_engine` tras una caída a mitad de lote.
- [ ] Progreso `Generating image N of M`.
- [ ] Formato de respuesta: rutas, `ERROR:` por elemento, advertencias de elemento y `WARNING:` del lote al final.
- [ ] Tests existentes de `create_image` en verde sin modificarlos.

## Validaciones manuales

### Antes de fusionar (RTX 4090 en Linux)

- [x] `imagehearth-mcp setup --batch-limit 5` y `doctor` muestra 5; un lote de 6 se rechaza con el error que explica el límite.
- [x] Desde un cliente MCP real, un lote pequeño de `fast` devuelve una línea por elemento en el orden pedido y el progreso muestra `Generating image N of M`.
- [x] Un lote mezclado desde el cliente real se rechaza sin arrancar ComfyUI ni descargar modelos.

### Para cerrar la fase (después de fusionar si hace falta)

- [x] Prueba real etiquetada: lote de cuatro `fast` y dos `high` con un modelo de Ollama cargado frente a seis `create_image`; tiempos y número de descargas del modelo anotados.
- [x] Prueba real etiquetada: lote de tres ediciones con Kontext frente a tres llamadas sueltas.
- [x] Cancelar un lote real a mitad: GPU libre, modelo restaurado, imágenes hechas en disco.
- [x] **Mantenedor:** Claude Code usa `create_image` con una lista de prompts para varias imágenes y con un prompt para una sola.
- [ ] **Mantenedor:** un modelo local de la fase 5 hace lo mismo (con `create_image`; `create_images` se retiró).
- [x] Ahorro medido trasladado a `README.md` y `README.es.md`.

## Lista para fusionar

- [x] `scripts/check.sh` en verde en Linux.
- [x] Prueba de contrato `/object_info` en verde.
- [x] Validaciones "Antes de fusionar" completadas.
- [ ] Instrucciones del servidor MCP, skill `imagehearth`, `tech-stack.md` y `docs/troubleshooting.md` actualizados.
- [ ] README con la sección de lotes (el ahorro puede quedar pendiente de la medición de cierre, indicándolo).
- [ ] Roadmap actualizado con las tareas hechas.
- [ ] Cambios revisados por el usuario, que realiza el commit.

## Lista para cerrar la fase

- [ ] Validaciones "Para cerrar la fase" completadas.
- [ ] README con el ahorro medido.
- [ ] Roadmap con la fase marcada como completada.

## Evidencia

| Comprobación | Resultado | Fecha |
|---|---|---|
| `scripts/check.sh` en Linux | 451 tests en verde | 2026-11-06 |
| Prueba de contrato `/object_info` | OK: 20 tipos de nodo existen | 2026-11-06 |
| `setup --batch-limit` y `doctor` | Comprobado a mano por el mantenedor: correcto | 2026-11-06 | |
| Lote desde cliente MCP real | Comprobado a mano por el mantenedor: correcto | 2026-11-06 | |
| Lote mezclado rechazado sin GPU | Comprobado a mano por el mantenedor: correcto | 2026-11-06 | |
| 4 `fast` + 2 `high` con Ollama frente a 6 llamadas | `scripts/measure_batch.py`, gemma4:26b, RTX 4090: 86,5 s con 6 descargas del modelo frente a 42,1 s con 1 (−51 %) | 2026-11-06 |
| 3 ediciones Kontext frente a 3 llamadas | 566,2 s frente a 550,3 s (−3 %): cada edición de una foto de 3536x2352 tarda ~3 min y eclipsa la preparación | 2026-11-06 |
| Cancelación de un lote real | 3 imágenes en disco, 3 `cancelled`, VRAM 3201→3378 MiB, modelo restaurado, sin estado pendiente | 2026-11-06 |
| Claude Code usa una lista de prompts en `create_image` (la herramienta `create_images` se retiró: el agente llamaba una vez por imagen; repetida la prueba con la descripción nueva) | Correcto, comprobado por el mantenedor | 2026-11-06 |
| Modelo local usa una lista de prompts en `create_image` | | |
