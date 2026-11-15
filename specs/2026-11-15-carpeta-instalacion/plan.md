# Plan: Fase 12

Rama: `feature/carpeta-instalacion`. Sin commits del asistente: los cambios se dejan en el árbol de trabajo para revisión. Los pasos marcados como **mantenedor** no los ejecuta el asistente.

Orden: primero el módulo de carpetas y comprobaciones, que no depende de nada. Después la instalación en otra carpeta (CLI, paso interactivo, persistencia y MCP). Por último el traslado, que es la parte con más riesgo y reutiliza las comprobaciones.

## 1. Carpetas y comprobaciones (`provisioner/locations.py`)

1. `default_install_dir()`: el padre de `DATA_DIR / "comfyui"` (resultado idéntico a hoy).
2. `list_drives()`: unidades con punto de montaje, sistema de archivos, espacio libre, si es de red o extraíble. Linux con `/proc/mounts` (filtrando sistemas virtuales y montajes sin escritura), macOS con `/Volumes`, Windows con `ctypes` (`GetLogicalDrives`, `GetDriveTypeW`, `GetVolumeInformationW`). Funciones de lectura inyectables para los tests.
3. `propose(drive)`: `<montaje>/ImageHearth`, o la de por defecto si el montaje es el del `HOME`.
4. `check(path, pending_files)`: devuelve errores y avisos. Permisos (crear y borrar un archivo de prueba en el primer ancestro existente), espacio (reutiliza `preflight.check_disk`), FAT32/exFAT con archivos de más de 4 GB (error) o sin ellos (aviso), red o extraíble (aviso), Windows: espacios o no ASCII (aviso) y longitud con `LongPathsEnabled` (error).
5. Tests en `tests/test_locations.py` con `/proc/mounts` y respuestas de Windows simuladas.

## 2. Instalación en otra carpeta

1. `cli.py`: `setup --install-dir PATH`; error si se combina con `--attach`.
2. `setup.py`: resolver `comfy_dir = PATH/comfyui` y `models_dir` (`--models-dir` o `comfy_dir/models`). Con instalación registrada y otra carpeta, error que remite a `update --move-to`.
3. Paso interactivo `Install folder` tras el modo, solo en gestionado sin `--install-dir` ni instalación registrada: `menu.choose` con la de siempre, unidades detectadas (espacio libre frente a descarga) y `Type a path`; 0 vuelve; el indicador `Step N of M` lo incluye.
4. Ejecutar `locations.check` antes de la confirmación final (y en no interactivo antes de descargar); los errores impiden continuar, los avisos se muestran en el resumen.
5. Persistencia tras la confirmación: `apply_config` escribe `comfy_dir` cuando no es el de por defecto y `models_dir` cuando difiere; `InstallManifest` añade `install_dir`.
6. `update`, `doctor` y `uninstall` usan las rutas registradas; `uninstall` borra la carpeta de instalación si es propia y queda vacía.
7. Tests en `tests/test_provisioner.py`: `--install-dir` en no interactivo, combinado con `--models-dir`, rechazo con `--attach`, rechazo por espacio, permisos y FAT32, paso interactivo (unidad detectada, ruta escrita, 0), nada escrito antes de confirmar, y `uninstall` en otra carpeta.

## 3. MCP

1. `agent_setup.status`: carpeta por defecto, unidades detectadas con espacio libre y carpeta actual si hay instalación.
2. `agent_setup.start` y `server.setup_start` con `install_dir: str = ""`; mismas comprobaciones, con los errores devueltos al agente.
3. Docstrings de `setup_status`/`setup_start` e instrucciones del servidor: preguntar al usuario si quiere otra carpeta antes de descargar.
4. Tests de `agent_setup` con `install_dir` válido, inválido y vacío.

## 4. Traslado (`update --move-to`)

1. `cli.py`: `update --move-to PATH` y `--yes`.
2. Plan del traslado: qué se mueve (ComfyUI gestionado sin `venv`, modelos propios según `install.json`), tamaño, destino, comprobaciones de `locations.check`. Rechazo en modo adjunto y si el destino es el actual.
3. Confirmación de una tecla (`menu.confirm`) o `--yes`; en no interactivo sin `--yes`, error.
4. Bloqueos: rechazar con `engine.lock` o instalación en curso, tomar `setup.lock` y parar el ComfyUI gestionado (`_stop_managed`).
5. Mismo sistema de archivos (mismo `st_dev`): renombrar.
6. Otro disco: copiar archivo a archivo a un temporal y renombrar, verificar tamaño y SHA-256 del manifiesto, apuntar lo verificado en `move.json`. Recrear el `venv` con uv en el destino.
7. Cambio de rutas al final, en orden: `extra_model_paths.yaml`, nodo de estado, `install.json`, `config.toml`; después borrar el origen y `move.json`.
8. Reanudación y cancelación: mismo destino continúa; otro destino con `move.json` da error; `--move-to` con el origen cancela y limpia el destino parcial.
9. Mensaje final: reiniciar las sesiones de los agentes.
10. Tests en `tests/test_move.py`: mismo disco (renombrar simulado), otro disco (`st_dev` distinto simulado), SHA-256 que no coincide, interrupción en mitad y repetición, cancelación, falta de espacio o permisos, adjunto, generación en curso, `uninstall` tras un traslado.

## 5. `doctor`

1. Mostrar carpeta de instalación, carpeta de modelos, sistema de archivos y espacio libre; en `--json` dentro de `details`.
2. Aviso si existe `move.json` (traslado a medias) con el comando para continuar.
3. Tests en `tests/test_provisioner.py`, junto a los de `doctor` existentes.

## 6. Documentación

1. `README.md` y `README.es.md`: `--install-dir`, pregunta de carpeta y `update --move-to`.
2. `docs/troubleshooting.md`: FAT32, falta de espacio o permisos, rutas largas en Windows, traslado interrumpido.
3. `llms-install.md`: preguntar la carpeta antes de `setup_start`.
4. Marcar en el roadmap las tareas hechas.

## 7. Pruebas reales

1. Linux, por el asistente, con `HOME` temporal y un segundo disco o partición montada: `setup --profile fast --install-dir <segundo disco>`, generar, `update --move-to` al disco del sistema (y vuelta), volver a generar, interrumpir un traslado con Ctrl+C y repetirlo, y `uninstall`.
2. **Mantenedor:** lo mismo en Windows con otra letra de unidad.

## 8. Validación local y cierre

1. Ejecutar `scripts/check.sh`.
2. Rellenar la evidencia en [validation.md](validation.md).
3. **Mantenedor:** revisar, hacer commit y fusionar en `main`.
4. Marcar la fase como completada en el roadmap cuando la lista de cierre esté completa.
