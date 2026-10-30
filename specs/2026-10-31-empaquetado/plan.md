# Plan: Fase 1

Rama: `feature/empaquetado`.

**Aviso:** al mover `mcp/server.py` y `skill/`, la configuración actual de los agentes deja de funcionar mientras esta rama esté activa en el repositorio. Hasta el paso 9, el servidor MCP instalado no se reinicia, o se vuelve a `main` para usarlo.

## 1. Estructura del paquete

1. Mover con `git mv`: `engine/` a `src/imagehearth_mcp/engine/` y `mcp/server.py` a `src/imagehearth_mcp/server.py`.
2. Mover con `git mv` a `src/imagehearth_mcp/data/`: `workflows/`, `skill/` y `extras/comfyui_custom_nodes/imageengine_status/`, este último como `comfyui_node/`.
3. Cambiar las importaciones `engine.*` a `imagehearth_mcp.engine.*`.
4. Eliminar los `sys.path.insert` y los `__main__` de `server.py`, `orchestrator.py`, `comfyui_manager.py`, `ollama_manager.py` y `kontext.py`, junto con el código que solo usaban ellos.
5. Actualizar las rutas de `per-file-ignores` en `pyproject.toml`.

## 2. Empaquetado y CLI

1. En `pyproject.toml`: nombre `imagehearth-mcp`, versión `0.1.0.dev0`, `build-system` con `hatchling`, sin `package = false`, sin `pythonpath = ["."]`, y `platformdirs` como dependencia.
2. Añadir `[project.scripts] imagehearth-mcp = "imagehearth_mcp.cli:main"`.
3. Declarar la expresión de licencia y `license-files` con ambas licencias.
4. Crear `cli.py`: sin argumentos arranca el servidor por stdio y `--version` muestra la versión.
5. Eliminar `requirements.txt` y regenerar `uv.lock`.
6. Comprobar con `uv build --wheel` que el wheel contiene workflows, skill, nodo y licencias, y que no contiene tests ni `specs/`.

## 3. Configuración

1. Reescribir la parte de rutas de `engine/config.py` con `platformdirs` y `tomllib`, con la prioridad y las claves de `requirements.md`.
2. Mantener las constantes de módulo que usa el código, para no cambiar sus llamadores ni el arnés de tests.
3. Renombrar las variables a `IMAGEHEARTH_*`, los logs y `COMFY_SUBFOLDER`.
4. Crear las carpetas al escribir, nunca al importar. Revisar cada escritura de logs, estado, bloqueo y salida.
5. Sustituir el puerto fijo de `server.py` por la configuración.
6. Dar errores claros para un TOML no válido, un puerto no numérico y una carpeta de ComfyUI inexistente.

## 4. Datos de paquete

1. Leer los workflows con `importlib.resources` en `config.py`, `workflow_runner.py`, `kontext.py` y `validation.py`.
2. Dejar en un solo punto el acceso a `data/`, con rutas reales para los consumidores que las necesiten.

## 5. Renombrado de cara al usuario

1. Cambiar el nombre de `FastMCP` a `imagehearth`.
2. Renombrar la skill en su cabecera y actualizar nombres de herramientas y referencias.
3. Quitar la ruta personal de `SKILL.md:231`.
4. Comprobar con `git grep -i imageengine` que solo queda lo permitido: el nodo, su ruta, los identificadores internos de Kontext, documentos históricos en `specs/` y el nombre local de la carpeta.

## 6. Tests

1. Adaptar `tests/harness.py` y `tests/test_requests.py` a las nuevas importaciones y rutas.
2. Cambiar el test que lanza `mcp/server.py` para que use el comando `imagehearth-mcp` por stdio y compruebe las 7 herramientas.
3. Añadir tests de `config.py`: prioridad entre variable, TOML y defecto; errores; e importación sin escrituras en un HOME temporal.
4. Añadir tests de datos de paquete: los tres workflows, la skill y el nodo se resuelven desde el paquete.

## 7. CI

1. Mantener el trabajo actual: `uv sync --locked`, `ruff` y `pytest`.
2. Añadir un trabajo que construya el wheel, lo instale en un entorno aparte con `pytest`, y ejecute `tests/` sin `src/` en el camino de importación. Debe comprobar que `imagehearth_mcp.__file__` está en `site-packages`.

## 8. Documentación

1. Actualizar ambos README: instalación desde el repositorio con `uv tool install ./`, nuevo comando, `config.toml`, variables, rutas, conexión de agentes y copia del nodo desde su nueva ruta. El nombre público pasa a ser ImageHearth.
2. Actualizar la ruta del nodo en `THIRD_PARTY_NOTICES.md`.
3. Actualizar `specs/tech-stack.md`: nombres, rutas y árbol de arquitectura.

## 9. Migración local

Requiere confirmación del usuario antes de empezar.

1. Comprobar que no hay ninguna sesión activa (`state/session.json`) y cerrar los servidores antiguos.
2. Copiar con `cp -p`, con marca de fecha, `~/.claude.json` y `~/.codex/config.toml`, y anotar el destino del enlace de la skill.
3. Instalar con `uv tool install ./` y crear `config.toml` con `comfy_dir = "~/AI/ComfyUI"`. `config.py` expande `~`, o se escribe la ruta absoluta.
4. Sustituir la entrada `imageengine` de Claude Code y de Codex por `imagehearth`, con la ruta absoluta del ejecutable instalado.
5. Sustituir `~/.claude/skills/imageengine` por el enlace `imagehearth` hacia la skill instalada, resolviendo la ruta con `importlib.resources`.
6. Revisar los permisos de los agentes que mencionen `mcp__imageengine__` y cambiarlos a `mcp__imagehearth__`.
7. Reiniciar los agentes y generar una imagen real.

**Reversión:** restaurar las copias y el enlace, `uv tool uninstall imagehearth-mcp` y volver a `main`, donde `mcp/server.py` sigue existiendo.

## 10. Cierre

1. Ejecutar la prueba manual con un usuario temporal de Linux descrita en `validation.md` y eliminar ese usuario después.
2. Marcar las tareas de la fase 1 en `specs/roadmap.md`.
3. Completar la evidencia en `validation.md`.
4. Con confirmación del usuario, abrir el PR, fusionar y comprobar el CI en verde en `main`.

## Dependencias

- Los pasos 2 a 6 dependen del paso 1 y se validan juntos: el paquete no funciona hasta completarlos.
- El paso 7 depende del paso 6, y el paso 8 de los pasos 2 a 5.
- El paso 9 depende de que los pasos 1 a 7 estén en verde en local.
- El paso 10 depende de todos los anteriores.
