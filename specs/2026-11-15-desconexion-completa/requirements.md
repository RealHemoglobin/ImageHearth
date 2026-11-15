# Fase 10: Desconexión completa de agentes

## Contexto

Fase 10 del [roadmap](../roadmap.md). Objetivo: tras `imagehearth-mcp uninstall` o `connect --remove`, ningún agente sigue mostrando ImageHearth, ni el servidor MCP ni la skill. Depende de la fase 5. Es independiente de las fases 11 y 14.

Origen: después de desinstalar, ImageHearth seguía apareciendo en Claude Code. El 2026-11-15 `~/.claude.json` ya no tenía la entrada, así que la causa real hay que reproducirla.

Estado de partida, comprobado el 2026-11-15 en `provisioner/connect.py`:

- `CLIENTS` define Claude Code, Claude Desktop, Codex, Gemini CLI, opencode, Hermes, pi, VS Code, Cursor y el resto de editores con su archivo, su clave (`mcpServers`, `mcp_servers`, `mcp`, `servers`) y, si existe, la CLI oficial para añadir y quitar. Claude Code y Gemini CLI solo usan `--scope user`.
- `disconnect_all(records)`, llamado desde `maintenance.py` en `uninstall`, solo recorre `records.connections` (lo que `connect` registró en `install.json`).
- `_remove_entry(client, path, command)` solo mira la clave `SERVER_NAME` (`imagehearth`). Si el comando guardado no coincide con el de la entrada, devuelve `changed` y la deja.
- `_remove_skill` solo borra `skills/imagehearth` si `records.is_owned(target)`.
- `disconnect(client)` (`connect --remove`) llama a `_remove_entry` sin comando, así que retira la entrada `imagehearth` del archivo por defecto aunque no esté registrada, pero no mira otros ámbitos ni el nombre `imageengine`.
- `doctor.py` no informa de las conexiones con agentes.

Causas posibles, según el roadmap: entradas no registradas o con el nombre antiguo `imageengine`, ámbitos `local` y `project` de Claude Code, comando cambiado por una reinstalación con `uv`, skill instalada antes del registro, sesión abierta que conserva las herramientas y `uv tool uninstall` sin pasar por `uninstall`.

## Alcance

Todo lo del roadmap para la fase 10 en una sola rama:

1. **Diagnóstico:** reproducir el caso en Linux con Claude Code y documentar la causa real en esta spec. Windows lo reproduce el mantenedor.
2. **Búsqueda:** módulo nuevo que encuentra las entradas `imagehearth` e `imageengine` y las skills `imagehearth` en cada agente conocido y en cada ámbito de Claude Code, y las clasifica.
3. **Desconexión:** `uninstall` y `connect --remove` retiran todas las entradas de ImageHearth (registradas o no) y las skills que coinciden con la del paquete.
4. **`doctor`:** informa de las entradas encontradas por agente y ámbito, con el comando y las huérfanas.
5. **Avisos finales:** reiniciar los agentes abiertos y `uv tool uninstall imagehearth-mcp`.
6. **Documentación y pruebas.**

## Fuera de alcance

- Editar `.mcp.json` (ámbito `project`): suele estar versionado; solo se avisa y se da la orden.
- Retirar skills con el nombre antiguo `imageengine`: solo se avisa en `doctor` y `uninstall`.
- Buscar `.mcp.json` en carpetas que `~/.claude.json` no conozca (no se recorre el disco).
- Cerrar o reiniciar agentes abiertos.
- Ejecutar `uv tool uninstall` desde el propio comando.
- Cambiar cómo `connect` añade la entrada (sigue en el ámbito `user`).
- Publicar una versión nueva en PyPI.

## Decisiones

