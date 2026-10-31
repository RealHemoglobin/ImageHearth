# Plan: Fase 2

Rama: `feature/portabilidad`. Sin commits del asistente: los cambios se dejan en el árbol de trabajo para revisión.

**Aviso:** el servidor MCP instalado (`uv tool`) no se actualiza hasta el paso 11. Hasta entonces las pruebas reales se hacen con `uv run` desde el repositorio.

## 1. Dependencias y paquete `platform/`

1. Añadir `psutil` y `filelock` a `pyproject.toml` y regenerar `uv.lock`.
2. Crear `src/imagehearth_mcp/platform/` con:
   - procesos: listar, buscar por ruta de ejecución, comprobar y terminar con `psutil` (sin `/proc` ni `SIGKILL`);
   - bloqueos: envoltorio de `filelock` que libera el bloqueo si muere el proceso;
   - rutas: ejecutable de Python del venv (`bin/python` o `Scripts\python.exe`);
   - arranque desacoplado: `start_new_session` en POSIX, `creationflags` en Windows.
3. Tests unitarios de cada módulo, con simulación de Windows donde no se pueda ejecutar.

## 2. Bloqueos, procesos y arranque en el motor

1. Sustituir `fcntl` en `orchestrator.py` por el bloqueo de `platform/`.
2. Sustituir en `comfyui_manager.py` el recorrido de `/proc`, `os.kill` y `venv/bin/python` por `platform/`.
3. Usar el arranque desacoplado por sistema al lanzar ComfyUI.

## 3. Logs

1. Reescribir `log.py`: un archivo por proceso (con PID en el nombre) y limpieza por antigüedad al arrancar. Sin `fcntl`, inodos ni renombrado de archivos abiertos.
2. Test de dos procesos escribiendo a la vez sin pérdida ni errores.

## 4. UTF-8 y `os.replace`

1. Declarar `encoding="utf-8"` en toda lectura y escritura de texto de `src/` (`git grep` de `read_text`, `write_text` y `open`).
2. Añadir una regla de `ruff` para impedir `open` sin `encoding`, si existe una equivalente.
3. Función de reintento para `os.replace` ante `PermissionError` transitorio, usada en estado y escrituras atómicas. Test con fallos simulados.

## 5. Memoria de GPU

1. Interfaz de lectura de memoria libre y total: `/system_stats` de ComfyUI primero, `nvidia-smi` como apoyo y, si ninguno responde, resultado desconocido (no un fallo).
2. Sustituir las llamadas actuales a `nvidia-smi` en `comfyui_manager.py`. Tests con respuestas simuladas.

## 6. Instancia gestionada de ComfyUI

1. Escribir `state/comfyui.pid` con PID y `create_time` al arrancar; validarlo con `psutil` antes de usarlo.
2. `restart()` y la parada solo actúan sobre la instancia registrada. Una instancia ajena en el puerto produce un aviso claro y no se toca.
3. Limpiar el registro si el proceso ya no existe. Tests con PID reutilizado simulado.

## 7. Ollama opcional y `MemoryProvider`

1. Añadir `ollama_mode` (`auto`/`off`) a `config.py`: `config.toml`, `IMAGEHEARTH_OLLAMA_MODE`, error claro ante valores no válidos.
2. Definir `MemoryProvider` (listar lo cargado, descargar, restaurar) y mover `ollama_manager.py` a una implementación suya.
3. Orquestador y estado: en `off`, o en `auto` sin respuesta de Ollama, no se descarga ni se restaura y el estado no es `degraded`.
4. Distinguir "no está" de "falló con modelos cargados"; en el segundo caso se conserva la protección actual.
5. Tests: sin Ollama, con Ollama que cae a mitad de sesión y con modelos cargados.

## 8. Nodo `imagehearth_status`

1. Renombrar la carpeta `data/comfyui_node/` y su contenido a `imagehearth_status`, y la ruta HTTP.
2. Devolver un `ComfyExtension` válido desde `comfy_entrypoint` (o registrar la ruta por otro mecanismo) y añadir `version` a la respuesta.
3. En `comfyui_client.py`, `status.py` y `free_models`: usar el nombre nuevo y comprobar la versión.
4. Si falta el nodo, usar la memoria libre de `/system_stats`, avisar una vez y no entrar en `recovery_required`. Ajustar `_reconcile`.
5. Tests de ambos caminos y actualización de `tests/harness.py`.

## 9. Mensajes en inglés

1. Traducir todos los mensajes de `engine/` y `server.py`, y renombrar `ADVERTENCIA` a `WARNING` en `result.py`.
2. Actualizar la skill (`SKILL.md`) y los tests que comparan texto.
3. `git grep -in "advertencia"` y cadenas en español en `src/` y `tests/`: solo debe quedar lo justificado.

## 10. Scripts de verificación

1. `scripts/check.ps1`: mismos pasos que `check.sh` (sincronizar, `ruff`, `pytest`, wheel en entorno aparte) con rutas de Windows.
2. `scripts/contract.sh` y `scripts/contract.ps1`: arrancar ComfyUI en CPU y comprobar con `/object_info` que existen todos los nodos usados por los workflows, sin descargar modelos.
3. Ejecutar `check.sh` y la prueba de contrato en Linux.

## 11. Migración local y documentación

1. Reinstalar el paquete con `uv tool install --reinstall ./` y sustituir el nodo antiguo de `~/AI/ComfyUI/custom_nodes` por `imagehearth_status`.
2. Actualizar ambos README (nodo, `ollama_mode`, requisitos de Windows), `tech-stack.md` (módulo `platform`, nodo renombrado) y `THIRD_PARTY_NOTICES.md` si cita la ruta del nodo.
3. Marcar las tareas de la fase 2 en el roadmap cuando estén verificadas (el usuario revisa antes).

## 12. Validación

1. Ejecutar la matriz de [validation.md](validation.md): automática en Linux, manual con RTX 4090 sin Ollama y con Ollama, y manual en Windows cuando haya acceso.
2. Rellenar la tabla de evidencia, incluidas las comprobaciones de Windows y macOS que no se hayan hecho.
