# Fase 11: Menús por número en `setup`

## Contexto

Fase 11 del [roadmap](../roadmap.md). Objetivo: responder a `setup` sin escribir nombres. Cada pregunta muestra opciones numeradas, se elige con una sola tecla sin pulsar Enter y la 0 vuelve a la pregunta anterior. Depende de las fases 3 y 9. Es independiente de las fases 10 y 14; las fases 12 y 13 usarán el componente de esta.

Estado de partida, comprobado el 2026-11-15:

- `provisioner/setup.py` pregunta con `input()`: modo de ComfyUI (`Choice [1]:`, solo si se detecta un ComfyUI existente), perfil (`Profile [quality]:`) y modelo de `quality` (`Quality model [flux-dev]:`). Un nombre mal escrito lanza `ProvisionError` y aborta la instalación.
- `ask(question)` en `setup.py` es la única pregunta de sí o no (`[y/N]`, con Enter). La usan `setup.py` (cambio a SDXL desde RealVisXL, cambio de modelo de `quality`, licencias, nodos personalizados, nodo de estado), `maintenance.py` (licencias en `update`, `Continue?` y borrar modelos en `uninstall`) y `connect.py` (`Remove them?` en `--remove`, `Connect X?` por agente en `--detect`).
- El orden de `_setup` es: detección, `choose_mode`, `choose_profile`, `choose_quality_model`, `_plan_change` (confirmación del cambio de modelo), `show_summary` y `require_acceptance` (licencias). Después ya instala.
- La interactividad se decide con `is_interactive(args)` (`--non-interactive` y `sys.stdin.isatty()`) en `setup` y con `sys.stdin.isatty()` en `update`, `uninstall` y `connect`.
- `cli.py` captura `KeyboardInterrupt` y sale con 130 y el mensaje `Interrupted. Run the same command again to continue.`
- La precisión (fp8, GGUF) no se pregunta: se elige por VRAM o con `--variant`.

## Alcance

1. **Componente de menú** en `provisioner/menu.py`: elección única numerada, sí o no de una tecla, selección múltiple y modo por línea sin terminal.
2. **Migrar todas las preguntas existentes** de `setup`, `update`, `uninstall` y `connect` (`--detect` y `--remove`) al componente.
3. **`setup` por pasos con estado:** modo, perfil, modelo de `quality` y confirmación final, con 0 para volver atrás e indicador de paso.
4. **`connect --detect`** como lista de selección múltiple.
5. **Pruebas y documentación.**

## Fuera de alcance

