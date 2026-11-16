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

- [x] ↓/↑ mueven el cursor y dan la vuelta en los extremos; espacio marca y desmarca; el contador de `Install selected (N)` se actualiza.
- [x] Enter envía desde una opción y desde `Install selected`; Enter sobre `← Back` y 0 devuelven `BACK`; enviar sin marcadas devuelve `[]`.
- [x] Marcas iniciales con `default=None` (todas) y con `default`; orden del resultado igual al de las opciones.
- [x] Sin `allow_back`: no hay `← Back` y 0 se ignora.
- [x] Teclas desconocidas y Esc solo ignoradas; Ctrl+C lanza `KeyboardInterrupt`.
- [x] Flechas como nombres (`"UP"`, `"DOWN"`) y como secuencias en bruto desde el lector inyectado.
- [x] `read_key` con terminal y consola simuladas: flechas en Linux (`ESC [`, `ESC O`) y en Windows (`\xe0`/`\x00` + `H`/`P`), Esc solo, terminal restaurada.
- [x] Lectura por línea sin terminal igual que antes (números por comas, `none`, Enter, 0).
- [x] Los menús de una opción sin cambios: sus tests existentes pasan sin tocarlos.
- [x] Tests de `setup` ajustados al paso `LoRAs` nuevo; los cambiados quedan anotados aquí. Cambiados: `test_lora_install.py` (`pick` ahora marca con flechas y espacio; `test_numbers_choose_the_loras`, `test_an_answer_is_dropped_when_the_model_is_changed_afterwards`, `test_existing_loras_come_marked_and_enter_keeps_them`, `test_choosing_none_in_the_step_removes_the_installed_ones`, `test_exiting_from_the_review_writes_nothing`, `test_deleting_loras_in_the_step_asks_for_the_final_confirmation`, y `choose_many` con `none`/números pasados a teclas o a lectura por línea), `test_setup_steps.py` (`test_zero_goes_back_and_keeps_answers`, `test_zero_from_every_step_goes_back_one_at_a_time`) y `test_menu.py` (`test_choose_many_numbers_and_retry` movido a `test_line_mode_choose_many`).

## Validaciones manuales

En Linux, por el asistente, con la RTX 4090 y sin modelos de lenguaje cargados:

- [x] Estudio previo completo y lista corta propuesta con tamaño total y licencias.
- [x] Lista corta aprobada por el usuario (fecha anotada).
- [x] `scripts/measure_models.py --help` documenta modelo, precisión, nivel y salida.
- [x] Cada modelo y precisión medidos en 8, 16 y 24 GB con `--reserve-vram`; JSON en `measurements/`. **Recortado el 2026-11-16 por decisión del usuario**: sin HiDream fp16 ni Qwen-Edit bf16.
- [x] Nivel 32+ GB en la tarjeta completa de 24 GB, con la estimación marcada (Qwen-Image bf16). Sin Qwen-Edit en 32+ por decisión del usuario.
- [x] Ediciones medidas (Klein 4B, Qwen-Edit fp8 y Q4_K_M). **Kontext no se midió como referencia** (decisión de acortar la tanda).
- [x] Imágenes JPG en `comparison/` de menos de 100 KB cada una, y rejillas por prompt.
- [x] El ComfyUI gestionado y la instalación del usuario no cambian (las mediciones usan su propio ComfyUI en otra ruta; `doctor` sin avisos nuevos, aunque no hay captura previa para comparar) tras las mediciones (`imagehearth-mcp doctor` igual que antes).
- [x] Pesos y PNG completos fuera del repositorio.
- [x] Selector en un pty real (bash y zsh), con `HOME` temporal y `setup` eligiendo SDXL 1.0, sin descargar: la lista se repinta en el sitio sin dejar restos, espacio marca, Enter instala las marcadas (se ve en el resumen final), 0 vuelve al paso anterior con las marcas conservadas y Ctrl+C deja la terminal en su estado normal.

Por el **mantenedor**, opcional:

- [ ] Recomendado de 16 GB medido en Windows con `scripts/measure_models.py`. Si no se hace, se anota como pendiente en la evidencia.
- [ ] Selector en Windows (PowerShell y Windows Terminal): flechas, espacio, Enter, 0 y Ctrl+C. Si no se hace, se anota como pendiente en la evidencia.

## Antes de fusionar

- [x] `scripts/check.sh` en verde.
- [x] `git diff --stat main -- src data` solo con los ficheros del selector.
- [x] `analysis.md` sin secciones vacías ni preguntas abiertas, con la decisión del usuario fechada.
- [x] Roadmap: casillas de la fase 14 marcadas y fase 15 concretada con los modelos elegidos.
- [x] `git status --short` solo muestra `scripts/measure_models.py`, `scripts/measure_models/`, esta carpeta, `specs/roadmap.md`, `provisioner/menu.py` (y `setup.py` si cambió) y los tests del selector.

## Evidencia

| Prueba | Resultado | Fecha |
|---|---|---|
| Lista corta aprobada | 5 de generación y 2 de edición, tal cual, con ~306 GB de descarga total y 83 GB libres | 2026-11-15 |
| Mediciones Linux 8 / 16 / 24 / 32+ GB | 54 mediciones, todas `ok`, en `measurements/` (JSON y log). Recortes: HiDream fp16, Qwen-Edit bf16, Qwen-Edit en 32+ GB, Kontext | 2026-11-16 |
| Comparativa visual | 8 rejillas y 37 JPG individuales (<100 KB) en `comparison/`; notas en `analysis.md` sección 7 | 2026-11-16 |
| Windows 16 GB (opcional) | | |
| Decisión del usuario | Se integran todos los modelos de la lista corta; el usuario elige con las mediciones a la vista (`analysis.md` sección 9, roadmap fase 15) | 2026-11-16 |
| Selector con flechas en Linux (pty real) | bash y zsh, `HOME` temporal, `setup` hasta el paso `LoRAs`: repintado en sitio sin restos, espacio marca y el contador cambia, 0 vuelve al modelo, Ctrl+C sale con código 130 y la terminal restaurada. No se descargó nada | 2026-11-15 |
| Selector con flechas en Windows (opcional) | Pendiente del mantenedor | |
| `scripts/check.sh` | 881 tests en verde y `ruff` limpio con `scripts/measure_models.py` incluido (repetido tras las mediciones) | 2026-11-16 |
