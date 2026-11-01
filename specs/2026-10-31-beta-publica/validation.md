# Validación: Fase 6

La validación tiene tres puertas, en este orden: fusionar la rama, publicar y cerrar la fase.

## Criterios de finalización

- Los comandos de instalación del [destino](../roadmap.md#destino) funcionan desde sus URL públicas en Linux y en Windows 11 con NVIDIA: instalan uv y el paquete, ejecutan `setup`, conectan los agentes detectados y generan una imagen de prueba.
- Con `curl | sh`, `setup` y `connect` siguen pudiendo preguntar al usuario. Sin terminal, el script se detiene con un mensaje claro y no acepta licencias.
- `imagehearth-mcp` `0.1.0b1` se instala desde PyPI y aparece en el registro oficial de MCP.
- La GitHub Release `v0.1.0b1` existe y su versión coincide con el paquete, los scripts y `server.json`.
- El README ya no lleva el aviso de desarrollo, y solo anuncia lo probado con hardware real.
- Las plantillas de incidencias piden la salida de `doctor --json`, y con ella se puede diagnosticar un fallo de instalación.
- **Cierre de la fase:** al menos 3 personas externas instalan y generan sin ayuda.

## Validaciones automáticas

Desde la raíz del repositorio, en Linux:

```bash
scripts/check.sh
```

Ejecuta `uv sync --locked`, `ruff`, `pytest` y los tests contra el wheel instalado en un entorno aparte.

```bash
scripts/contract.sh
```

Prueba de contrato: ComfyUI en CPU y comprobación con `/object_info` de que existen todos los nodos que usan los workflows.

En Windows (PowerShell):

```powershell
scripts\check.ps1
```

```powershell
scripts\contract.ps1
```

Contenido y sintaxis:

```bash
uv build
```

```bash
sh -n install.sh
```

La puerta de calidad obligatoria de [tech-stack](../tech-stack.md) es `scripts/check.sh` más la prueba de contrato.

Los tests deben cubrir:

- [x] Misma versión en `pyproject.toml`, `install.sh`, `install.ps1` y `server.json`.
- [x] `server.json` válido.
- [x] Wheel y sdist con datos de paquete y licencias, y sin modelos ni archivos locales.
- [x] Scripts sin `sudo` ni `--accept-licenses`.

## Validaciones manuales

### Antes de fusionar

- [x] Revisión de árbol e historial sin secretos ni datos privados, o decisión tomada con el mantenedor.
- [x] `install.sh` en un HOME aislado con un wheel local: sin uv, con uv y repetido.
- [x] `install.sh` por tubería desde un servidor local, para comprobar `/dev/tty` y el caso sin terminal.
- [x] Registro MCP contrastado con su documentación actual, y supuestos de [requirements.md](requirements.md) resueltos.
- [x] Enlaces del README correctos fuera de GitHub.

### Antes de publicar (pendientes de fases anteriores)

- [x] `scripts\check.ps1` en verde en Windows.
- [ ] `scripts\contract.ps1` en verde en Windows.
- [x] `install.ps1` ejecutado en Windows (desde un clon del repositorio).
- [x] Generación real en Windows con NVIDIA.
- [ ] Mediciones de Windows en el README y `tech-stack.md`.
- [ ] Máquina limpia Ubuntu con NVIDIA: instalación completa e imagen de prueba.
- [ ] Máquina limpia Windows 11 con NVIDIA: instalación completa e imagen de prueba.
- [ ] Interrumpir la descarga y repetir continúa donde se quedó.
- [ ] Un archivo corrupto se detecta y se vuelve a descargar.
- [ ] Con espacio insuficiente falla antes de descargar nada.
- [ ] `uninstall` deja intactos un ComfyUI y unos modelos preexistentes.
- [ ] Un agente real completa la instalación siguiendo `llms-install.md`.
- [ ] Ensayo en TestPyPI instalado en Linux y Windows.

### Después de publicar

- [ ] `curl ... install.sh | sh` desde la URL pública, en Linux.
- [ ] `irm ... install.ps1 | iex` desde la URL pública, en Windows.
- [ ] Entrada visible y correcta en el registro MCP.
- [ ] `uv tool install imagehearth-mcp==0.1.0b1` funciona como alternativa manual.

## Lista para fusionar

- [x] `scripts/check.sh` en verde en Linux.
- [x] Prueba de contrato `/object_info` en verde.
- [x] Validaciones "Antes de fusionar" completadas.
- [x] Ambos README, `docs/troubleshooting.md`, `docs/releasing.md`, `docs/beta-testing.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md` y plantillas creados.
- [x] Ningún documento anuncia como soportado algo sin probar.
- [x] Roadmap actualizado con las tareas hechas.
- [ ] Cambios revisados por el usuario, que realiza el commit.

Fusionar no significa publicar: la publicación sigue bloqueada hasta completar "Antes de publicar".

## Lista para cerrar la fase

- [ ] Validaciones "Antes de publicar" y "Después de publicar" completadas.
- [ ] Entre 5 y 10 probadores convocados, en hardware distinto.
- [ ] Al menos 3 personas externas instalan y generan sin ayuda.
- [ ] Los fallos de instalación recibidos se pudieron diagnosticar con `doctor --json`.
- [ ] Roadmap con la fase marcada como completada.

## Evidencia

| Comprobación | Resultado | Fecha |
|---|---|---|
| `scripts/check.sh` en Linux | Verde: 380 tests, ruff limpio, también contra el wheel | 2026-10-31 |
| `scripts\check.ps1` en Windows | Verde (Windows 11, Python 3.13): ruff y 376 tests con 4 omitidos, también contra el wheel | 2026-11-01 |
| Prueba de contrato `/object_info` | Verde: existen los 19 tipos de nodo | 2026-10-31 |
| Revisión de árbol e historial | Sin tokens, claves, rutas personales ni correos personales, en los 25 commits. Ningún binario, `engine.lock`, `state/` ni `logs/` versionado. Un commit de 2026-10-31 (`d8ef2c5`) tiene como autor el nombre `TitoYano`, con correo noreply del mismo identificador de GitHub: es público, sin secreto, y lo decide el mantenedor | 2026-10-31 |
| `install.sh` en HOME aislado | Con wheel local, sin uv, por tubería desde un servidor local y dentro de una terminal: instala uv y el paquete, pregunta por `/dev/tty`, y al rechazar las licencias no descarga nada y sale con 1. Repetido con uv: no rompe nada. Sin terminal (`setsid`): se detiene sin tocar nada. `connect --detect` real: detecta clientes, pregunta por cada uno y, al responder que no, no cambia nada. Orden `setup` + `connect` con terminal comprobado con un ejecutable simulado, porque el real exige aceptar licencias y descargar. La descarga real queda para las máquinas limpias | 2026-10-31 |
| `install.ps1` en Windows | Ejecutado desde un clon (instala el código del clon) en el equipo de desarrollo, tras borrar el ComfyUI y los modelos instalados a mano: `setup` completo con el perfil `full` y `doctor` en verde (RTX 4090, controlador 621.01). No es una máquina limpia ni la URL pública | 2026-11-01 |
| Generación y mediciones en Windows | Generación `fast` y `quality` correcta con Claude Code (`claude`). Mediciones sin hacer | 2026-11-01 |
| Máquina limpia Ubuntu | | |
| Máquina limpia Windows 11 | | |
| `llms-install.md` con un agente real | | |
| Ensayo en TestPyPI | | |
| Publicación en PyPI y GitHub Release | | |
| Registro MCP | | |
| Comandos desde las URL públicas | | |

### Probadores externos

| Probador | Sistema y GPU | Agente | Instaló sin ayuda | Generó | Incidencia | Fecha |
|---|---|---|---|---|---|---|
| | | | | | | |
