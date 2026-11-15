# Fase 12: Carpeta de instalación

## Contexto

Fase 12 del [roadmap](../roadmap.md). Objetivo: que el usuario decida en qué disco se instalan ComfyUI y los modelos, que ocupan decenas de GB, y que pueda mover una instalación existente a otro sitio con `update`. Depende de las fases 3 y 11; la pregunta de carpeta usa el componente de menú de la [fase 11](../2026-11-15-menus-por-numero/requirements.md).

Estado de partida, comprobado el 2026-11-15:

- El ComfyUI gestionado se instala en `config.COMFY_DIR`, que por defecto es `DATA_DIR / "comfyui"` (`~/.local/share/imagehearth/comfyui` o `%LOCALAPPDATA%\imagehearth\comfyui`). Se puede cambiar con `comfy_dir` en `config.toml` o `IMAGEHEARTH_COMFY_DIR`, pero `setup` no lo pregunta.
- `setup --models-dir` existe: guarda los modelos fuera de ComfyUI y los comparte con `extra_model_paths.yaml` (`comfyui.write_extra_model_paths`).
- El registro de instalación (`install.json`, `InstallManifest`) guarda `mode`, `comfy_dir` y `models_dir`. `models.resolve_dir` usa `models_dir` registrado o `comfy_dir/models`.
- `apply_config` escribe `comfy_dir` en `config.toml` solo en modo adjunto o si difiere del de por defecto.
- `preflight.check_disk(needs)` comprueba espacio libre por carpeta. No hay comprobaciones de permisos, sistema de archivos ni longitud de ruta.
- `update` no tiene argumentos: solo completa los modelos pendientes del perfil instalado.
- `setup_start` (MCP) acepta `profile`, `accept_licenses`, `existing_comfyui` y `quality_model`.
- `config.toml`, `install.json`, los bloqueos (`engine.lock`, `setup.lock`, `setup-job.lock`) y los logs siguen en las rutas del sistema y no se mueven.

## Alcance

Todo lo que pide el roadmap para la fase:

1. **`setup --install-dir PATH`**: ComfyUI gestionado en `PATH/comfyui` y modelos en `PATH/comfyui/models`, salvo `--models-dir`.
2. **Pregunta de carpeta en `setup` interactivo** con el menú de la fase 11, como un paso más con 0 para volver.
3. **Persistencia** en `config.toml` y en `install.json`, usada por `update`, `doctor` y `uninstall`.
4. **Comprobaciones previas** en la carpeta elegida: permisos, espacio, sistema de archivos, unidades de red o extraíbles, rutas en Windows.
5. **MCP**: `setup_status` y `setup_start` con `install_dir` opcional e instrucciones al agente.
6. **`update --move-to PATH`**: traslado del ComfyUI gestionado y de los modelos propios, reanudable.
7. **`doctor`**: carpeta de instalación, disco y espacio libre.
8. **Pruebas y documentación.**

## Fuera de alcance

- Mover `config.toml`, `install.json`, bloqueos, logs o la carpeta de salida de imágenes.
- Elegir carpeta de ComfyUI en modo adjunto: ComfyUI es del usuario. Solo `--models-dir`, como ahora.
- Mover el ComfyUI del usuario (modo adjunto) o modelos preexistentes que ImageHearth no descargó.
- Mover el entorno de Python copiándolo: se recrea.
- Interfaz gráfica para elegir la carpeta (explorador de archivos).
- Dependencias nuevas (`psutil` u otras) para listar unidades.
- macOS probado: queda preparado sin probar.

## Decisiones

