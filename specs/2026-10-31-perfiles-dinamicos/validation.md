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

- [x] Solo `fast`: `list_workflows` devuelve `sdxl_turbo` y la generación `fast` funciona.
- [x] Solo `fast`: `create_image` con `quality=high` da el error accionable y no se arranca ComfyUI.
- [x] Solo `fast`: `edit_image` da el error accionable e indica `full`.
- [x] Con `quality` y `full`: aparecen y funcionan los workflows correspondientes, sin reiniciar el servidor.
- [x] Modelo truncado a propósito: su workflow deja de ofrecerse.
- [x] `doctor` y el catálogo coinciden en qué perfil está completo.

### Instalación de desarrollo y modo adjunto

- [x] La instalación de desarrollo sigue ofreciendo y generando con sus tres capacidades.
- [x] Un ComfyUI adjunto ofrece lo que tiene. Si hay modelos en `extra_model_paths.yaml`, anotar el resultado en la evidencia.

### Separación del cargador

- [x] Edición real con Kontext con una referencia y con varias, en la RTX 4090.

### Mediciones

- [x] `scripts/measure_profiles.py` completo en la RTX 4090 con Linux.
- [ ] `scripts/measure_profiles.py` completo en el equipo NVIDIA con Windows, y catálogo comprobado allí.
- [x] Sin modelos de lenguaje cargados durante las mediciones.

### macOS preparado (sin Mac)

- [x] `flux_dev_gguf` genera una imagen en la RTX 4090 con los archivos `Q5_K_M` reales.
- [x] `flux_kontext_dev_gguf` edita una imagen en la RTX 4090 con los archivos `Q5_K_M` reales.
- [x] Los archivos descargados coinciden con el SHA-256 de `models.toml`.
- [x] Los perfiles `mac-*` no aparecen en Linux ni en Windows, y los perfiles existentes no cambian.
- [x] No se ejecuta en un Mac: MPS, PyTorch en Metal y memoria unificada quedan sin verificar, y no se anuncia como soportado.

## Lista para fusionar

- [ ] `scripts/check.sh` en verde en Linux y `scripts\check.ps1` en verde en Windows.
- [x] Prueba de contrato `/object_info` en verde.
- [ ] Validaciones manuales completadas.
- [x] Las 7 herramientas conservan nombres y parámetros, revisado en el diff.
- [ ] Ambos README y `tech-stack.md` actualizados con las mediciones.
- [ ] `models.toml` con los GGUF y `ComfyUI-GGUF` fijados, y `THIRD_PARTY_NOTICES.md` actualizado.
- [ ] README (ambos) y `tech-stack.md` dicen que macOS está preparado y sin probar.
- [ ] Roadmap actualizado con las tareas hechas.
- [ ] Cambios revisados por el usuario, que realiza el commit.

## Evidencia

| Comprobación | Resultado | Fecha |
|---|---|---|
| `scripts/check.sh` en Linux | Verde, 261 tests | 2026-10-31 |
| `scripts\check.ps1` en Windows | | |
| Prueba de contrato `/object_info` | Verde en Linux, 19 tipos de nodo, con ComfyUI-GGUF | 2026-10-31 |
| Catálogo con cada perfil | Prueba manual del usuario en Linux, con un ComfyUI adjunto aislado: `fast`, `quality` y `full` generan con cada perfil, y los errores indican el perfil. Modelo truncado y ComfyUI sin arrancar en los errores, comprobados aparte con carpetas aisladas | 2026-10-31 |
| Modelos en `extra_model_paths.yaml` | El supuesto falló: ComfyUI veía Kontext y el catálogo no. Catálogo y `doctor` leen ya ese archivo. Corrección cubierta con tests; falta repetir la edición real con el modelo en esa ruta | 2026-10-31 |
| Edición real tras la separación del cargador | Correcta con 1 y 2 referencias en la RTX 4090 | 2026-10-31 |
| Medición en RTX 4090 (Linux) | Completa; ver README. El arranque en frío no vacía la caché de disco | 2026-10-31 |
| Medición en equipo Windows (anotar GPU y VRAM) | | |
| Workflows GGUF en RTX 4090 | Ambos correctos con archivos reales, SHA-256 coincidente. Pico 14,4 y 12,9 GB; 23,8 y 30,1 s | 2026-10-31 |
| Flujo de `setup` con macOS simulado | Tests en verde (`tests/test_catalog.py`) | 2026-10-31 |
| macOS real | Sin verificar, no anunciado | |
