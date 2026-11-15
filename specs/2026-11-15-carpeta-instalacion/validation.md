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

- [x] Detección de unidades en Linux (`/proc/mounts` simulado, sistemas virtuales filtrados) y Windows (respuestas de `ctypes` simuladas).
- [x] Comprobaciones: sin permisos, sin espacio, FAT32 con archivo de más de 4 GB (error), FAT32 sin archivos grandes (aviso), red o extraíble (aviso), Windows con ruta larga sin `LongPathsEnabled` (error).
- [x] `setup --install-dir` no interactivo: rutas de ComfyUI y modelos, `config.toml` e `install.json`.
- [x] `--install-dir` con `--models-dir`; rechazo con `--attach`; rechazo con otra carpeta sobre una instalación registrada.
- [x] Paso interactivo: la de siempre, unidad detectada, ruta escrita válida e inválida, 0 vuelve, `Step N of M` correcto.
- [x] Nada se escribe ni se crea antes de la confirmación final.
- [x] `setup_status` con unidades y carpeta actual; `setup_start` con `install_dir` válido, inválido y vacío.
- [x] `update --move-to` en el mismo disco (renombrar) y en otro disco (copiar y verificar).
- [x] SHA-256 que no coincide: el traslado se detiene y el origen sigue intacto.
- [x] Traslado interrumpido y repetido; cancelación volviendo al origen; destino distinto con traslado a medias rechazado.
- [x] Rechazo en modo adjunto, con generación o instalación en curso, y sin `--yes` en no interactivo.
- [x] `extra_model_paths.yaml`, nodo de estado, `install.json` y `config.toml` actualizados tras el traslado.
- [x] `doctor` con carpeta, disco, espacio y traslado a medias, también en `--json`.
- [x] `uninstall` tras instalar en otra carpeta y tras un traslado.
- [x] Tests existentes sin cambios de comportamiento; ningún test toca el `HOME` real. Único ajuste: las secuencias de teclas de `test_setup_steps.py` y `test_quality_model.py` llevan una tecla más, porque `setup` interactivo ahora tiene el paso `Install folder` (y los números `Step N of M` suben en uno). Los tests de `setup` usan `list_drives` simulado.

## Validaciones manuales

En Linux, por el asistente, con `HOME` temporal y un segundo disco o partición montada:

- [x] `setup --profile fast --install-dir <segundo disco>` y generación (la imagen de prueba de `setup`, que pasa por el motor; no se llamó a la herramienta MCP `create_image`).
- [x] `setup` interactivo: la pregunta muestra las unidades con su espacio libre (en un pty real, con las unidades reales del equipo).
- [x] `update --move-to` a otro disco (de `/mnt/LinuxExtra` a `/mnt/linux-parts/ssd237`, y de vuelta), con la confirmación mostrando tamaño y espacio, y generación después.
- [x] Ctrl+C durante un traslado entre discos: el origen sigue generando; repetir el comando lo termina. La interrupción real cayó durante la creación del entorno de Python (con los 1330 archivos ya copiados y verificados): una interrupción a mitad de la copia solo está cubierta por el test simulado.
- [x] `doctor` antes y después del traslado, y con el traslado a medias (avisa con los dos comandos).
- [x] `uninstall`: no queda nada en ninguna de las dos carpetas. En la prueba real quedaron los `models/configs/*.yaml` que trae ComfyUI; se corrigió después (`_prune_models_dir` los trata como de ComfyUI) y solo lo cubren tests simulados, sin repetir la prueba real.

En Windows:

- [ ] **Mantenedor:** instalar `fast` en otra letra de unidad, generar, `update --move-to`, volver a generar y `uninstall`, en PowerShell.

## Lista para fusionar

- [x] `scripts/check.sh` en verde en Linux.
- [ ] Validaciones manuales en Linux completadas.
- [ ] **Mantenedor:** validación en Windows.
- [x] `README.md`, `README.es.md`, `docs/troubleshooting.md` y `llms-install.md` actualizados.
- [ ] Roadmap con las tareas hechas marcadas y la fase como completada.
- [ ] Cambios revisados por el usuario, que realiza el commit.

## Evidencia

| Comprobación | Resultado | Fecha |
|---|---|---|
| `scripts/check.sh` | 709 tests, ruff y tests contra el wheel en verde (EXIT 0) | 2026-11-15 |
| `setup --install-dir` en segundo disco y generación | `/mnt/LinuxExtra` (ext4), HOME temporal, puerto 8199: instalado, imagen de prueba generada, `config.toml` e `install.json` con la carpeta | 2026-11-15 |
| Pregunta interactiva con unidades | Pty real: la de siempre (recomendada), 7 unidades ordenadas por espacio libre con su etiqueta de red, `Type a path` y 0 | 2026-11-15 |
| `update --move-to` entre discos y generación | LinuxExtra → ssd237 y vuelta: 7,0 GB en 1330 archivos copiados y verificados, entorno recreado, origen borrado, imagen generada después | 2026-11-15 |
| Traslado interrumpido y repetido | SIGINT durante la creación del entorno: el origen generó una imagen, `doctor` avisó, repetir el comando terminó. Interrupción a mitad de copia: solo simulada | 2026-11-15 |
| `doctor` antes y después | Carpeta, modelos, sistema de archivos y espacio libre; aviso con el traslado a medias | 2026-11-15 |
| `uninstall` tras traslado | Borra lo de ImageHearth y restaura `config.toml`; quedan `models/configs/*.yaml` de ComfyUI (comportamiento previo) | 2026-11-15 |
| Windows (otra letra de unidad) | Pendiente: lo hace el mantenedor | — |
