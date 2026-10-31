# Validación: Fase 4

## Criterios de finalización

- `list_workflows` devuelve solo lo instalado, con la forma `{name, file}`.
- Con solo `fast`, `quality=high` y `edit_image` fallan con un error que indica el perfil y el comando de `setup`, sin arrancar ComfyUI ni tocar Ollama.
- Ninguna petición cambia de modelo en silencio.
- Ampliar el perfil se nota sin reiniciar el servidor MCP.
- `kontext.build_workflow` no usa identificadores fijos y su resultado es equivalente al anterior, con una y con varias referencias.
- La tabla de requisitos de ambos README contiene mediciones reales de la RTX 4090 y del equipo Windows, con el equipo indicado.
- Las 7 herramientas conservan nombres y parámetros, y el servidor sigue arrancando sin ComfyUI.
- En macOS simulado, `setup` rechaza continuar sin `--experimental` antes de descargar nada, y con él completa el flujo con perfiles `mac-*`.
- Los modelos GGUF tienen revisión, tamaño y SHA-256 fijados, y sus workflows se han ejecutado de verdad en la RTX 4090.
- Ningún documento anuncia macOS como soportado, y ninguna fase posterior depende de probarlo.

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

Los tests simulan la carpeta de modelos y no descargan nada. La puerta de calidad obligatoria de [tech-stack](../tech-stack.md) es `scripts/check.sh` más la prueba de contrato.

## Validaciones manuales

### Catálogo (Linux, con carpetas aisladas)

- [ ] Solo `fast`: `list_workflows` devuelve `sdxl_turbo` y la generación `fast` funciona.
- [ ] Solo `fast`: `create_image` con `quality=high` da el error accionable y no se arranca ComfyUI.
- [ ] Solo `fast`: `edit_image` da el error accionable e indica `full`.
- [ ] Con `quality` y `full`: aparecen y funcionan los workflows correspondientes, sin reiniciar el servidor.
- [ ] Modelo truncado a propósito: su workflow deja de ofrecerse.
- [ ] `doctor` y el catálogo coinciden en qué perfil está completo.

### Instalación de desarrollo y modo adjunto

- [ ] La instalación de desarrollo sigue ofreciendo y generando con sus tres capacidades.
- [ ] Un ComfyUI adjunto ofrece lo que tiene. Si hay modelos en `extra_model_paths.yaml`, anotar el resultado en la evidencia.

### Separación del cargador

- [ ] Edición real con Kontext con una referencia y con varias, en la RTX 4090.

### Mediciones

- [ ] `scripts/measure_profiles.py` completo en la RTX 4090 con Linux.
- [ ] `scripts/measure_profiles.py` completo en el equipo NVIDIA con Windows, y catálogo comprobado allí.
- [ ] Sin modelos de lenguaje cargados durante las mediciones.

### macOS preparado (sin Mac)

- [ ] `flux_dev_gguf` genera una imagen en la RTX 4090 con los archivos `Q5_K_M` reales.
- [ ] `flux_kontext_dev_gguf` edita una imagen en la RTX 4090 con los archivos `Q5_K_M` reales.
- [ ] Los archivos descargados coinciden con el SHA-256 de `models.toml`.
- [ ] Los perfiles `mac-*` no aparecen en Linux ni en Windows, y los perfiles existentes no cambian.
- [x] No se ejecuta en un Mac: MPS, PyTorch en Metal y memoria unificada quedan sin verificar, y no se anuncia como soportado.

## Lista para fusionar

- [ ] `scripts/check.sh` en verde en Linux y `scripts\check.ps1` en verde en Windows.
- [ ] Prueba de contrato `/object_info` en verde.
- [ ] Validaciones manuales completadas.
- [ ] Las 7 herramientas conservan nombres y parámetros, revisado en el diff.
- [ ] Ambos README y `tech-stack.md` actualizados con las mediciones.
- [ ] `models.toml` con los GGUF y `ComfyUI-GGUF` fijados, y `THIRD_PARTY_NOTICES.md` actualizado.
- [ ] README (ambos) y `tech-stack.md` dicen que macOS está preparado y sin probar.
- [ ] Roadmap actualizado con las tareas hechas.
- [ ] Cambios revisados por el usuario, que realiza el commit.

## Evidencia

| Comprobación | Resultado | Fecha |
|---|---|---|
| `scripts/check.sh` en Linux | | |
| `scripts\check.ps1` en Windows | | |
| Prueba de contrato `/object_info` | | |
| Catálogo con cada perfil | | |
| Modelos en `extra_model_paths.yaml` | | |
| Edición real tras la separación del cargador | | |
| Medición en RTX 4090 (Linux) | | |
| Medición en equipo Windows (anotar GPU y VRAM) | | |
| Workflows GGUF en RTX 4090 | | |
| Flujo de `setup` con macOS simulado | | |
| macOS real | Sin verificar, no anunciado | |