- Pregunta de carpeta de instalación: llega con la [fase 12](../roadmap.md#fase-12-carpeta-de-instalación), que usará el componente.
- Pregunta de LoRAs: llega con la [fase 13](../roadmap.md#fase-13-loras-para-sdxl-10).
- Pregunta nueva para elegir la variante o precisión: sigue eligiéndose por VRAM o con `--variant`.
- Menús con flechas, colores o interfaz a pantalla completa.
- Dependencias nuevas (`readchar`, `questionary`, `prompt_toolkit`).
- Cambiar argumentos de la CLI o el comportamiento no interactivo.
- Volver atrás después de la confirmación final: las preguntas durante la instalación (nodos personalizados) son de sí o no de una tecla, sin 0.

## Decisiones

| Tema | Decisión |
|---|---|
| Alcance | Solo las preguntas que existen hoy. El componente queda listo para las fases 12 y 13 |
| Módulo | `provisioner/menu.py`, solo biblioteca estándar, sin dependencias nuevas |
| Lectura de una tecla | `termios`/`tty` (modo `cbreak`) en Linux y macOS y `msvcrt.getwch` en Windows. La terminal se restaura siempre en un `finally` |
| Lector inyectable | Las funciones del menú reciben un lector de teclas (por defecto el de la terminal) para probar con secuencias de teclas sin terminal |
| Elección única, hasta 9 opciones | Opciones del 1 al 9; la recomendada marcada (`(recommended)`) y elegida con Enter. Un número válido elige al instante y la elección se muestra en la misma línea. Tecla no válida: se ignora sin mensaje |
| Elección única, más de 9 opciones | Se escribe el número y Enter; Enter vacío elige la recomendada; entrada no válida vuelve a preguntar |
| Sí o no | Una tecla: `y` o `s` sí, `n` no, Enter el valor por defecto (no, salvo que se indique). Mayúsculas aceptadas. Se muestra la respuesta en la misma línea |
| Selección múltiple | Lista numerada con todas marcadas por defecto; Enter acepta las marcadas; se escriben números separados por comas y Enter para elegir otras. `0` vuelve atrás o sale si es la primera pregunta |
| 0 | En las preguntas de los pasos de `setup` vuelve al paso anterior; en la primera pregunta sale sin cambiar nada (código 0 y `Nothing was changed.`). En las preguntas sueltas (`update`, `uninstall`, `connect`) 0 equivale a no o a salir sin cambios |
| Volver atrás | Las respuestas posteriores se conservan como valor por defecto si siguen siendo válidas (por ejemplo, el modelo de `quality` al volver al perfil y elegir otro con `quality`). La detección de hardware no se repite |
| Pasos de `setup` | Modo de ComfyUI (solo si se detecta uno), perfil, modelo de `quality` (solo con perfil que lo tenga y sin `--quality-model`) y confirmación final. Los pasos resueltos por argumentos de la CLI no se muestran ni cuentan |
| Indicador de paso | `Step 2 of 4` antes de cada pregunta, con el total de pasos que se van a mostrar en esta ejecución. Se recalcula si una respuesta cambia los pasos siguientes (perfil sin `quality`) |
| Confirmación final | Resume modo, carpeta, perfil, modelo y precisión, descargas y licencias, e incluye el cambio de modelo de `quality` si lo hay. Opciones: 1 aceptar e instalar, 0 volver al paso anterior. Sustituye a las preguntas separadas de licencias y de cambio de modelo |
| Cambio a SDXL desde RealVisXL | Sigue siendo una pregunta de sí o no dentro del paso del modelo de `quality` |
| `connect --detect` | Una selección múltiple con los agentes detectados, todos marcados. Sustituye a `Connect X?` por agente |
| Ctrl+C | En cualquier pregunta sale sin traza, con el mensaje y el código 130 actuales, restaurando la terminal. Antes de la confirmación final no se ha escrito nada |
| Sin terminal | Si no hay terminal interactiva (`stdin` no es TTY, IDE, tubería) o hay `--non-interactive`, se mantiene la lectura por línea (número o Enter) o el error con los argumentos necesarios, como ahora |
| Idioma | Interfaz en inglés, como el resto de la CLI |

## Restricciones

- Ningún cambio en el modo no interactivo ni en los argumentos de la CLI: `agent_setup.py` y las pruebas actuales siguen funcionando igual.
- La terminal queda siempre en su modo original, también con Ctrl+C o una excepción.
- Funciona en Linux, Windows y macOS; macOS preparado sin probar.
- Antes de la confirmación final, `setup` no escribe nada en disco (ni `install.json` ni `config.toml`).
- Los tests simulados no usan una terminal real ni tocan el `HOME` real.
- Sin commits del asistente.

## Entregables

- `src/imagehearth_mcp/provisioner/menu.py`.
- `setup.py` reorganizado en pasos con estado; `ask` sustituido por el componente.
- `maintenance.py` y `connect.py` usando el componente; `connect --detect` con selección múltiple.
- Tests en `tests/test_menu.py` y ampliaciones de `tests/test_provisioner.py`, `tests/test_quality_model.py` y `tests/test_connect.py`.
- `README.md`, `README.es.md` y `docs/troubleshooting.md` actualizados.
- Evidencia en [validation.md](validation.md).
