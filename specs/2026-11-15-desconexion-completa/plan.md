# Plan: Fase 10

Rama: `feature/desconexion-completa`. Sin commits del asistente: los cambios se dejan en el árbol de trabajo para revisión. Los pasos marcados como **mantenedor** no los ejecuta el asistente.

Orden: primero el diagnóstico, que puede cambiar el peso de cada medida. Después el escaneo, que es la base de la desconexión y de `doctor`, la desconexión, `doctor`, documentación y pruebas reales.

## 1. Diagnóstico en Linux

1. Con un `HOME` temporal y el paquete instalado con `uv tool install` desde la rama: `setup` mínimo o solo `connect claude-code`, comprobar `claude mcp list`, `uninstall` y volver a comprobar.
2. Repetir con los escenarios del roadmap: entrada añadida a mano con `imageengine`, entrada en ámbito `local`, `uv tool uninstall` y reinstalación (comando en otra ruta), skill copiada sin registro y una sesión de Claude Code abierta durante la desinstalación.
3. Anotar en la evidencia de [validation.md](validation.md) qué escenario deja ImageHearth visible y qué archivo o ámbito retenía la entrada. Si alguno no se reproduce, decirlo.

## 2. Escaneo (`provisioner/agent_scan.py`)

1. Tipo `Finding`: agente, ámbito (`user`, `local`, `project` o `file`), archivo, carpeta de proyecto si la hay, nombre (`imagehearth`/`imageengine`), comando, si es nuestra, si está registrada, si el ejecutable existe y si es editable (`.mcp.json` no).
2. `is_ours(command)`: nombre del ejecutable `imagehearth-mcp` o `imageengine-mcp`, con o sin `.exe`, sin distinguir mayúsculas en Windows. Reutilizar `_command_of` de `connect.py` moviéndolo al módulo nuevo o importándolo.
3. Escaneo por cliente de `CLIENTS` con su lector actual (`_read_config`), buscando ambos nombres bajo `client.key`.
4. Claude Code: ámbito `user` en la raíz de `~/.claude.json`, ámbito `local` en `projects.<ruta>.mcpServers` y ámbito `project` leyendo `<ruta>/.mcp.json` de cada proyecto listado, si existe.
5. Skills: para cada cliente con `skills`, carpeta `imagehearth` con estado `owned` (registro), `identical` (`SKILL.md` igual al del paquete), `modified` o `absent`; carpeta `imageengine` solo informada.
6. Huérfanas: ejecutable inexistente o más de una entrada nuestra en el mismo agente.
7. Archivos ilegibles o mal formados: hallazgo con error, sin interrumpir el resto.
8. Tests en `tests/test_agent_scan.py`.

## 3. Retirada en `connect.py`

1. `_remove_entry` generalizado a un hallazgo: nombre y ámbito concretos, criterio `is_ours` en lugar de comparar con el comando registrado.
2. CLI oficial por ámbito: `claude mcp remove --scope user|local <nombre>` (en `local`, `cwd` = carpeta del proyecto), `gemini mcp remove`, `pi mcp remove`. Tras la CLI, releer el archivo; si la entrada sigue, editar el archivo como reserva.
3. Edición directa para `local` cuando no hay CLI o falla: quitar `projects.<ruta>.mcpServers.<nombre>` conservando el resto del JSON.
4. `.mcp.json`: no se edita; aviso con la orden `claude mcp remove --scope project <nombre>` y la carpeta.
5. Entradas ajenas (comando de otro programa): se dejan y se dice agente, archivo y comando.
6. Skills: retirar `owned` e `identical`; avisar de `modified` y de `imageengine`.
7. Confirmación de no registradas: lista y pregunta en interactivo; `--yes` las retira; no interactivo sin `--yes` las lista con `connect --remove <agente> --yes` y termina con aviso y código 0.
8. `disconnect(client)` y `disconnect_all(records)` sobre el escaneo; `records.connections` se limpia de lo retirado.
9. Tests en `tests/test_connect.py`.

## 4. `uninstall` y `connect --remove`

1. `maintenance.py`: `uninstall` usa la nueva desconexión, pasa `--yes` e interactividad y acumula fallos como ahora.
2. Al terminar, ambos comandos recuerdan reiniciar los agentes abiertos. `uninstall` da también `uv tool uninstall imagehearth-mcp`.
3. Si quedan no registradas o `.mcp.json` sin retirar, resumen final con las órdenes.
4. Tests de la salida y de que no se toca nada ajeno.

## 5. `doctor`

1. Capa nueva `agents` al final de las capas de `--json`: por agente y ámbito, nombre, archivo, comando, registrada, nuestra, huérfana, y skills.
2. Texto: una línea por entrada; las huérfanas en aviso con `connect --remove <agente>`.
3. Que `doctor` no escriba nada (test).
4. Tests de texto y `--json`.

## 6. Documentación

1. `README.md` y `README.es.md`: qué hace `uninstall` con los agentes, el reinicio y `uv tool uninstall`.
2. `docs/agents.md`: ámbitos de Claude Code y qué se retira en cada uno.
3. `docs/troubleshooting.md`: "ImageHearth sigue apareciendo tras desinstalar", con `doctor` y `connect --remove`.
4. `tech-stack.md`: fila de decisión sobre desconexión por nombre y ámbitos.

## 7. Pruebas reales en Linux

1. Prueba real etiquetada con Claude Code (`HOME` temporal): conectar, añadir a mano `imageengine` en ámbito `local`, desinstalar y comprobar que `claude mcp list` no muestra ImageHearth en ningún ámbito.
2. Repetir el ciclo con Codex, opencode, Hermes y pi si están instalados, comprobando su archivo y una sesión nueva.
3. Comprobar que una entrada `imagehearth` con un comando ajeno y una skill modificada se conservan.
4. **Mantenedor:** reproducir el caso y el ciclo completo en Windows.

## 8. Validación local y cierre

1. Ejecutar `scripts/check.sh`.
2. Rellenar la evidencia en [validation.md](validation.md) y marcar en el roadmap las tareas hechas.
3. **Mantenedor:** revisar, hacer commit y fusionar en `main`.
4. Marcar la fase como completada en el roadmap cuando la lista de cierre esté completa.
