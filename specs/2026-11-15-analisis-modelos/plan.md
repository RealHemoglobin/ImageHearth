# Plan: Fase 14

Rama: `feature/analisis-modelos`. Sin commits del asistente: los cambios se dejan en el árbol de trabajo para revisión. Los pasos marcados como **usuario** o **mantenedor** no los ejecuta el asistente.

Orden: primero el estudio sin descargas y la lista corta, que el usuario aprueba; después la herramienta, las mediciones y la comparativa; por último el documento y la decisión. La tarea 2 es una parada obligatoria. La tarea 10 (selector múltiple con flechas) no depende del análisis: se puede hacer mientras se espera la aprobación de la tarea 2 o al final, antes de la validación.

## 1. Estudio previo (sin descargas)

1. Revisar los candidatos de generación y edición de [requirements](requirements.md#decisiones) y buscar los aparecidos después, con soporte en ComfyUI (nativo o con nodos mantenidos).
2. Para cada uno, anotar en un borrador de `analysis.md`: repositorio y revisión en Hugging Face, licencia y condiciones, si exige aprobación, precisiones disponibles (bf16, fp8, GGUF, NF4…) y tamaño de cada una, codificadores de texto y VAE (y si se comparten con los ya instalados: T5, CLIP-L, VAE de FLUX), soporte en la versión fijada de ComfyUI, capacidades (generación, edición, texto legible, resoluciones) y VRAM declarada.
3. Proponer la lista corta: entre 4 y 6 de generación y entre 1 y 3 de edición, cubriendo los cuatro niveles y al menos una alternativa comercial por nivel si existe. Cada descarte con su motivo.
4. Sumar el tamaño de descarga de la lista corta.

## 2. Aprobación de la lista corta (**usuario**)

1. Presentar la lista corta, los descartes, el tamaño total y las licencias que exigen aceptar condiciones en Hugging Face.
2. El usuario aprueba, quita o añade candidatos y confirma que hay espacio. Anotar la lista aprobada y la fecha en `analysis.md`.
3. Si algún repositorio exige aceptar condiciones o `HF_TOKEN`, lo hace el usuario.

## 3. Herramienta de medición

1. `scripts/measure_models.py`: partiendo de `measure_profiles.py`, arrancar ComfyUI aparte en un puerto libre con carpetas de modelos y salida temporales, con `--reserve-vram` según el nivel pedido (`--tier 8|16|24|32`).
2. Workflows de prueba en `scripts/measure_models/<modelo>-<precision>.json` (generación) y `<modelo>-edit.json` (edición), con marcadores para prompt, semilla, tamaño e imagen de entrada.
3. Prompts y semilla fijos en el script (los tres de la fase 9 y los dos nuevos de composición compleja y estilo; dos ediciones sobre una imagen fija).
4. Por ejecución: una de calentamiento y tres medidas; registrar tiempo medio, pico de VRAM, pico de RAM, si hubo descarga parcial a RAM, versión de ComfyUI, nodos personalizados y errores (incluido OOM).
5. Salida: JSON en `measurements/<modelo>-<precision>-<nivel>.json` e imágenes PNG en una carpeta fuera del repositorio.
6. Descarga de pesos a una carpeta temporal fuera del repositorio, verificando tamaño y SHA-256 anotados en el estudio.
7. `ruff` limpio; `scripts/check.sh` en verde.

## 4. Mediciones en Linux

1. Para cada modelo y precisión de la lista aprobada, medir en los niveles 8, 16 y 24 GB en los que pueda caber (con descarga parcial a RAM si el modelo la admite). Un nivel donde no funciona se anota como no cabe, con el error.
2. Nivel 32+ GB: medir bf16 en la tarjeta completa; si necesita descarga parcial, anotar la VRAM estimada sin descarga y marcarla como estimada.
3. Si un candidato no funciona con la versión fijada de ComfyUI, medirlo con la mínima que lo soporte y anotarlo.
4. Medir las ediciones de los modelos de edición de la lista, y Kontext como referencia.

## 5. Comparativa visual

1. Convertir las imágenes de cada modelo (precisión más alta medida) a JPG de unos 512 px y menos de 100 KB en `comparison/`.
2. Montar una rejilla por prompt con los modelos de la lista y FLUX.1 Dev, FLUX.1 Schnell y SDXL 1.0 como referencia (de la fase 9 o regenerados con el mismo script).
3. Rejilla de edición con Kontext como referencia.

## 6. Medición en Windows (**mantenedor**, opcional)

1. Medir en Windows el recomendado para 16 GB con `scripts/measure_models.py`.
2. Si no se hace, anotarlo como pendiente en la [evidencia](validation.md#evidencia).

## 7. Documento `analysis.md`

1. Secciones: candidatos y descartes; lista aprobada; criterios (licencia, memoria, calidad, velocidad, integración, capacidades); parámetros usados por modelo; tabla de mediciones por modelo, precisión y nivel; comparativa con las rejillas; notas de calidad por prompt (texto legible, manos y caras, composición, estilo).
2. Tabla final por nivel (8, 16, 24, 32+ GB): recomendado para `quality`, para edición y alternativa de licencia comercial, con la VRAM y el tiempo medidos (o estimados en 32+).
3. Propuesta: qué se integra en la fase 15, qué se descarta y por qué, qué perfiles o variantes de la escalera de la fase 7 cambian, nodos personalizados o versión de ComfyUI que exigiría.

## 8. Decisión (**usuario**)

1. El usuario revisa el documento y decide qué modelos se integran y para qué nivel.
2. Escribir la decisión con fecha en `analysis.md`.
3. Actualizar el roadmap: marcar las casillas de la fase 14 y concretar en la fase 15 los modelos elegidos. No cambiar el estado de otras fases.

## 9. Validación final

1. Rellenar la [evidencia](validation.md#evidencia).
2. `scripts/check.sh` en verde.
3. `git status --short`: solo cambios en `scripts/`, esta carpeta de specs, el roadmap y los ficheros del selector (tarea 10).

## 10. Selector múltiple con flechas

1. `read_key`: devolver `"UP"` y `"DOWN"`. En Linux y macOS, tras leer `ESC` dentro del mismo `cbreak`, esperar con `select` un tiempo corto (unos 50 ms) y leer `[`/`O` y la letra; Esc solo o secuencias desconocidas devuelven `""`. En Windows, traducir `\xe0`/`\x00` + `H`/`P` en lugar de descartarlos.
2. `_Reader.key`: normalizar también las secuencias en bruto (`\x1b[A`, `\x1b[B`, `\x1bOA`, `\x1bOB`) que lleguen carácter a carácter desde un lector inyectado, para que los tests puedan usar cualquiera de las dos formas.
3. `choose_many` en modo teclas: estado con cursor y marcas; dibujar título, ayuda, opciones, `→ Install selected (N)` y `← Back`; repintar en el sitio con ANSI tras cada tecla (subir tantas líneas como se dibujaron y borrarlas); aplicar las teclas de [requirements](requirements.md#selector-múltiple-con-flechas); al terminar, dejar la lista final y `Selected: ...`.
4. Windows: activar el procesamiento VT de la consola con `ctypes` (`GetStdHandle`, `GetConsoleMode`, `SetConsoleMode` con `ENABLE_VIRTUAL_TERMINAL_PROCESSING`); si falla, usar la línea con comas.
5. Mantener la rama por línea (sin terminal) tal como está, con números separados por comas, `none` y Enter.
6. Revisar el texto del paso `LoRAs` en `setup.choose_loras`; cambiarlo solo si menciona la entrada por comas.
7. Tests en `tests/test_menu.py`: moverse con ↓/↑ y marcar con espacio; vuelta al llegar a los extremos; desmarcar; Enter desde una opción y desde `Install selected`; Enter sobre `← Back` y 0 devuelven `BACK`; enviar sin marcadas devuelve `[]`; marcas iniciales con `default=None` y con `default`; teclas desconocidas y Esc ignoradas; Ctrl+C; sin `allow_back` no aparece `← Back` y 0 se ignora; secuencias en bruto y nombres; el contador `(N)` se actualiza; la línea `Selected:` final.
8. Tests de `read_key` con `termios`/`select` y `msvcrt` simulados: flechas, Esc solo y teclas especiales desconocidas.
9. Ajustar los tests que hoy envían números separados por comas con lector inyectado (`test_lora_install.py`, `test_setup_steps.py`, `test_quality_model.py`): pasar a flechas y espacio, o a la fixture de lectura por línea donde lo que se prueba es la entrada por comas. Anotar en la validación los tests cambiados.
10. Prueba manual en un pty real en Linux (bash y zsh): `setup` con SDXL 1.0 en un `HOME` temporal, paso `LoRAs`, sin llegar a descargar; comprobar repintado, Ctrl+C con la terminal restaurada y 0 volviendo al paso anterior.
11. Prueba manual en Windows (PowerShell y Windows Terminal) por el **mantenedor**, opcional como el resto de Windows de la fase.
12. Roadmap: marcar las casillas del apartado del selector en la fase 14.
