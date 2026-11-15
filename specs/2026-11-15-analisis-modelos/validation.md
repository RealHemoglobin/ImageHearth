# Validación: Fase 14

La rama no se fusiona hasta que la lista corta esté aprobada, las mediciones de Linux estén completas en los cuatro niveles, `scripts/check.sh` esté en verde y el usuario haya escrito su decisión. La medición en Windows es opcional y, si falta, queda anotada como pendiente.

## Criterios de finalización

- `analysis.md` recoge todos los candidatos revisados, con licencia y motivo de cada descarte.
- La lista corta tiene la aprobación del usuario con fecha, antes de cualquier descarga.
- Cada modelo de la lista aprobada tiene mediciones reales en Linux (tiempo, pico de VRAM y de RAM) en 8, 16, 24 y 32+ GB, o la anotación de que no cabe con el error; en 32+ GB, la VRAM sin descarga está marcada como estimada si no se pudo medir directamente.
- La comparativa visual con los mismos cinco prompts y semilla `1234` está en `comparison/`, con FLUX.1 Dev, FLUX.1 Schnell y SDXL 1.0 como referencia, y la de edición con Kontext como referencia.
- La tabla final por nivel indica el recomendado para `quality`, para edición y la alternativa comercial (o que no existe).
- El usuario ha decidido qué modelos se integran en la fase 15, y la decisión está en `analysis.md` y en el roadmap.
- No hay cambios en `src/`, `data/` ni en los workflows del producto.

## Validaciones automáticas

Desde la raíz del repositorio, en Linux:

```bash
scripts/check.sh
```

Ejecuta `uv sync --locked`, `ruff`, `pytest` y los tests contra el wheel instalado. Es la puerta de calidad obligatoria de [tech-stack](../tech-stack.md); aquí comprueba que el script nuevo pasa `ruff` y que nada del producto ha cambiado. No hace falta `scripts/contract.sh`: la fase no toca workflows del producto.

```bash
git diff --stat main -- src data
```

Debe salir vacío.

## Validaciones manuales

En Linux, por el asistente, con la RTX 4090 y sin modelos de lenguaje cargados:

- [ ] Estudio previo completo y lista corta propuesta con tamaño total y licencias.
- [ ] Lista corta aprobada por el usuario (fecha anotada).
- [ ] `scripts/measure_models.py --help` documenta modelo, precisión, nivel y salida.
- [ ] Cada modelo y precisión medidos en 8, 16 y 24 GB con `--reserve-vram`; JSON en `measurements/`.
- [ ] Nivel 32+ GB medido con bf16 en la tarjeta completa, con la estimación marcada si hubo descarga parcial.
- [ ] Ediciones medidas, con Kontext como referencia.
- [ ] Imágenes JPG en `comparison/` de menos de 100 KB cada una, y rejillas por prompt.
- [ ] El ComfyUI gestionado y la instalación del usuario no cambian tras las mediciones (`imagehearth-mcp doctor` igual que antes).
- [ ] Pesos y PNG completos fuera del repositorio.

Por el **mantenedor**, opcional:

- [ ] Recomendado de 16 GB medido en Windows con `scripts/measure_models.py`. Si no se hace, se anota como pendiente en la evidencia.

## Antes de fusionar

- [ ] `scripts/check.sh` en verde.
- [ ] `git diff --stat main -- src data` vacío.
- [ ] `analysis.md` sin secciones vacías ni preguntas abiertas, con la decisión del usuario fechada.
- [ ] Roadmap: casillas de la fase 14 marcadas y fase 15 concretada con los modelos elegidos.
- [ ] `git status --short` solo muestra `scripts/measure_models.py`, `scripts/measure_models/`, esta carpeta y `specs/roadmap.md`.

## Evidencia

| Prueba | Resultado | Fecha |
|---|---|---|
| Lista corta aprobada | | |
| Mediciones Linux 8 / 16 / 24 / 32+ GB | | |
| Comparativa visual | | |
| Windows 16 GB (opcional) | | |
| Decisión del usuario | | |
| `scripts/check.sh` | | |
