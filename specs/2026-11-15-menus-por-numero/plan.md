# Plan: Fase 11

Rama: `feature/menus-por-numero`. Sin commits del asistente: los cambios se dejan en el árbol de trabajo para revisión. Los pasos marcados como **mantenedor** no los ejecuta el asistente.

Orden: primero el componente con sus tests, que no depende de nada. Después las preguntas sueltas (sí o no) en todos los comandos, que es un cambio mecánico, y por último la reorganización de `setup` en pasos, que es la parte con más riesgo.

## 1. Componente (`provisioner/menu.py`)

1. Lector de teclas: `read_key()` con `termios`/`tty.setcbreak` en POSIX y `msvcrt.getwch` en Windows, restaurando la terminal en `finally`. Ctrl+C (`\x03` en modo crudo de Windows) se convierte en `KeyboardInterrupt`.
2. `Option(key, label, detail)` y resultado `BACK` para el 0.
3. `choose(title, options, default, reader=None, allow_back=True)`: hasta 9 opciones con una tecla, Enter elige la recomendada, tecla no válida ignorada, eco de la elección en la misma línea; con más de 9, número y Enter con reintento.
4. `confirm(question, default=False, reader=None)`: `y`, `s`, `n` y Enter, sin distinguir mayúsculas.
5. `choose_many(title, options, reader=None)`: todas marcadas, Enter acepta, números separados por comas y Enter, validación y reintento, 0 para volver.
6. Modo por línea cuando no hay terminal: mismas funciones leyendo líneas de `input()`; el que llama decide la interactividad como ahora.
7. Tests en `tests/test_menu.py` con un lector inyectado: elegir por número, Enter, tecla no válida, más de 9 opciones, selección múltiple, 0, Ctrl+C y restauración de la terminal (con `termios` simulado).

## 2. Preguntas de sí o no

1. Sustituir `ask` de `setup.py` por `menu.confirm` en `setup.py`, `maintenance.py` y `connect.py`, manteniendo `ask` como alias solo si algún test o módulo externo lo necesita.
2. `uninstall`: `Continue?` y borrar modelos con una tecla.
3. `update`: licencias con una tecla.
4. `connect --remove`: `Remove them?` con una tecla.
5. Ajustar los tests que simulan `input()` para que inyecten teclas.

## 3. `connect --detect`

1. Sustituir el bucle `Connect X?` por `menu.choose_many` con los agentes detectados, todos marcados.
2. `--yes` y el modo no interactivo sin cambios.
3. Tests: aceptar todos con Enter, elegir un subconjunto, 0 para salir sin conectar nada.

## 4. `setup` por pasos

1. Separar la detección (una vez) de las preguntas: estado `Answers` con modo, carpeta, puerto, perfil, selección de modelo de `quality`.
2. Lista de pasos activos según argumentos y detección: modo (si hay ComfyUI detectado y no hay `--attach`/`--managed`/modo registrado), perfil (sin `--profile`), modelo de `quality` (perfil con `quality`, sin `--quality-model`) y confirmación final.
3. Bucle de pasos con índice: cada paso devuelve una respuesta o `BACK`; `BACK` en el primero sale con `Nothing was changed.` y código 0. Indicador `Step N of M`, recalculado cuando cambia el perfil.
4. Conservar respuestas al volver atrás: el valor por defecto de cada paso es la respuesta anterior si sigue siendo válida.
5. `choose_mode`, `choose_profile` y `choose_quality_model` reciben el valor por defecto y el menú; la rama no interactiva no cambia.
6. Confirmación final: `show_summary` más el cambio de modelo (`quality.show_change`) y `menu.choose` con 1 aceptar y 0 volver. Sustituye a `require_acceptance` y a la pregunta de `_plan_change` en interactivo; con `--accept-licenses` y `--yes` se mantiene el comportamiento actual.
7. Comprobar que nada se escribe antes de la confirmación (`records.save()` y `apply_config` después).
8. Preguntas durante la instalación (nodos personalizados, nodo de estado) con `menu.confirm`, sin 0.
9. Tests en `tests/test_provisioner.py` y `tests/test_quality_model.py`: recorrido completo solo con teclas, 0 desde cada paso, conservación de respuestas, cambio de perfil que quita el paso del modelo, Ctrl+C sin escrituras, y los tests no interactivos actuales sin cambios.

## 5. Documentación

1. `README.md` y `README.es.md`: cómo se responde a `setup` (números, Enter, 0, Ctrl+C).
2. `docs/troubleshooting.md`: la terminal no responde a las teclas o se usa desde un IDE (usar los argumentos o `--non-interactive`).
3. Marcar en el roadmap las tareas hechas.

## 6. Pruebas manuales en Linux

1. Con `HOME` temporal y `uv run` desde la rama, en bash y zsh dentro de un pty real: `setup` hasta la confirmación final solo con teclas, volver con 0 desde cada paso, cambiar el perfil y comprobar los pasos, Ctrl+C en cada pregunta y comprobar que la terminal queda bien (`stty -a` antes y después) y que no hay `install.json`.
2. `connect --detect`, `connect --remove` y `uninstall` con teclas.
3. Con tubería (`echo 1 | imagehearth-mcp setup ...`) y `--non-interactive`: mismo comportamiento que en `main`.
4. **Mantenedor:** prueba manual en Windows con PowerShell y Windows Terminal.

## 7. Validación local y cierre

1. Ejecutar `scripts/check.sh`.
2. Rellenar la evidencia en [validation.md](validation.md).
3. **Mantenedor:** revisar, hacer commit y fusionar en `main`.
4. Marcar la fase como completada en el roadmap cuando la lista de cierre esté completa.
