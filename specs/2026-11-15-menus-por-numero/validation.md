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

- [ ] `scripts/check.sh` en verde en Linux.
- [ ] Validaciones manuales en Linux completadas.
- [ ] **Mantenedor:** validación en Windows.
- [ ] `README.md`, `README.es.md` y `docs/troubleshooting.md` actualizados.
- [ ] Roadmap con las tareas hechas marcadas y la fase como completada.
- [ ] Cambios revisados por el usuario, que realiza el commit.

## Evidencia

| Comprobación | Resultado | Fecha |
|---|---|---|
| `scripts/check.sh` | Pendiente | — |
| `setup` solo con teclas en bash | Pendiente | — |
| `setup` solo con teclas en zsh | Pendiente | — |
| 0 desde cada paso y cambio de perfil | Pendiente | — |
| Ctrl+C en cada pregunta y terminal restaurada | Pendiente | — |
| `connect --detect`, `connect --remove` y `uninstall` | Pendiente | — |
| Tubería y `--non-interactive` | Pendiente | — |
| Windows (PowerShell y Windows Terminal) | Pendiente: lo hace el mantenedor | — |
