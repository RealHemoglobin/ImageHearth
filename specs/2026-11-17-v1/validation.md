# Validación: Fase 16

La rama se fusiona cuando se cumplen tres condiciones:

- los tests simulados están en verde;
- `check` y `contract` están en verde en Linux y en Windows;
- la instalación funciona en una máquina limpia con Windows 11 y NVIDIA.

La fase se cierra cuando 1.0.0 está publicada y se ha comprobado desde las URL públicas.

## Criterios de finalización

- No queda ningún hallazgo de seguridad alto o medio sin corregir, y `docs/security-review.md` recoge todos los hallazgos con su estado.
- `docs/versioning.md` define la política. `update` migra un `install.json` de esquema 1 sin descargar ni borrar modelos y rechaza un esquema futuro sin cambiar nada.
- `scripts/contract_latest` comprueba el último ComfyUI publicado y deja un log y un código de salida. La guía explica cómo programarlo en Windows y en Linux.
- `tech-stack.md` describe los trabajos en segundo plano y la política de versiones.
- No queda `0.1.0b3` en el repositorio, salvo en el historial de `CHANGELOG.md`.
- Se cumplen los cinco criterios de la misión (tabla de evidencia).
- 1.0.0 está en PyPI, en la GitHub Release y en el registro MCP.

## Validaciones automáticas

En Linux, desde la raíz del repositorio:

```bash
scripts/check.sh
scripts/contract.sh
```

En Windows:

```powershell
scripts\check.ps1
scripts\contract.ps1
scripts\contract_latest.ps1
```

`check` ejecuta `uv sync --locked`, `ruff`, `pytest` y los tests contra el wheel instalado: es la puerta de calidad de [tech-stack](../tech-stack.md). `contract_latest` sirve de aviso. Si falla porque el último ComfyUI cambió, no bloquea la fusión, pero se anota en la evidencia.

Los tests deben cubrir:

- [ ] Cada corrección de seguridad alta o media, con un caso que fallaba antes.
- [ ] Extracción del archivo de ComfyUI: rechaza rutas con `..`, absolutas y enlaces.
- [ ] Registros de esquema 1 de las fases 9, 13 y 15: cargan, migran y conservan modelos, predeterminados, LoRAs, carpeta y conexiones.
- [ ] Migración simulada de esquema 1 a 2: aplicada en orden, con copia `.bak` y una sola escritura.
- [ ] Esquema futuro: error que pide actualizar ImageHearth, sin cambiar el registro.
- [ ] `update` muestra el origen y el destino. Sin cambios, no descarga nada. Con `--yes`, no pregunta.
- [ ] `doctor` (también `--json`) informa de un registro que necesita migración.
- [ ] `contract_latest`: resuelve la última versión (con la API simulada), registra la versión probada y devuelve el código de salida correcto.
- [ ] Ningún test toca el `HOME` real ni descarga nada.

## Validaciones manuales

En Windows 11 con NVIDIA:

- [ ] Máquina limpia: `irm ... install.ps1 | iex` desde la rama. Instala sin intervención salvo licencias y perfil.
- [ ] Primera imagen generada por un agente conectado con `connect`, sin editar ningún archivo a mano.
- [ ] `doctor` detecta un fallo provocado (ComfyUI parado o un modelo borrado) y dice cómo arreglarlo.
- [ ] `uninstall` deja intactos un ComfyUI y unos modelos que ya existían.
- [ ] `update` desde una instalación `0.1.0b3`: migra, conserva modelos y conexiones y sigue generando.
- [ ] `contract_latest.ps1` programado con el Programador de tareas: se ejecuta y deja el log.
- [ ] Supuesto de Linux resuelto: prueba real de 1.0.0 en Linux, o README ajustado.

Después de publicar:

- [ ] `irm https://raw.githubusercontent.com/RealHemoglobin/ImageHearth/main/install.ps1 | iex` en Windows.
- [ ] `curl ... install.sh | sh` en Linux, si se confirma el supuesto.
- [ ] `uv tool install imagehearth-mcp==1.0.0` funciona como alternativa manual.
- [ ] La entrada del registro MCP es visible y está en 1.0.0.

## Criterios de la misión

| Criterio | Quién | Máquina | Fecha | Resultado |
|---|---|---|---|---|
| 1. La instalación en máquina limpia termina sin intervención salvo licencias y perfil | Usuario | Windows 11, NVIDIA | | |
| 2. Primera imagen sin editar configuración a mano | Usuario | Windows 11, NVIDIA | | |
| 3. `doctor` dice qué falla y cómo arreglarlo | Usuario | Windows 11, NVIDIA | | |
| 4. Desinstalar deja el sistema como estaba | Usuario | Windows 11, NVIDIA | | |
| 5. Solo se anuncian combinaciones probadas con hardware real | Asistente (README y `tech-stack.md`) y usuario | — | | |

## Lista para fusionar

- [ ] `scripts/check.sh` y `scripts/contract.sh` en verde en Linux.
- [ ] `scripts\check.ps1` y `scripts\contract.ps1` en verde en Windows.
- [ ] Instalación en máquina limpia Windows 11 con NVIDIA completada.
- [ ] `docs/security-review.md` sin hallazgos altos ni medios abiertos.
- [ ] Documentación y versión 1.0.0 revisadas.
- [ ] El usuario ha revisado los cambios y ha hecho los commits.

## Lista para cerrar la fase

- [ ] 1.0.0 publicada en PyPI, en la GitHub Release y en el registro MCP.
- [ ] Validaciones posteriores a la publicación completadas.
- [ ] Tabla de criterios de la misión completa.
- [ ] Roadmap con la fase 16 completada y «Siguiente paso» actualizado.

## Evidencia

Se rellena durante la implementación con:

- los comandos;
- la fecha;
- la máquina;
- los resultados;
- los ajustes de tests existentes.
