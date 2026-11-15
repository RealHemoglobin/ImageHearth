# Validación: Fase 10

Una sola puerta: la rama no se fusiona hasta que estén en verde los tests simulados, `scripts/check.sh` y las pruebas reales en Linux, y el mantenedor haya hecho la de Windows.

## Criterios de finalización

- Tras `uninstall`, una sesión nueva de Claude Code, Codex, opencode, Hermes y pi no muestra ImageHearth ni su skill.
- Una entrada que no creó `connect` (registro perdido, nombre `imageengine`, ámbito `local`, comando cambiado) se detecta y se retira con confirmación, o con `--yes`.
- En no interactivo sin `--yes`, las no registradas se listan con la orden para quitarlas y no se tocan.
- Las entradas de `.mcp.json` se avisan con su orden y no se editan.
- `doctor` informa de las entradas por agente y ámbito y marca las huérfanas.
- `uninstall` recuerda reiniciar los agentes y da `uv tool uninstall imagehearth-mcp`.
- Nada ajeno a ImageHearth se toca: entradas con otro comando, skills modificadas y `.mcp.json` se conservan.
- La causa real del caso de partida está documentada en la evidencia (o los escenarios probados, si no se reproduce).

## Validaciones automáticas

Desde la raíz del repositorio, en Linux:

```bash
scripts/check.sh
```

Ejecuta `uv sync --locked`, `ruff`, `pytest` y los tests contra el wheel instalado en un entorno aparte. Es la puerta de calidad obligatoria de [tech-stack](../tech-stack.md); esta fase no toca workflows, así que la prueba de contrato no es obligatoria.

Los tests deben cubrir:

- [ ] Entrada no registrada `imagehearth` con comando de ImageHearth: detectada y retirada con confirmación y con `--yes`.
- [ ] Nombre antiguo `imageengine` con `imageengine-mcp`: detectado y retirado.
- [ ] Ámbito `local` de Claude Code (`projects.<ruta>.mcpServers`): detectado y retirado sin tocar el resto del proyecto.
- [ ] `.mcp.json` en un proyecto conocido: detectado, avisado con la orden y sin editar.
- [ ] Comando cambiado por reinstalación (otra ruta de `imagehearth-mcp`): retirado.
- [ ] Entrada `imagehearth` con un comando ajeno: conservada y avisada.
- [ ] Skill sin registro e idéntica a la del paquete: retirada.
- [ ] Skill modificada por el usuario: conservada y avisada.
- [ ] Skill `imageengine`: solo avisada.
- [ ] No interactivo sin `--yes`: registradas retiradas, no registradas listadas y sin tocar, código 0.
- [ ] CLI oficial que no retira la entrada: reserva editando el archivo.
- [ ] Mismas reglas en Codex (TOML), Hermes (YAML), opencode, pi y Gemini CLI.
- [ ] Copia de seguridad antes de cada escritura.
- [ ] Archivo mal formado: error informado sin interrumpir los demás agentes.
- [ ] `doctor` y `doctor --json`: entradas por agente y ámbito, huérfanas (ejecutable inexistente, duplicadas) y sugerencia de `connect --remove`; no escribe nada.
- [ ] Avisos finales de reinicio y `uv tool uninstall imagehearth-mcp`.
- [ ] Ningún test toca el `HOME` real.

## Validaciones manuales

En Linux, por el asistente, con `HOME` temporal:

- [ ] Diagnóstico: escenarios de la tarea 1 del plan reproducidos y causa anotada.
- [ ] Prueba real con Claude Code: conectar, añadir `imageengine` en ámbito `local`, `uninstall`, y `claude mcp list` sin ImageHearth en ningún ámbito.
- [ ] Sesión nueva de Claude Code sin herramientas ni skill de ImageHearth.
- [ ] Ciclo conectar y desinstalar con Codex, opencode, Hermes y pi (los que estén instalados), comprobando su archivo.
- [ ] Entrada con comando ajeno y skill modificada conservadas tras `uninstall`.
- [ ] `doctor` tras `uv tool uninstall` sin `uninstall` previo marca las entradas como huérfanas (ejecutando `doctor` desde la rama con `uv run`).

En Windows:

- [ ] **Mantenedor:** reproducir el caso de partida y el ciclo conectar, `uninstall`, `claude mcp list` y sesión nueva.

## Lista para fusionar

- [ ] `scripts/check.sh` en verde en Linux.
- [ ] Validaciones manuales en Linux completadas.
- [ ] **Mantenedor:** validación en Windows.
- [ ] `README.md`, `README.es.md`, `docs/agents.md`, `docs/troubleshooting.md` y `tech-stack.md` actualizados.
- [ ] Roadmap con las tareas hechas marcadas y la fase como completada.
- [ ] Cambios revisados por el usuario, que realiza el commit.

