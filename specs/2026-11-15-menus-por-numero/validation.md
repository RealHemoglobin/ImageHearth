# Validación: Fase 11

Una sola puerta: la rama no se fusiona hasta que estén en verde los tests simulados, `scripts/check.sh` y las pruebas manuales en Linux, y el mantenedor haya hecho la de Windows.

## Criterios de finalización

- Una instalación completa con `setup` se hace solo con teclas numéricas, sin escribir nombres ni pulsar Enter salvo para aceptar la recomendada.
- Desde cualquier pregunta anterior a la confirmación final, 0 vuelve a la anterior con lo ya respondido; en la primera, 0 sale sin cambiar nada.
- Cada pregunta muestra `Step N of M` con el total correcto para esa ejecución.
- La confirmación final resume las respuestas y el cambio de modelo, y permite volver con 0.
- Las preguntas de sí o no de `setup`, `update`, `uninstall` y `connect` se responden con una tecla.
- `connect --detect` muestra una selección múltiple con los agentes detectados.
- Ctrl+C en cualquier pregunta sale sin traza, con código 130, sin escribir nada y con la terminal restaurada.
- El modo no interactivo, la lectura por línea sin terminal y los argumentos de la CLI siguen funcionando igual.

## Validaciones automáticas

Desde la raíz del repositorio, en Linux:

```bash
scripts/check.sh
```

Ejecuta `uv sync --locked`, `ruff`, `pytest` y los tests contra el wheel instalado en un entorno aparte. Es la puerta de calidad obligatoria de [tech-stack](../tech-stack.md); esta fase no toca workflows, así que la prueba de contrato no es obligatoria.

Los tests deben cubrir:

- [ ] Elección única: número válido, Enter para la recomendada, tecla no válida ignorada, 0 devuelve `BACK`.
- [ ] Más de 9 opciones: número y Enter, entrada no válida y reintento.
- [ ] Sí o no: `y`, `s`, `n`, mayúsculas y Enter con el valor por defecto.
- [ ] Selección múltiple: Enter acepta todas, números separados por comas, entrada no válida, 0.
- [ ] Ctrl+C lanza `KeyboardInterrupt` y la terminal se restaura (`termios` simulado).
- [ ] Lectura por línea sin terminal.
- [ ] `setup` completo solo con teclas inyectadas, con y sin ComfyUI detectado.
- [ ] 0 desde cada paso de `setup` vuelve al anterior y conserva las respuestas válidas; 0 en el primero sale con código 0 sin escribir nada.
- [ ] Cambio de perfil a uno sin `quality` quita el paso del modelo y recalcula `Step N of M`.
- [ ] Pasos resueltos por argumentos (`--profile`, `--quality-model`, `--attach`, `--managed`) no se muestran.
- [ ] Confirmación final con cambio de modelo de `quality`: aceptar y volver.
- [ ] Nada se escribe en disco antes de la confirmación final.
- [ ] `connect --detect`: todos, subconjunto y 0.
- [ ] `uninstall`, `update` y `connect --remove` con confirmación de una tecla.
- [ ] Tests no interactivos existentes sin cambios de comportamiento.
- [ ] Ningún test toca el `HOME` real.

## Validaciones manuales

En Linux, por el asistente, con `HOME` temporal y un pty real:

- [ ] `setup` en bash y en zsh hasta la confirmación final solo con teclas.
- [ ] 0 desde cada paso y cambio de perfil con el indicador de paso correcto.
- [ ] Ctrl+C en cada pregunta: sin traza, código 130, `stty -a` igual antes y después, sin `install.json`.
- [ ] `connect --detect`, `connect --remove` y `uninstall` con teclas.
- [ ] Con tubería y con `--non-interactive`: mismo comportamiento que en `main`.

En Windows:

- [ ] **Mantenedor:** `setup`, 0 para volver, Ctrl+C y `connect --detect` en PowerShell y en Windows Terminal.

## Lista para fusionar

- [x] `scripts/check.sh` en verde en Linux.
- [ ] Validaciones manuales en Linux completadas.
- [ ] **Mantenedor:** validación en Windows.
- [x] `README.md`, `README.es.md` y `docs/troubleshooting.md` actualizados.
- [ ] Roadmap con las tareas hechas marcadas y la fase como completada.
- [ ] Cambios revisados por el usuario, que realiza el commit.

## Evidencia

| Comprobación | Resultado | Fecha |
|---|---|---|
| `scripts/check.sh` | Verde: ruff, 617 tests y tests contra el wheel | 2026-11-15 |
| `setup` solo con teclas en bash | Hasta la confirmación final en un pty real, sin aceptar (no se descargó nada) | 2026-11-15 |
| `setup` solo con teclas en zsh | Igual, con `zsh -f -i` | 2026-11-15 |
| 0 desde cada paso y cambio de perfil | 0 desde confirmación, modelo y perfil en bash; el cambio de perfil con `Step N of M` recalculado, en tests simulados | 2026-11-15 |
| Ctrl+C en cada pregunta y terminal restaurada | Perfil, modelo y confirmación en bash y zsh: código 130, `stty -a` igual, sin `install.json` | 2026-11-15 |
| `connect --detect`, `connect --remove` y `uninstall` | `connect --detect` (subconjunto y 0) en pty con `HOME` temporal; `--remove` y `uninstall` solo en tests simulados | 2026-11-15 |
| Tubería y `--non-interactive` | Mismos errores y mensajes que antes (necesita `--accept-licenses` / `--profile`) | 2026-11-15 |
| Windows (PowerShell y Windows Terminal) | Pendiente: lo hace el mantenedor | — |