| Tema | Decisión |
|---|---|
| Nombres buscados | `imagehearth` e `imageengine` como clave del servidor en la sección MCP de cada cliente |
| Entrada nuestra | El comando (primer elemento, o `command`/`url` según el formato) es un ejecutable llamado `imagehearth-mcp` o `imageengine-mcp` (con o sin `.exe`), exista o no. Cualquier otro comando es ajeno: se deja y se dice cuál y dónde |
| Registradas | Se retiran como ahora, aunque el comando haya cambiado por una reinstalación, si sigue siendo de ImageHearth |
| No registradas, interactivo | Se listan (agente, ámbito, archivo, comando) y se retiran tras una confirmación, con copia de seguridad |
| No registradas, `--yes` | Se retiran sin preguntar, con copia de seguridad |
| No registradas, no interactivo sin `--yes` | Se retiran las registradas; las no registradas se listan con la orden para quitarlas (`connect --remove <agente> --yes`) y el comando termina con un aviso, sin fallar ni tocarlas |
| Ámbitos de Claude Code | `user` (`mcpServers` raíz de `~/.claude.json`), `local` (`projects.<ruta>.mcpServers`) y `project` (`<ruta>/.mcp.json` de cada proyecto que conozca `~/.claude.json`) |
| `.mcp.json` | Solo aviso con la orden (`claude mcp remove --scope project imagehearth` en esa carpeta) |
| CLI oficial | Se usa cuando existe, con el ámbito correspondiente (`--scope local` ejecutado con `cwd` en la carpeta del proyecto). Después se comprueba en el archivo que la entrada ya no está; si sigue, se edita el archivo como reserva |
| Otros agentes | Codex, opencode, Hermes, pi, Gemini CLI, Claude Desktop y los editores con archivo: mismas reglas en su archivo de configuración |
| Skills | Se retira `skills/imagehearth` si consta como propia o si su `SKILL.md` coincide byte a byte con el del paquete. Una carpeta con `SKILL.md` distinto se deja y se avisa |
| Huérfana (para `doctor`) | Entrada nuestra cuyo ejecutable no existe, o segunda entrada de ImageHearth en el mismo agente (duplicada entre nombres o ámbitos) |
| Módulo | `provisioner/agent_scan.py`: encuentra entradas y skills y devuelve hallazgos estructurados. `connect.py` y `doctor.py` lo usan; `connect.py` mantiene la escritura y las copias |
| Avisos al terminar | `uninstall` y `connect --remove` recuerdan reiniciar los agentes abiertos; `uninstall` da además `uv tool uninstall imagehearth-mcp` |

## Restricciones

- Nada ajeno a ImageHearth se toca: ni entradas con otro comando, ni skills modificadas, ni `.mcp.json`.
- Copia de seguridad antes de cada escritura, con el mecanismo actual (`_backup`).
- Funciona en Linux, Windows y macOS: rutas con `pathlib` y comparación de nombres de ejecutable sin depender de mayúsculas ni de `.exe` en Windows.
- `doctor` no escribe nada.
- La salida de `doctor --json` mantiene su estructura estable; se añade una capa nueva al final.
- Los tests simulados no tocan el `HOME` real (HOME y variables `*_HOME` temporales).
- Sin commits del asistente.

## Entregables

- `src/imagehearth_mcp/provisioner/agent_scan.py`.
- `connect.py`: `disconnect` y `disconnect_all` sobre los hallazgos del escaneo, confirmación y avisos.
- `maintenance.py`: `uninstall` con los avisos finales y la lista de no registradas.
- `doctor.py`: capa de agentes en texto y `--json`.
- Tests en `tests/test_agent_scan.py` y ampliaciones de `tests/test_connect.py`.
- `README.md`, `README.es.md`, `docs/agents.md` y `docs/troubleshooting.md` actualizados.
- Diagnóstico y evidencia en [validation.md](validation.md).

## Supuestos abiertos

- La causa real del caso de partida puede no reproducirse. Si no aparece, se documentan los escenarios probados y la fase sigue con todas las medidas del roadmap, que cubren las causas posibles.
