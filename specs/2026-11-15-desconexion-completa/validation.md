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

| Escenario | ¿Deja ImageHearth visible? | Archivo o ámbito | Fecha |
|---|---|---|---|

### Comprobaciones

| Comprobación | Resultado | Fecha |
|---|---|---|
