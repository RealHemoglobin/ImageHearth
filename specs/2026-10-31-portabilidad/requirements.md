# Fase 2: Portabilidad del núcleo

## Contexto

Tercera fase del [roadmap](../roadmap.md). Su objetivo es eliminar cada bloqueo de las secciones B y C del [análisis](../analysis.md): el servidor debe arrancar y funcionar en Linux y Windows, Ollama pasa a ser opcional y el motor deja de depender de que el nodo de ComfyUI esté instalado y sea correcto.

Estado de partida, comprobado el 2026-10-31:

- El paquete `imagehearth-mcp` ya se instala con `uv tool install ./` (fase 1). La verificación local es `scripts/check.sh`.
- `engine/orchestrator.py` y `engine/log.py` importan `fcntl`; `engine/comfyui_manager.py` recorre `/proc`, usa `SIGKILL`, `venv/bin/python` y `start_new_session=True`.
- Ollama es obligatorio de hecho y su ausencia deja el estado en `degraded`.
- Sin el nodo `imageengine_status`, `free_models` falla, ComfyUI se reinicia y la sesión pasa a `recovery_required`. El nodo devuelve `None` en `comfy_entrypoint` y ComfyUI lo muestra como `IMPORT FAILED`.

## Alcance

- Crear `platform/` con procesos (`psutil`), bloqueos (`filelock`), rutas del venv y arranque desacoplado por sistema.
- Sustituir la rotación compartida de logs por un archivo por proceso con limpieza por antigüedad.
- Declarar `encoding="utf-8"` en toda lectura y escritura de texto.
- Reintentar `os.replace` ante bloqueos transitorios en Windows.
- Abstraer la memoria de GPU: `/system_stats` y después `nvidia-smi`.
- Hacer Ollama opcional (`ollama_mode`: `auto` u `off`) y distinguir "Ollama no está" de "Ollama falló con modelos cargados".
- Diseñar `MemoryProvider` (listar lo cargado, descargar, restaurar) con Ollama como única implementación.
- Corregir el nodo (`ComfyExtension` válido), renombrarlo a `imagehearth_status` y versionar el endpoint.
- Alternativa sin nodo: memoria libre de `/system_stats`, aviso y sin bucle de `recovery_required`.
- Registrar con PID la instancia gestionada de ComfyUI y no reiniciar ni matar nunca una ajena.
- Traducir mensajes a inglés y renombrar `ADVERTENCIA` a `WARNING`, también en la skill y los tests.
- `scripts/check.ps1`, prueba de contrato con `/object_info` y ejecución en Windows.
- Actualizar README, `tech-stack.md` y la instalación local (nodo renombrado en `~/AI/ComfyUI`).

## Fuera de alcance

- Otros proveedores de memoria (llama.cpp, LM Studio, vLLM) y `memory_mode`: fase 5.
- Instalar el nodo en ComfyUI desde el paquete: fase 3. Aquí se copia a mano.
- Soporte y verificación en macOS y perfiles GGUF: fase 4.
- Subcomandos `setup`, `doctor`, `connect`, etc.: fases 3 y 5.
- Pasar la skill a `FastMCP(instructions=...)` y reducir herramientas: fase 5.
- CI de cualquier tipo: no se usa GitHub Actions.

## Decisiones

| Tema | Decisión |
|---|---|
| Alcance de la rama | Una sola rama, `feature/portabilidad`, con todas las tareas ordenadas en el plan |
| Fase 1 | Se da por completada; sus comprobaciones manuales pendientes no bloquean esta fase. El roadmap no se modifica en este paso |
| Orden | Primero lo que desbloquea Windows (`platform/`, logs, UTF-8, `os.replace`, VRAM, PID); después Ollama opcional, `MemoryProvider`, nodo y mensajes |
| Nodo | Se renombra a `imagehearth_status` (carpeta, ruta HTTP, referencias en cliente, estado, tests y README). Devuelve un `ComfyExtension` válido y el endpoint incluye versión |
| Migración del nodo | En esta máquina se sustituye a mano el nodo antiguo de `~/AI/ComfyUI/custom_nodes`; no hay compatibilidad con la ruta `imageengine_*` |
| Ollama | Clave `ollama_mode` en `config.toml` y variable `IMAGEHEARTH_OLLAMA_MODE`, con valores `auto` (por defecto) y `off`. `ollama_url` se conserva |
| Ollama ausente | En `auto`, si no responde, no hay nada que descargar ni restaurar y el estado no pasa a `degraded`. Si falla con modelos cargados, se conserva la protección actual |
| Instancia gestionada | `state/comfyui.pid` con PID y `create_time`, validado con `psutil` para evitar reutilización de PID. Una instancia sin registro propio nunca se reinicia ni se mata |
| Dependencias nuevas | `psutil` y `filelock`, obligatorias |
| Mensajes | Todo en inglés, `ADVERTENCIA` pasa a `WARNING` en código, skill y tests. Sin compatibilidad con el prefijo antiguo |
| Logs | Un archivo por proceso, con limpieza por antigüedad al arrancar |
| Scripts | `scripts/check.ps1` equivalente a `check.sh`, y prueba de contrato manual `scripts/contract.sh` y `scripts/contract.ps1` |
| Puerta de calidad | `scripts/check.sh` en Linux, `check.ps1` en Windows y la prueba de contrato `/object_info` |
| Windows | Su validación manual no bloquea el merge: se documenta el resultado, o su ausencia, en `validation.md` |
| macOS | Se escribe código portable, pero queda sin verificar y no se anuncia como soportado |

## Restricciones

- No se cambian nombres, parámetros ni resultados de las 7 herramientas, salvo el texto de los mensajes.
- El servidor sigue sin depender de PyTorch ni de Ollama para arrancar.
- Nunca se mata ni reinicia una instancia de ComfyUI que no sea la gestionada.
- Los borrados siguen limitados a la subcarpeta de ComfyUI propia del proyecto.
- No hay `git commit` por parte del asistente: el usuario revisa y confirma los cambios.
- Según [tech-stack](../tech-stack.md), la interfaz es en inglés; los documentos de `specs/` siguen en español.

## Entregables

- Paquete `platform/` y el código del motor sin `fcntl`, `/proc`, `SIGKILL` ni rutas del venv fijas.
- Interfaz `MemoryProvider` con la implementación de Ollama y el modo `ollama_mode`.
- Nodo `imagehearth_status` corregido y versionado, y el motor tolerante a su ausencia.
- Registro PID de la instancia gestionada.
- Mensajes, skill y tests en inglés con `WARNING`.
- `scripts/check.ps1`, `scripts/contract.sh` y `scripts/contract.ps1`.
- README, `tech-stack.md` y `THIRD_PARTY_NOTICES.md` actualizados.

## Supuestos abiertos

- El roadmap marca la última tarea de la fase 1 como pendiente; al darla por completada, habrá que marcarla al revisar el roadmap (no se ha tocado aquí).
- El roadmap describe el nodo como "añadir versión al endpoint"; el renombrado a `imagehearth_status` es una decisión nueva de esta fase y el roadmap no la recoge.
