# Validación: Fase 12

Una sola puerta: la rama no se fusiona hasta que estén en verde los tests simulados, `scripts/check.sh` y la prueba real en Linux, y el mantenedor haya hecho la de Windows.

## Criterios de finalización

- `setup` permite instalar en otro disco, de forma interactiva y con `--install-dir`, y falla antes de descargar si no hay espacio, permisos o el sistema de archivos no admite los archivos.
- Sin `--install-dir` ni elección distinta, la instalación queda exactamente donde hoy.
- La carpeta elegida queda en `config.toml` e `install.json`, y `update`, `doctor` y `uninstall` la usan.
- `setup_status` informa de las carpetas posibles y `setup_start` acepta `install_dir`.
- `update --move-to` traslada una instalación existente, que sigue generando después.
- Un traslado interrumpido deja la instalación funcionando en el origen, y repetir el comando lo termina.
- `doctor` muestra carpeta, disco y espacio libre, y avisa de un traslado a medias.
- `uninstall` limpia la carpeta elegida sin tocar nada ajeno.

## Validaciones automáticas

Desde la raíz del repositorio, en Linux:

```bash
scripts/check.sh
```

Ejecuta `uv sync --locked`, `ruff`, `pytest` y los tests contra el wheel instalado en un entorno aparte. Es la puerta de calidad obligatoria de [tech-stack](../tech-stack.md); esta fase no toca workflows, así que la prueba de contrato no es obligatoria.

Los tests deben cubrir:

- [ ] Detección de unidades en Linux (`/proc/mounts` simulado, sistemas virtuales filtrados) y Windows (respuestas de `ctypes` simuladas).
- [ ] Comprobaciones: sin permisos, sin espacio, FAT32 con archivo de más de 4 GB (error), FAT32 sin archivos grandes (aviso), red o extraíble (aviso), Windows con ruta larga sin `LongPathsEnabled` (error).
- [ ] `setup --install-dir` no interactivo: rutas de ComfyUI y modelos, `config.toml` e `install.json`.
- [ ] `--install-dir` con `--models-dir`; rechazo con `--attach`; rechazo con otra carpeta sobre una instalación registrada.
- [ ] Paso interactivo: la de siempre, unidad detectada, ruta escrita válida e inválida, 0 vuelve, `Step N of M` correcto.
- [ ] Nada se escribe ni se crea antes de la confirmación final.
- [ ] `setup_status` con unidades y carpeta actual; `setup_start` con `install_dir` válido, inválido y vacío.
- [ ] `update --move-to` en el mismo disco (renombrar) y en otro disco (copiar y verificar).
- [ ] SHA-256 que no coincide: el traslado se detiene y el origen sigue intacto.
- [ ] Traslado interrumpido y repetido; cancelación volviendo al origen; destino distinto con traslado a medias rechazado.
- [ ] Rechazo en modo adjunto, con generación o instalación en curso, y sin `--yes` en no interactivo.
- [ ] `extra_model_paths.yaml`, nodo de estado, `install.json` y `config.toml` actualizados tras el traslado.
- [ ] `doctor` con carpeta, disco, espacio y traslado a medias, también en `--json`.
- [ ] `uninstall` tras instalar en otra carpeta y tras un traslado.
- [ ] Tests existentes sin cambios de comportamiento; ningún test toca el `HOME` real.

## Validaciones manuales

En Linux, por el asistente, con `HOME` temporal y un segundo disco o partición montada:

- [ ] `setup --profile fast --install-dir <segundo disco>` y `create_image`.
- [ ] `setup` interactivo: la pregunta muestra las unidades con su espacio libre.
- [ ] `update --move-to` a otro disco, con la confirmación mostrando tamaño y espacio, y `create_image` después.
- [ ] Ctrl+C a mitad de un traslado entre discos: el origen sigue generando; repetir el comando lo termina.
- [ ] `doctor` antes y después del traslado.
- [ ] `uninstall`: no queda nada en ninguna de las dos carpetas.

En Windows:

- [ ] **Mantenedor:** instalar `fast` en otra letra de unidad, generar, `update --move-to`, volver a generar y `uninstall`, en PowerShell.

## Lista para fusionar

- [ ] `scripts/check.sh` en verde en Linux.
- [ ] Validaciones manuales en Linux completadas.
- [ ] **Mantenedor:** validación en Windows.
- [ ] `README.md`, `README.es.md`, `docs/troubleshooting.md` y `llms-install.md` actualizados.
- [ ] Roadmap con las tareas hechas marcadas y la fase como completada.
- [ ] Cambios revisados por el usuario, que realiza el commit.

## Evidencia

| Comprobación | Resultado | Fecha |
|---|---|---|
| `scripts/check.sh` | | |
| `setup --install-dir` en segundo disco y generación | | |
| Pregunta interactiva con unidades | | |
| `update --move-to` entre discos y generación | | |
| Traslado interrumpido y repetido | | |
| `doctor` antes y después | | |
| `uninstall` tras traslado | | |
| Windows (otra letra de unidad) | Pendiente: lo hace el mantenedor | — |
