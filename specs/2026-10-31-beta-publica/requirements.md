# Fase 6: Beta pública

## Contexto

Fase 6 del [roadmap](../roadmap.md), cuyo objetivo es que cualquiera con Linux o Windows y NVIDIA pueda instalar ImageHearth. Depende de las fases 3 y 5.

Estado de partida, comprobado el 2026-10-31:

- `pyproject.toml` está en `0.1.0.dev0`. No hay ninguna etiqueta de versión.
- `RealHemoglobin/ImageHearth` es **privado**, así que las URL de `raw.githubusercontent.com` del [destino](../roadmap.md#destino) aún no funcionan.
- `imagehearth-mcp` está libre en PyPI (la consulta devuelve 404).
- No existen `install.sh`, `install.ps1`, `server.json`, `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md` ni `.github/`.
- `mcp-publisher` no está instalado. En esta máquina tampoco están `pwsh` ni `shellcheck`.
- `setup` no conecta agentes: es un comando aparte, `connect --detect`.
- El README instala con `git clone` y lleva un aviso de desarrollo.
- `doctor --json` ya existe.

Pendientes de fases anteriores:

- `scripts\check.ps1` en verde y generación real en Windows.
- Mediciones de Windows en el README y `tech-stack.md`.
- Pruebas en máquinas limpias: Ubuntu y Windows 11 con NVIDIA.
- `llms-install.md` seguido de principio a fin por un agente real.

## Alcance

- `install.sh` e `install.ps1`, breves y legibles.
- Paquete preparado para publicar como `0.1.0b1`, con metadatos completos.
- `server.json` para el registro oficial de MCP.
- README en inglés y español reescritos: la instalación de un comando pasa a ser la principal y se quita el aviso de desarrollo.
- Guía de problemas frecuentes, `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md` y plantillas de incidencias que pidan la salida de `doctor --json`.
- Guía de publicación que el mantenedor sigue paso a paso, incluido el ensayo en TestPyPI.
- Revisión de que el repositorio se puede hacer público.
- Convocatoria y plantilla de informe para 5 a 10 probadores externos.
- Cierre de los pendientes listados arriba, como condición previa a publicar.

## Fuera de alcance

- **Ejecutar la publicación:** `uv publish`, `gh release create`, `mcp-publisher publish` y hacer público el repositorio los ejecuta el mantenedor.
- GitHub Actions y Trusted Publishing, según [tech-stack](../tech-stack.md).
- `.mcpb` para Claude Desktop, salvo que una prueba real demuestre que `connect` no basta.
- Publicar la `0.1.0` definitiva: llega después de que los probadores validen la beta.
- macOS como soportado, que sigue preparado sin probar, tras `--experimental`.
- Pendientes de la fase 4 que no bloquean: Mac, perfil GGUF para NVIDIA, origen de FLUX Dev y FLUX.1 Schnell.
- Revisión de seguridad completa y política de versiones: fase 7.

## Decisiones

| Tema | Decisión |
|---|---|
| Quién publica | El asistente lo deja todo listo y el mantenedor ejecuta cada paso irreversible |
| Pendientes anteriores | Bloquean la publicación, no la fusión: hay que fusionar antes, porque los scripts se sirven desde `main` |
| Versión | `0.1.0b1`, tras un ensayo en TestPyPI. La `0.1.0` sale cuando los probadores validen la beta |
| Instalación en los scripts | Instalar uv si falta, `uv tool install imagehearth-mcp==<versión>` con versión fijada, `setup` y `connect --detect`. Es lo que pide el [destino](../roadmap.md#destino), que incluye conectar agentes |
| Versión fijada | La misma en `pyproject.toml` e `install.*`. Un test lo comprueba |
| Entrada con `curl \| sh` | La entrada estándar es el propio script, así que `setup` y `connect` deben leer de `/dev/tty`. Sin terminal, el script se detiene y explica el comando no interactivo |
| Ruta del ejecutable | Los scripts lo localizan con `uv tool dir --bin`, porque puede no estar aún en `PATH` |
| Probadores | Criterio de cierre de la fase, no de fusión. Su evidencia se anota en [validation.md](validation.md) después de publicar |
| `.mcpb` | No se crea. Claude Desktop sigue con `connect` y `docs/agents.md`, marcado como sin probar mientras no se pruebe |
| Idioma | Scripts, guías, plantillas y README principal en inglés, con README en español. `specs/` en español |
| Guía de publicación | En `docs/releasing.md`, en inglés |

## Restricciones

- Los scripts no piden `sudo`, no aceptan licencias en nombre del usuario y no ocultan qué van a hacer. `setup` sigue mostrando espacio y licencias antes de descargar.
- Solo se anuncia como soportada una combinación de sistema y GPU probada con hardware real, según la [misión](../mission.md). Lo mismo vale para agentes y editores.
- Mantener la alternativa manual con `uv tool install` en el README.
- Los pesos de modelos nunca se redistribuyen: el paquete no los incluye.
- El servidor sigue arrancando sin PyTorch ni ComfyUI.
- Ningún token se escribe en el repositorio ni en scripts: `UV_PUBLISH_TOKEN` se usa solo en el entorno del mantenedor.
- Sin `git commit` por parte del asistente: el usuario revisa y confirma los cambios.

## Entregables

- `install.sh` e `install.ps1` en la raíz.
- `pyproject.toml` con versión `0.1.0b1` y metadatos: autores, palabras clave, clasificadores y URL.
- `server.json` y la marca de propiedad en el README que exija el registro.
- `README.md` y `README.es.md` reescritos.
- `docs/troubleshooting.md` y `docs/releasing.md`.
- `CHANGELOG.md`, `CONTRIBUTING.md` y `SECURITY.md`.
- `.github/ISSUE_TEMPLATE/` con plantillas para fallos de instalación, fallos generales y peticiones.
- `docs/beta-testing.md`, con la convocatoria y la plantilla de informe.
- Tests de versión fijada, contenido del paquete y validez de `server.json`.
- Roadmap con las tareas hechas marcadas cuando estén verificadas.

## Supuestos abiertos

- **Registro MCP (contrastado el 2026-10-31):** esquema `2025-12-11`, nombre con el prefijo `io.github.<usuario>/` y marca `mcp-name:` en el README de PyPI, ya incluida. Queda sin confirmar si el registro distingue mayúsculas en `RealHemoglobin`, y si acepta `0.1.0b1`: el esquema admite versiones que no son semver, pero lo recomienda. Se ve al ejecutar `mcp-publisher validate` y `publish`.
- **Versión preliminar con uv:** se supone que `uv tool install paquete==0.1.0b1` funciona sin `--prerelease`, al estar fijada. Se comprueba en el ensayo con TestPyPI, donde además hará falta indicar el índice y que las dependencias sigan viniendo de PyPI.
- **Hardware:** el mantenedor aporta el equipo Windows y las máquinas limpias. Sin ellos, la fusión es posible pero la publicación queda bloqueada.
- **`install.ps1` en esta máquina:** sin `pwsh` solo se puede ejecutar en Windows. Hasta entonces consta como sin ejecutar.
- **Historial de git:** no se ha revisado. Si la revisión de la tarea 2 encuentra secretos o datos personales, habrá que decidir con el mantenedor antes de hacer público el repositorio.