## Evidencia

### Diagnóstico

Linux, `HOME` temporal, Claude Code 2.1.322, `imagehearth-mcp` 0.1.0b3 instalado con `uv tool install` desde el commit de partida (código anterior a la fase). Causa en cada caso: lo que `uninstall` anterior no miraba.

| Escenario | ¿Deja ImageHearth visible? | Archivo o ámbito | Fecha |
|---|---|---|---|
| `connect claude-code` + `uninstall` con registro intacto | No: `claude mcp list` sin ImageHearth | (entrada `user` retirada) | 2026-11-15 |
| Entrada `imageengine` añadida a mano (`claude mcp add --scope user`) y `uninstall` | **Sí** | `~/.claude.json`, raíz `mcpServers`, ámbito `user` | 2026-11-15 |
| Entrada `imagehearth` en ámbito `local` de un proyecto y `uninstall` | **Sí** | `~/.claude.json`, `projects.<ruta>.mcpServers`, ámbito `local` | 2026-11-15 |
| Entrada en `.mcp.json` del proyecto (ámbito `project`) y `uninstall` | **Sí** ("Pending approval") | `<proyecto>/.mcp.json` | 2026-11-15 |
| Registro `install.json` perdido y `uninstall` | **Sí**: el comando responde «No install record found: nothing was removed» y no mira los agentes | `~/.claude.json`, ámbito `user` | 2026-11-15 |
| `uv tool uninstall` sin `uninstall` previo | Entrada `user` apuntando a un ejecutable que ya no existe; `doctor` anterior no la mostraba | `~/.claude.json` | 2026-11-15 |
| Skill copiada sin registro | Se queda en `~/.claude/skills/imagehearth` (por el código: `_remove_skill` exige registro; no se probó con el código antiguo, sí con el nuevo, que la retira por ser idéntica) | `~/.claude/skills/imagehearth` | 2026-11-15 |
| Comando cambiado por reinstalación con `uv` (otra ruta) | Por el código, `_remove_entry` devolvía `changed` y la dejaba; cubierto por test simulado, no reproducido con `uv` real | `~/.claude.json` | 2026-11-15 |
| Sesión de Claude Code abierta durante la desinstalación | No reproducido: `claude -p` no deja una sesión interactiva abierta; el aviso de reinicio cubre la causa conocida | — | 2026-11-15 |

La causa más probable del caso de partida es la combinación de **registro perdido** (el comando salía sin mirar los agentes) o una entrada **a mano / con el nombre antiguo / en otro ámbito**. Con `~/.claude.json` ya limpio el 2026-11-15 no se puede saber cuál fue exactamente.

### Comprobaciones

| Comprobación | Resultado | Fecha |
|---|---|---|
| `scripts/check.sh` | Verde: `ruff` limpio, 571 tests pasan en el repositorio y contra el wheel instalado | 2026-11-15 |
| Prueba real Claude Code con el código nuevo: registro perdido + `imageengine` (`user`) + `imagehearth` (`local`) + `.mcp.json`, `uninstall --yes` | `user` y `local` retiradas; `.mcp.json` avisado con la orden y sin editar; tras retirarlo a mano, `claude mcp list` sin ImageHearth | 2026-11-15 |
| Sesión nueva de Claude Code (`claude mcp list` desde la carpeta del proyecto) tras `uninstall` | Sin ImageHearth ni skill | 2026-11-15 |
| `connect --remove claude-code` sin `--yes` y sin terminal | Entrada no registrada listada con la orden `connect --remove claude-code --yes`, sin tocar, código 0; con `--yes` la retira junto con la skill idéntica | 2026-11-15 |
| Ciclo `connect` + `uninstall` con Claude Code, Codex, opencode y pi (`HOME` temporal) | Sin `imagehearth` en ningún archivo de configuración; `codex mcp list` y `pi mcp list` sin servidores. Hermes no está instalado: solo cubierto por tests simulados. `opencode` no estaba en el `PATH` de la prueba: solo se comprobó el archivo | 2026-11-15 |
| Entrada `imagehearth` con comando ajeno y skill modificada tras `uninstall` | Ambas conservadas y avisadas | 2026-11-15 |
| `doctor` desde la rama tras `uv tool uninstall` sin `uninstall` | Capa `agents` en aviso, entradas marcadas `ORPHAN` y `fix` con `connect --remove` por agente | 2026-11-15 |
| Windows | Pendiente: lo hace el mantenedor | — |