| Tema | Decisión |
|---|---|
| Alcance | Todo el roadmap: instalación, pregunta interactiva, MCP, comprobaciones, `update --move-to` y `doctor` |
| Estructura en la carpeta | `PATH/comfyui` para ComfyUI gestionado; modelos en `PATH/comfyui/models` salvo `--models-dir`. `PATH` puede no existir: se crea tras la confirmación final |
| `--install-dir` y `--attach` | Incompatibles: error de argumentos antes de detectar nada |
| `--install-dir` y `--models-dir` | Compatibles: ComfyUI en `PATH/comfyui`, modelos donde diga `--models-dir` |
| `--install-dir` en una instalación existente | Si difiere de la registrada, error que remite a `update --move-to`. `setup` no traslada |
| Pregunta interactiva | Paso `Install folder` tras el modo (solo en gestionado, sin `--install-dir` y sin instalación registrada). Opciones: la de siempre (recomendada), otras unidades detectadas con su espacio libre frente a lo que se va a descargar, y `Type a path`. 0 vuelve atrás. La confirmación final muestra la carpeta |
| Unidades detectadas | Solo biblioteca estándar: `/proc/mounts` en Linux filtrando sistemas virtuales (`proc`, `sysfs`, `tmpfs`, `overlay`, `squashfs`...), `/Volumes` en macOS y letras de unidad con `ctypes` (`GetLogicalDrives`, `GetDriveTypeW`) en Windows. En cada unidad se propone `<montaje>/ImageHearth` (o la carpeta de usuario si el montaje es `/` o `/home`). Unidades sin permiso de escritura no se ofrecen |
| Ruta escrita | Se expande `~`, se resuelve a absoluta y se pasan las mismas comprobaciones; si fallan, se explica y se vuelve a preguntar |
| Persistencia | `comfy_dir` siempre en `config.toml` cuando no es el de por defecto, y `models_dir` si es distinta de `comfy_dir/models`; `install.json` guarda `install_dir`, `comfy_dir` y `models_dir` |
| Comprobaciones previas | Antes de descargar: permisos de escritura (crear y borrar un archivo de prueba), espacio libre, sistema de archivos, unidad de red o extraíble, y en Windows rutas con espacios o no ASCII y longitud |
| FAT32 / exFAT sin archivos grandes | Si el sistema de archivos tiene límite de 4 GB por archivo y algún archivo pendiente lo supera: **rechazar** antes de descargar con un error claro. Si todos caben: aviso |
| Red o extraíble | Solo aviso (rendimiento y desconexión), no bloquea |
| Windows: espacios y no ASCII | Aviso; longitud de ruta: rechazo si la ruta más larga prevista supera 260 caracteres y las rutas largas no están activadas (`LongPathsEnabled`) |
| MCP | `setup_status` devuelve la carpeta por defecto, las unidades detectadas con espacio libre y, si hay instalación, la carpeta actual. `setup_start(install_dir="")` acepta una carpeta; vacía usa la de siempre. Las instrucciones piden al agente que pregunte si el usuario quiere otra carpeta antes de descargar |
| `update --move-to PATH` | Traslada el ComfyUI gestionado y los modelos que instaló ImageHearth a `PATH/comfyui` (y `models_dir` propia a `PATH/models` si estaba fuera). No mueve modelos preexistentes ni nada en modo adjunto (en adjunto, error explicativo) |
| Confirmación del traslado | Muestra qué se mueve, tamaño, espacio libre en destino y comprobaciones; pide confirmación de una tecla o `--yes` en no interactivo |
| Bloqueos durante el traslado | Rechaza si hay una generación (`engine.lock`) o una instalación (`setup.lock`, `setup-job.lock`) en curso; para el ComfyUI gestionado si está en marcha; toma `setup.lock` durante todo el traslado |
| Mismo sistema de archivos | Renombrar (`os.replace`/`Path.rename`) |
| Otro disco | Copiar, verificar y borrar el origen solo al final. **Verificación:** tamaño para todo y SHA-256 del manifiesto para los modelos que lo declaran |
| Reanudación | Un archivo de estado del traslado (`move.json` en `DATA_DIR`) con origen, destino y archivos ya verificados. Mientras no termina, `install.json` y `config.toml` apuntan al origen, que sigue funcionando. Repetir el mismo comando continúa; otro destino con un traslado a medias da error que pide terminarlo o cancelarlo (`update --move-to` con el origen lo cancela y limpia el destino parcial) |
| Entorno de Python | No se copia: se recrea en el destino con uv como en `setup`, y se borra el del origen al final |
| Rutas tras el traslado | Se actualizan `config.toml`, `install.json`, `extra_model_paths.yaml` y el nodo de estado. Las conexiones de agentes no cambian (apuntan al ejecutable). El servidor MCP lee la configuración al arrancar: el mensaje final pide reiniciar las sesiones de los agentes |
| `doctor` | Muestra carpeta de instalación, carpeta de modelos, sistema de archivos y espacio libre; en `--json` dentro de `details`. Avisa si hay un traslado a medias |
| `uninstall` | Usa las rutas registradas; borra la carpeta de instalación solo si la creó ImageHearth y quedó vacía |
| Idioma | Interfaz en inglés, como el resto de la CLI |

## Restricciones

- El modo no interactivo y los argumentos actuales siguen funcionando igual; sin `--install-dir` el resultado es idéntico a hoy.
- Antes de la confirmación final, `setup` no escribe nada en disco (tampoco crea la carpeta elegida).
- Un traslado interrumpido (Ctrl+C, corte, error) deja la instalación funcionando en el origen.
- Nunca se borra nada fuera de lo que ImageHearth registró como propio.
- Funciona en Linux y Windows; macOS preparado sin probar.
- Solo biblioteca estándar más las dependencias actuales.
- Los tests simulados no tocan el `HOME` real ni discos reales fuera de carpetas temporales.
- Sin commits del asistente.

## Entregables

- `cli.py`: `setup --install-dir` y `update --move-to`, `--yes`.
- Módulo de carpetas y unidades (`provisioner/locations.py`): detección de unidades, comprobaciones previas y propuesta de carpeta.
- `setup.py`: paso de carpeta, comprobaciones y persistencia.
- `maintenance.py` (o `provisioner/move.py`): traslado reanudable.
- `install_manifest.py`, `doctor.py`, `agent_setup.py` y `server.py` actualizados.
- Tests en `tests/test_locations.py`, `tests/test_move.py` y ampliaciones de `tests/test_provisioner.py` (incluido `doctor`) y `tests/test_agent_setup.py`.
- `README.md`, `README.es.md`, `docs/troubleshooting.md` y `llms-install.md` actualizados.
- Evidencia en [validation.md](validation.md).
