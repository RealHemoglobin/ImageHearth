# Validación: Fase 3

## Criterios de finalización

- `imagehearth-mcp setup` funciona en máquinas limpias Ubuntu y Windows 11 con NVIDIA y termina generando una imagen de prueba.
- Interrumpir la descarga y repetir el comando continúa donde se quedó.
- Un archivo corrupto se detecta y se vuelve a descargar.
- Con espacio insuficiente falla antes de descargar nada.
- `uninstall` deja intactos un ComfyUI y unos modelos preexistentes.
- Nada se descarga sin mostrar el resumen y aceptar las licencias.
- `doctor` identifica la capa que falla y cómo arreglarla, también con `--json`.
- `imagehearth-mcp` sin argumentos sigue sirviendo MCP por stdio, y las 7 herramientas no cambian.
- La decisión del spike está documentada en `tech-stack.md`.

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

Los tests simulan hardware, red y procesos, y no descargan modelos. No se exige cobertura mínima. La puerta de calidad obligatoria de [tech-stack](../tech-stack.md) es `scripts/check.sh` más la prueba de contrato.

## Validaciones manuales

### Ubuntu limpio con NVIDIA

- [ ] `uv tool install` y `imagehearth-mcp setup --profile fast` terminan con la imagen de prueba.
- [ ] Ampliar a `full` no vuelve a descargar lo que ya existe.
- [ ] Generación con `fast`, generación con `quality` y edición con Kontext desde un agente conectado a mano.
- [ ] Interrumpir la descarga y repetir: continúa donde se quedó.
- [ ] Corromper un modelo y repetir: se detecta y se vuelve a descargar.
- [ ] Con espacio insuficiente: falla antes de descargar nada, con un mensaje accionable.
- [ ] Modo no interactivo sin `--accept-licenses`: falla sin descargar nada.
- [ ] Puerto ocupado y driver ausente: mensajes accionables.
- [ ] `doctor` y `doctor --json` con el sistema correcto y con una capa rota a propósito.
- [ ] `update` sobre una instalación existente.
- [ ] `uninstall` en modo gestionado: borra lo propio y pide confirmación para los modelos.

### Windows 11 limpio con NVIDIA

- [ ] `uv tool install` y `imagehearth-mcp setup --profile fast` terminan con la imagen de prueba.
- [ ] Generación con `fast`, generación con `quality` y edición con Kontext desde un agente conectado a mano.
- [ ] Interrumpir la descarga y repetir: continúa donde se quedó.
- [ ] Corromper un modelo y repetir: se detecta y se vuelve a descargar.
- [ ] Con espacio insuficiente: falla antes de descargar nada.
- [ ] `doctor --json` y `uninstall` funcionan, incluidos los archivos abiertos o bloqueados.

### Modo adjunto (en Linux y en Windows)

- [ ] Se detecta un ComfyUI existente, y en Windows también ComfyUI Desktop.
- [ ] El nodo se instala solo con permiso, y la generación funciona con la URL y las rutas configuradas.
- [ ] Los modelos ya presentes no se vuelven a descargar.
- [ ] `uninstall` deja intactos ese ComfyUI y sus modelos.

### Instalación de desarrollo

- [ ] La instalación actual sigue generando imágenes tras reinstalar el paquete.

### macOS

- [ ] No se verifica en esta fase y no se anuncia como soportado: anotarlo en la evidencia.

## Lista para fusionar

- [ ] `scripts/check.sh` en verde en Linux y `scripts\check.ps1` en verde en Windows.
- [ ] Prueba de contrato `/object_info` en verde.
- [ ] Validaciones manuales de Ubuntu, Windows 11 y modo adjunto completadas.
- [ ] Las 7 herramientas conservan nombres, parámetros y resultados, revisado en el diff.
- [ ] `models.toml` con todas las revisiones fijadas y los SHA-256 comprobados.
- [ ] Texto de consentimiento revisado con las licencias confirmadas.
- [ ] README (ambos), `tech-stack.md` y `THIRD_PARTY_NOTICES.md` actualizados.
- [ ] Roadmap actualizado con las tareas de la fase 3 verificadas.
- [ ] Cambios revisados por el usuario, que realiza el commit.

## Evidencia

| Comprobación | Resultado | Fecha |
|---|---|---|
| Decisión del spike | | |
| `scripts/check.sh` en Linux | | |
| `scripts\check.ps1` en Windows | | |
| Prueba de contrato `/object_info` | | |
| `setup` en Ubuntu limpio | | |
| `setup` en Windows 11 limpio | | |
| Reanudación de descarga | | |
| Archivo corrupto | | |
| Espacio insuficiente | | |
| Modo adjunto y `uninstall` con datos preexistentes | | |
| `doctor --json` con capa rota | | |
| macOS | Sin verificar, no anunciado | |
