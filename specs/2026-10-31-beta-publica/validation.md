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

- [ ] Misma versión en `pyproject.toml`, `install.sh`, `install.ps1` y `server.json`.
- [ ] `server.json` válido.
- [ ] Wheel y sdist con datos de paquete y licencias, y sin modelos ni archivos locales.
- [ ] Scripts sin `sudo` ni `--accept-licenses`.

## Validaciones manuales

### Antes de fusionar

- [ ] Revisión de árbol e historial sin secretos ni datos privados, o decisión tomada con el mantenedor.
- [ ] `install.sh` en un HOME aislado con un wheel local: sin uv, con uv y repetido.
- [ ] `install.sh` por tubería desde un servidor local, para comprobar `/dev/tty` y el caso sin terminal.
- [ ] Registro MCP contrastado con su documentación actual, y supuestos de [requirements.md](requirements.md) resueltos.
- [ ] Enlaces del README correctos fuera de GitHub.

### Antes de publicar (pendientes de fases anteriores)

- [ ] `scripts\check.ps1` y `scripts\contract.ps1` en verde en Windows.
- [ ] `install.ps1` ejecutado en Windows.
- [ ] Generación real en Windows con NVIDIA.
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

- [ ] `scripts/check.sh` en verde en Linux.
- [ ] Prueba de contrato `/object_info` en verde.
- [ ] Validaciones "Antes de fusionar" completadas.
- [ ] Ambos README, `docs/troubleshooting.md`, `docs/releasing.md`, `docs/beta-testing.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md` y plantillas creados.
- [ ] Ningún documento anuncia como soportado algo sin probar.
- [ ] Roadmap actualizado con las tareas hechas.
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
| `scripts/check.sh` en Linux | | |
| `scripts\check.ps1` en Windows | | |
| Prueba de contrato `/object_info` | | |
| Revisión de árbol e historial | | |
| `install.sh` en HOME aislado | | |
| `install.ps1` en Windows | | |
| Generación y mediciones en Windows | | |
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
