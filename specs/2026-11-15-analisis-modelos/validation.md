# Validación: Fase 14

La rama no se fusiona hasta que la lista corta esté aprobada, las mediciones de Linux estén completas en los cuatro niveles, el selector múltiple con flechas tenga sus tests y su prueba manual en Linux, `scripts/check.sh` esté en verde y el usuario haya escrito su decisión. Lo de Windows (medición y prueba del selector) es opcional y, si falta, queda anotado como pendiente.

## Criterios de finalización

- `analysis.md` recoge todos los candidatos revisados, con licencia y motivo de cada descarte.
- La lista corta tiene la aprobación del usuario con fecha, antes de cualquier descarga.
- Cada modelo de la lista aprobada tiene mediciones reales en Linux (tiempo, pico de VRAM y de RAM) en 8, 16, 24 y 32+ GB, o la anotación de que no cabe con el error; en 32+ GB, la VRAM sin descarga está marcada como estimada si no se pudo medir directamente.
- La comparativa visual con los mismos cinco prompts y semilla `1234` está en `comparison/`, con FLUX.1 Dev, FLUX.1 Schnell y SDXL 1.0 como referencia, y la de edición con Kontext como referencia.
- La tabla final por nivel indica el recomendado para `quality`, para edición y la alternativa comercial (o que no existe).
- El usuario ha decidido qué modelos se integran en la fase 15, y la decisión está en `analysis.md` y en el roadmap.
- No hay cambios en `src/`, `data/` ni en los workflows del producto, salvo `provisioner/menu.py` (y `provisioner/setup.py` si el texto del paso `LoRAs` lo pedía).
- En `setup` con terminal, el paso `LoRAs` se responde con flechas, espacio y Enter, sin escribir números; 0 vuelve atrás y Ctrl+C sale limpio con la terminal restaurada.
- Sin terminal, `choose_many` sigue aceptando números separados por comas; los menús de una opción y `--loras` no cambian.

## Validaciones automáticas

Desde la raíz del repositorio, en Linux:

```bash
scripts/check.sh
```

Ejecuta `uv sync --locked`, `ruff`, `pytest` y los tests contra el wheel instalado. Es la puerta de calidad obligatoria de [tech-stack](../tech-stack.md); aquí comprueba que el script nuevo pasa `ruff` y que el selector y el resto del producto pasan sus tests. No hace falta `scripts/contract.sh`: la fase no toca workflows del producto.

```bash
git diff --stat main -- src data
```

Solo debe mostrar `src/imagehearth_mcp/provisioner/menu.py` y, si se cambió, `src/imagehearth_mcp/provisioner/setup.py`.

Los tests del selector deben cubrir:

- [ ] ↓/↑ mueven el cursor y dan la vuelta en los extremos; espacio marca y desmarca; el contador de `Install selected (N)` se actualiza.
- [ ] Enter envía desde una opción y desde `Install selected`; Enter sobre `← Back` y 0 devuelven `BACK`; enviar sin marcadas devuelve `[]`.
- [ ] Marcas iniciales con `default=None` (todas) y con `default`; orden del resultado igual al de las opciones.
- [ ] Sin `allow_back`: no hay `← Back` y 0 se ignora.
- [ ] Teclas desconocidas y Esc solo ignoradas; Ctrl+C lanza `KeyboardInterrupt`.
- [ ] Flechas como nombres (`"UP"`, `"DOWN"`) y como secuencias en bruto desde el lector inyectado.
- [ ] `read_key` con terminal y consola simuladas: flechas en Linux (`ESC [`, `ESC O`) y en Windows (`\xe0`/`\x00` + `H`/`P`), Esc solo, terminal restaurada.
- [ ] Lectura por línea sin terminal igual que antes (números por comas, `none`, Enter, 0).
- [ ] Los menús de una opción sin cambios: sus tests existentes pasan sin tocarlos.
- [ ] Tests de `setup` ajustados al paso `LoRAs` nuevo; los cambiados quedan anotados aquí.

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
- [ ] Selector en un pty real (bash y zsh), con `HOME` temporal y `setup` eligiendo SDXL 1.0, sin descargar: la lista se repinta en el sitio sin dejar restos, espacio marca, Enter instala las marcadas (se ve en el resumen final), 0 vuelve al paso anterior con las marcas conservadas y Ctrl+C deja la terminal en su estado normal.

Por el **mantenedor**, opcional:

- [ ] Recomendado de 16 GB medido en Windows con `scripts/measure_models.py`. Si no se hace, se anota como pendiente en la evidencia.
- [ ] Selector en Windows (PowerShell y Windows Terminal): flechas, espacio, Enter, 0 y Ctrl+C. Si no se hace, se anota como pendiente en la evidencia.

## Antes de fusionar

- [ ] `scripts/check.sh` en verde.
- [ ] `git diff --stat main -- src data` solo con los ficheros del selector.
- [ ] `analysis.md` sin secciones vacías ni preguntas abiertas, con la decisión del usuario fechada.
- [ ] Roadmap: casillas de la fase 14 marcadas y fase 15 concretada con los modelos elegidos.
- [ ] `git status --short` solo muestra `scripts/measure_models.py`, `scripts/measure_models/`, esta carpeta, `specs/roadmap.md`, `provisioner/menu.py` (y `setup.py` si cambió) y los tests del selector.

## Evidencia

| Prueba | Resultado | Fecha |
|---|---|---|
| Lista corta aprobada | | |
| Mediciones Linux 8 / 16 / 24 / 32+ GB | | |
| Comparativa visual | | |
| Windows 16 GB (opcional) | | |
| Decisión del usuario | | |
| Selector con flechas en Linux (pty real) | | |
| Selector con flechas en Windows (opcional) | | |
| `scripts/check.sh` | | |
