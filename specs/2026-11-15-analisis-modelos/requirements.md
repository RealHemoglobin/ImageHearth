# Fase 14: Análisis de modelos de generación

## Contexto

Fase 14 del [roadmap](../roadmap.md). Objetivo: decidir, con mediciones, qué modelos de generación y edición distintos de SDXL y FLUX.1 merece la pena añadir para tarjetas de 8, 16, 24 y 32 GB o más, sin cambiar la interfaz de ImageHearth. El resultado alimenta la [fase 15](../roadmap.md#fase-15-nuevos-modelos-de-generación), que es la que integra los modelos elegidos.

Estado de partida, comprobado el 2026-11-15:

- `quality` admite FLUX.1 Dev, FLUX.1 Schnell o SDXL 1.0 ([fase 9](../2026-11-06-eleccion-modelo-quality/requirements.md)); `fast` es SDXL Turbo y la edición es siempre FLUX.1 Kontext Dev, con licencia no comercial.
- La comparativa de la fase 9 usó tres prompts con semilla `1234` a 1024×1024 (recuperados de los metadatos de `comparison/flux_dev-*.png`):
  1. `a lighthouse on a rocky coast at sunset, detailed photograph`
  2. `portrait of an elderly fisherman with a weathered face, soft window light`
  3. `a cozy cabin in a snowy forest at night, warm light in the windows, a wooden sign that reads OPEN`
- Sus mediciones están en `../2026-11-06-eleccion-modelo-quality/measurements/*.json`, generadas con `scripts/measure_profiles.py`, que arranca su propia instancia de ComfyUI en un puerto libre y mide VRAM, RAM y tiempo.
- La máquina de medición es Linux con una RTX 4090 de 24 GB y 59 GB de RAM.
- La versión de ComfyUI está fijada en el provisionador (`provisioner/comfyui.py`, `pin.version`).

Además, a petición del usuario el 2026-11-15, la fase incluye un cambio de producto pequeño e independiente del análisis: el **selector múltiple con flechas** en `setup`. Estado de partida:

- `provisioner/menu.py` (fase 11): `choose` elige una opción con una tecla (1–9) o con número y Enter si hay más de 9; `choose_many` pide siempre una línea con números separados por comas (`Enter for all, or numbers separated by commas:`), Enter acepta las marcadas, `none` no elige ninguna (si hay marcas iniciales) y 0 vuelve atrás.
- Su único uso es `setup.choose_loras` (paso `LoRAs` de `setup` al elegir SDXL 1.0), con las instaladas marcadas al empezar.
- `read_key` lee una tecla con `termios`/`tty` en Linux y macOS y con `msvcrt.getwch` en Windows, donde descarta las teclas especiales (prefijo `\x00` o `\xe0`), así que hoy las flechas no se leen en ningún sistema.
- Los tests inyectan teclas con un lector (`tests/test_menu.py::keys`) y cubren la lectura por línea sin terminal con la fixture `lines`.

## Alcance

1. **Estudio previo sin descargas** de todos los candidatos vigentes con soporte en ComfyUI: licencia, tamaños, precisiones, codificadores, soporte nativo o por nodos, capacidades.
2. **Lista corta** propuesta al usuario (entre 4 y 6 de generación y entre 1 y 3 de edición) y aprobada por él antes de descargar nada.
3. **Script de medición** `scripts/measure_models.py`, herramienta de desarrollo fuera del paquete.
4. **Mediciones reales** en Linux de cada preseleccionado en los niveles de 8, 16, 24 y 32+ GB.
5. **Comparativa visual** con los mismos prompts y semilla, guardada junto al documento.
6. **Documento** `analysis.md` en esta carpeta con criterios, mediciones, tabla por nivel y recomendación.
7. **Decisión del usuario** sobre qué se integra en la fase 15, escrita en el documento y trasladada al roadmap.
8. **Selector múltiple con flechas** en `menu.choose_many` cuando hay terminal interactiva: flechas para moverse, espacio para marcar o desmarcar, Enter para instalar las marcadas y 0 para volver atrás.

## Fuera de alcance

- Cualquier cambio en `src/` (paquete, motor, servidor, provisionador), `models.toml` o los workflows del producto para integrar modelos. Eso es la fase 15. La única excepción es el selector múltiple (`provisioner/menu.py` y, si hace falta, `provisioner/setup.py`).
- Flechas en los menús de una sola opción (`choose`), también en los de más de 9 opciones: siguen por número.
- Cambiar la lectura por línea sin terminal o los argumentos de la CLI (`--loras`).
- Integrar en el producto nodos personalizados o una versión nueva de ComfyUI.
- LoRAs para modelos nuevos, upscaling o vídeo.
- Medir en macOS.
- Medir con una GPU de 32 GB real (no la hay).
- Modelos sin soporte en ComfyUI (ni nativo ni con nodos mantenidos).

## Decisiones

| Tema | Decisión |
|---|---|
| Candidatos de generación | Revisar al menos Stable Diffusion 3.5 (Medium y Large, y Large Turbo), Qwen-Image, HiDream-I1 (Full, Dev, Fast), Chroma, Lumina-Image 2.0, HunyuanImage, Sana, PixArt-Σ y FLUX.2, más los que hayan aparecido en la fecha del estudio con soporte en ComfyUI. Se confirma que siguen vigentes y su licencia actual en el repositorio |
| Candidatos de edición | Qwen-Image-Edit, los modelos de edición de FLUX.2 si existen, HiDream-E1, OmniGen2, Step1X-Edit y otros con soporte en ComfyUI, con prioridad a los de licencia comercial |
| Preselección | El estudio previo se hace sin descargar pesos. Se propone una lista corta con el motivo de cada descarte y **el usuario la aprueba antes de descargar**. No se descarga ningún candidato fuera de la lista aprobada |
| Licencia | Se registra: uso comercial, condiciones (umbral de ingresos, atribución, usos prohibidos), si exige aprobación o token para descargar, y el enlace al texto. Los no comerciales se miden solo si no hay alternativa comercial en su nivel o para edición |
| Herramienta | `scripts/measure_models.py`, basado en `measure_profiles.py`: arranca un ComfyUI aparte (puerto libre, carpeta temporal fuera del repositorio y de la instalación del usuario), carga workflows de prueba que viven en `scripts/measure_models/` (no en `src/`), genera con los prompts y semillas fijados, mide tiempo, pico de VRAM y pico de RAM, y escribe JSON por modelo, precisión y nivel |
| Versión de ComfyUI | La fijada en el provisionador. Si un candidato no funciona con ella, se mide con la versión mínima que lo soporte y se anota qué exigiría actualizar la fijada |
| Nodos personalizados | Solo si el modelo no tiene soporte nativo. Se anotan nombre, repositorio y commit; cuentan en contra en el criterio de integración |
| Niveles | 8, 16 y 24 GB en la RTX 4090 con `--reserve-vram` (24 − nivel GB reservados; 24 GB con la tarjeta completa). **32+ GB**: se mide la precisión más alta (bf16) en la 4090, con descarga parcial a RAM si no cabe, y se anota la VRAM que pediría sin descarga como estimación (pesos + activaciones medidas), marcada como estimada en la tabla |
| Prompts | Los tres de la fase 9 (paisaje, persona, texto `OPEN`), más uno de composición compleja y uno de estilo no fotográfico, todos con semilla `1234` a 1024×1024. Los cinco quedan escritos en el script y en `analysis.md`. Edición: dos ediciones sobre una imagen fija (cambio de cielo y añadir texto), con la misma semilla |
| Parámetros | Pasos, CFG/guía y muestreador recomendados por cada modelo en su tarjeta o en los ejemplos oficiales de ComfyUI, anotados en el documento |
| Repeticiones | Tiempo: media de 3 ejecuciones tras una de calentamiento. Memoria: pico de las 3 |
| Imágenes | Se versionan en `comparison/` de esta carpeta como JPG de unos 512 px y menos de 100 KB, más una rejilla por prompt. Los PNG completos y los pesos se quedan fuera del repositorio |
| Windows | Opcional: si el mantenedor mide el recomendado de 16 GB en Windows, se añade; si no, queda como pendiente anotado y no bloquea la fase |
| Cierre | El usuario elige qué modelos se integran en la fase 15 y para qué nivel; la decisión se escribe en `analysis.md` y en la fase 15 del roadmap |
| Idioma | Documento en español, como el resto de `specs/`; prompts y salida del script en inglés |

### Selector múltiple con flechas

| Tema | Decisión |
|---|---|
| Cuándo se usa | En `choose_many` siempre que haya lectura de teclas (terminal interactiva o lector inyectado en los tests). Sin terminal (tubería, IDE) se mantiene la línea con números separados por comas, `none` y Enter, igual que hoy. `--non-interactive` y `--loras` no cambian |
| Pantalla | Título, una línea de ayuda `↑/↓ move · Space mark · Enter install · 0 back` (sin `0 back` si no se permite volver), las opciones con `[x]` o `[ ]` y su detalle como hoy, y al final dos filas: `→ Install selected (N)` con el número de marcadas y `← Back` (solo con `allow_back`, con su `back_label`). El cursor se indica con `>` al principio de la fila |
| Teclas | ↑ y ↓ mueven el cursor por las opciones y las dos filas finales, y dan la vuelta al llegar a un extremo. Espacio marca o desmarca la opción bajo el cursor (sobre las filas finales no hace nada). Enter envía las marcadas esté donde esté el cursor, salvo sobre `← Back`, que vuelve atrás. 0 vuelve atrás desde cualquier fila. Ctrl+C sale limpio como en el resto. Cualquier otra tecla se ignora |
| Marcas iniciales | Las de hoy: `default=None` marca todas; con `default`, las indicadas (en `setup`, las LoRAs ya instaladas). Enviar sin ninguna marcada devuelve la lista vacía, que sustituye al `none` de la línea |
| Valor devuelto | El mismo que hoy: las `key` marcadas en el orden de las opciones, o `BACK`. `setup.choose_loras` no cambia de contrato |
| Lectura de flechas | `read_key` devuelve las flechas como `"UP"` y `"DOWN"`: en Linux y macOS lee la secuencia completa (`ESC [ A`/`B` y `ESC O A`/`B`) dentro del mismo modo `cbreak`, con un tiempo de espera corto tras `ESC` para distinguirlo de una pulsación de Esc sola (que se ignora); en Windows traduce `\xe0`/`\x00` seguidos de `H`/`P`. Las demás teclas especiales siguen devolviendo `""`. El lector inyectado de los tests acepta tanto los nombres como las secuencias en bruto |
| Repintado | Se redibuja la lista en el sitio con secuencias ANSI (subir el cursor y borrar líneas), sin limpiar la pantalla. En Windows se activa el procesamiento de secuencias VT de la consola con `ctypes` (`SetConsoleMode`) antes de dibujar; si no se puede activar, se vuelve a la línea con comas |
| Al terminar | Queda impresa la lista con las marcas finales y una línea con lo elegido (`Selected: a, b` o `Selected: none`), para que el historial de la terminal muestre la respuesta, como hacen los menús de una tecla |
| Menús de una opción | Sin cambios |

## Restricciones

- No se cambia código del producto ni sus datos, salvo el selector múltiple; el script de medición importa del paquete solo lo que ya expone (`catalog`, `config`, `paths`, `processes`, `spawn`), como `measure_profiles.py`.
- No se toca la instalación del usuario ni el ComfyUI gestionado: todo en carpetas temporales del script.
- Las descargas usan `HF_TOKEN` si un repositorio lo exige y no se aceptan licencias en nombre del usuario: si un modelo exige aceptar condiciones en Hugging Face, se le pide al usuario.
- Espacio en disco: antes de descargar la lista corta se suma su tamaño y se confirma con el usuario que hay sitio.
- No medir con modelos de lenguaje cargados en la GPU (el script se niega, como `measure_profiles.py`).
- `scripts/check.sh` sigue en verde (`ruff` cubre `scripts/`).
- El selector múltiple usa solo la biblioteca estándar, restaura siempre la terminal (también con Ctrl+C o una excepción) y funciona en Linux y Windows; macOS preparado sin probar.
- Los menús de una opción, la lectura por línea y el modo no interactivo se comportan exactamente igual que antes.
- Sin commits del asistente.

## Entregables

- `scripts/measure_models.py` y workflows de prueba en `scripts/measure_models/`.
- `specs/2026-11-15-analisis-modelos/analysis.md`: candidatos, descartes, criterios, mediciones, comparativa, tabla por nivel y decisión.
- `specs/2026-11-15-analisis-modelos/measurements/*.json`.
- `specs/2026-11-15-analisis-modelos/comparison/*.jpg`.
- `specs/roadmap.md`: casillas de la fase 14 y, una vez decidido, la lista de modelos de la fase 15.
- `src/imagehearth_mcp/provisioner/menu.py`: `read_key` con flechas y `choose_many` con el selector; `provisioner/setup.py` solo si el texto del paso `LoRAs` lo necesita.
- Tests en `tests/test_menu.py` y ajustes de los que hoy envían números separados por comas con un lector inyectado (`tests/test_lora_install.py`, `tests/test_setup_steps.py`, `tests/test_quality_model.py`).
