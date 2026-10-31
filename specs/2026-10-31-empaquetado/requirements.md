# Fase 1: Empaquetado

## Contexto

Segunda fase del [roadmap](../roadmap.md). Su objetivo es convertir el repositorio en un paquete instalable, sin cambiar el comportamiento del motor. Resuelve la sección A del [análisis](../analysis.md).

Estado de partida, comprobado el 2026-10-31:

- `main` (`571047e`) tiene el CI en verde en `RealHemoglobin/ImageHearth`.
- `pyproject.toml` usa `[tool.uv] package = false` y el código vive en `engine/` y `mcp/`.
- `engine/config.py` guarda datos, logs, estado y salida junto al código, y fija la ruta de ComfyUI y el puerto.
- `mcp/server.py`, `engine/orchestrator.py` y `engine/comfyui_manager.py` usan `sys.path.insert`. Esos dos últimos, `engine/ollama_manager.py` y `engine/kontext.py` tienen `__main__`.
- Claude Code y Codex lanzan `mcp/server.py` con el Python del venv de ComfyUI, y `~/.claude/skills/imageengine` es un enlace a `skill/` en el repositorio.

## Alcance

- Mover el código a `src/imagehearth_mcp/` y eliminar `mcp/`, `engine/`, `workflows/`, `skill/` y `extras/` de la raíz.
- Ampliar `pyproject.toml` con `hatchling` y el comando `imagehearth-mcp`, y retirar `requirements.txt`.
- Incluir workflows, skill y nodo como datos de paquete, leídos con `importlib.resources`.
- Reescribir `config.py` con `platformdirs`, `config.toml` y variables de entorno.
- Sustituir `sys.path.insert` y los `__main__` por la CLI.
- Renombrar a ImageHearth lo indicado en [Decisiones](#decisiones).
- Actualizar los tests, el CI, ambos README y `tech-stack.md`.
- Migrar la instalación local de esta máquina.

## Fuera de alcance

- Portabilidad a Windows y macOS: `fcntl`, `/proc`, rutas del venv y CI en otros sistemas son de la fase 2.
- Hacer Ollama opcional o tolerar la falta del nodo: fase 2.
- Corregir `IMPORT FAILED` en el nodo o renombrarlo: fase 2.
- Traducir mensajes o renombrar `ADVERTENCIA`: fase 2.
- Subcomandos `setup`, `doctor`, `connect`, `models`, `update` y `uninstall`: fases 3 y 5.
- Instalar el nodo en ComfyUI desde el paquete: fase 3.
- Pasar la skill a `FastMCP(instructions=...)`: fase 5.
- Publicar en PyPI: fase 6.

## Decisiones

| Tema | Decisión |
|---|---|
| Distribución | Paquete `imagehearth-mcp`, módulo `imagehearth_mcp` y comando `imagehearth-mcp` |
| Estructura | `src/imagehearth_mcp/` con `server.py`, `cli.py`, `engine/` y `data/` (`workflows/`, `skill/`, `comfyui_node/`) |
| CLI | `imagehearth-mcp` sin argumentos arranca el servidor por stdio, y `--version` muestra la versión. No hay más subcomandos |
| `__main__` de `engine/` | Se eliminan, sin sustituto. La CLI solo sustituye el arranque del servidor |
| Se renombra a ImageHearth | Paquete, comando, variables `IMAGEHEARTH_*`, carpetas de datos, nombre del servidor MCP (`imagehearth`, también en `FastMCP`), skill, logs y subcarpeta de ComfyUI |
| No se renombra | El nodo `imageengine_status` y su ruta HTTP, que corrige la fase 2. Tampoco los identificadores internos `IMAGEENGINE_*` de `engine/kontext.py`, que no ve el usuario |
| Compatibilidad con `IMAGEENGINE_*` | Ninguna: solo hay una instalación y se migra aquí |
| Prioridad de configuración | Variable de entorno, después `config.toml`, después valor por defecto |
| Claves de `config.toml` | `comfy_dir`, `comfy_port`, `output_dir` y `ollama_url` |
| Variables nuevas | `IMAGEHEARTH_COMFY_DIR`, `IMAGEHEARTH_COMFY_PORT`, `IMAGEHEARTH_OUTPUT_DIR` e `IMAGEHEARTH_OLLAMA_URL`. Los plazos y `MAX_PIXELS` conservan su sufijo actual |
| Ruta de ComfyUI por defecto | `comfyui/` dentro de la carpeta de datos de `platformdirs`. Si no existe, el error indica la ruta buscada y cómo configurarla. Esta máquina fija `~/AI/ComfyUI` en `config.toml` |
| Rutas | Las de `tech-stack.md` con `imagehearth` en lugar de `imageengine`. En Linux, los logs quedan en `~/.local/state/imagehearth/log/`, el valor de `platformdirs`, y se actualiza la tabla |
| Datos existentes | No se mueven ni se borran `output/`, `logs/` ni `state/` del repositorio, ni la subcarpeta `imageengine` de ComfyUI |
| Migración local | La hace Claude como último paso, con copia de seguridad y previa confirmación del usuario |
| Validación limpia | CI contra el wheel instalado y prueba manual con un usuario temporal de Linux |

## Restricciones

- Las 7 herramientas conservan nombres, parámetros y resultados. Solo cambia su prefijo en los agentes, de `mcp__imageengine__` a `mcp__imagehearth__`.
- Importar el paquete no crea carpetas ni archivos. Se crean al escribir en ellos.
- Nada se escribe dentro del paquete instalado.
- Un `config.toml` no válido o un puerto no numérico dan un error que indica el archivo o la variable.
- La skill empaquetada no contiene rutas personales: se corrige `skill/SKILL.md:231`.
- Los datos de paquete no se importan como módulos, incluido el `__init__.py` del nodo.
- El nodo conserva su licencia GPL-3.0, que se incluye en el wheel junto con la MIT.
- El CI sigue sin necesitar GPU, ComfyUI ni modelos.
- Sigue siendo una fase solo para Linux: no se anuncia soporte de otros sistemas.

## Entregables

- `src/imagehearth_mcp/` con código y datos, sin las carpetas antiguas en la raíz.
- `pyproject.toml` y `uv.lock` actualizados, sin `requirements.txt`.
- Wheel instalable con `uv tool install ./`, con el comando `imagehearth-mcp`.
- Tests de configuración, de datos de paquete y de arranque del comando.
- `.github/workflows/ci.yml` con un trabajo contra el wheel instalado.
- `README.md`, `README.es.md`, `THIRD_PARTY_NOTICES.md` y `specs/tech-stack.md` actualizados.
- Instalación local migrada y generando imágenes.
- Tareas de la fase 1 marcadas en el roadmap.

## Supuestos

- Versión inicial `0.1.0.dev0`. La fase 6 publica la `0.1`.
- Expresión de licencia `MIT AND GPL-3.0-only`. Si el texto de `THIRD_PARTY_NOTICES.md` o la licencia de ComfyUI indican otra variante de GPL-3.0, se usa esa.
- El puerto y la URL de Ollama se aplican en todo el código, incluida la referencia fija de `mcp/server.py:139`. `COMFY_HOST` sigue siendo `127.0.0.1`.
