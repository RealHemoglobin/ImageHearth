# Validación: Fase 7

La validación tiene dos puertas: fusionar la rama (RTX 4090 en Linux y Windows con NVIDIA) y cerrar la fase (AMD de 16 GB en Windows, después de fusionar).

## Criterios de finalización

- Tras `install.sh` o `install.ps1`, `imagehearth-mcp` funciona en una terminal nueva sin pasos manuales.
- `doctor` detecta que el comando no está en el `PATH` y da la orden exacta.
- En una tarjeta de 16 GB (simulada para fusionar, real para cerrar) `setup` propone FLUX GGUF y `quality` genera sin quedarse sin memoria, aunque tarde más.
- En una de 8 GB (simulada) `setup` propone la variante SDXL y `quality` genera con ella; la edición consta como no disponible con un error claro.
- Con un `llama-server` de un solo modelo cargado y `memory_mode = "auto"`, una generación lo para, genera y lo deja respondiendo con el mismo modelo y los mismos parámetros, con un `WARNING:` en el resultado.
- Un `llama-server` de otro usuario, de un servicio o de un contenedor no se toca; solo se avisa.
- Con `memory_mode = "manual"` u `off` no se para ningún proceso.
- Ningún documento anuncia como soportado lo que solo se ha simulado.

## Validaciones automáticas

Desde la raíz del repositorio, en Linux:

```bash
scripts/check.sh
```

Ejecuta `uv sync --locked`, `ruff`, `pytest` y los tests contra el wheel instalado en un entorno aparte.

```bash
scripts/contract.sh
```

Prueba de contrato con `/object_info`, que debe incluir los nodos de `sdxl_quality`.

```bash
sh -n install.sh
```

En Windows (PowerShell):

```powershell
scripts\check.ps1
```

```powershell
scripts\contract.ps1
```

La puerta de calidad obligatoria de [tech-stack](../tech-stack.md) es `scripts/check.sh` más la prueba de contrato.

Los tests deben cubrir:

- [ ] Instaladores con `uv tool update-shell`, sin `sudo` ni `--accept-licenses`.
- [ ] Comprobación de `PATH` en `doctor`, también en `--json`.
- [ ] Identificación de `llama-server`: mismo usuario, `/props`, otro programa en el puerto, otro usuario, servicio o contenedor.
- [ ] Parada y relanzado con `exe()`, `cwd()` y entorno; `AccessDenied` en `environ()`; fallo al relanzar.
- [ ] Relanzado desde `recover_engine` tras una caída a mitad.
- [ ] `manual` y `off` no paran ningún proceso.
- [ ] Elección de argumentos de ComfyUI por hardware y `comfy_args` que prevalece.
- [ ] Comprobación de memoria: cabe, cabe con RAM y aviso, no cabe.
- [ ] Elección de variante en `setup` y en `catalog.choose` por tramo de VRAM.
- [ ] `models.toml` válido, con revisión, tamaño, SHA-256 y licencia de los modelos nuevos.
- [ ] Edición no disponible por debajo de 12 GB con mensaje accionable.

## Validaciones manuales

### Antes de fusionar (RTX 4090 en Linux)

- [ ] `install.sh` en un HOME aislado con un wheel local, con zsh, bash y fish: `imagehearth-mcp` se encuentra en un shell nuevo.
- [ ] `install.sh` con `uv` ya presente y con `uv` del gestor del sistema, si está disponible.
- [ ] `doctor` con el directorio de herramientas fuera del `PATH`: da la orden exacta.
- [ ] `llama-server` real de un solo modelo: una generación lo para, libera la VRAM, genera y lo relanza con el mismo modelo, `n_ctx` y directorio, y responde.
- [ ] Matar el motor a mitad de una generación con `llama-server` parado: `recover_engine` lo relanza.
- [ ] Mediciones de fp8, GGUF y SDXL nativas y simulando 16 y 8 GB con `--reserve-vram`.
- [ ] `quality` genera simulando 16 GB con la variante GGUF.
- [ ] `quality` genera simulando 8 GB con la variante SDXL.
- [ ] `setup` propone la variante correcta en cada tramo simulado y muestra tamaño y licencias de esa variante.
- [ ] Comparación de calidad de las tres variantes con los mismos prompts.

### Antes de fusionar (Windows con NVIDIA)

- [ ] `scripts\check.ps1` en verde.
- [ ] `scripts\contract.ps1` en verde.
- [ ] `install.ps1`: `imagehearth-mcp` se encuentra en una PowerShell nueva.
- [ ] `llama-server` oficial de Windows: se para y vuelve sin abrir consola.
- [ ] Mediciones de Windows en el README.

### Para cerrar la fase (AMD de 16 GB en Windows, después de fusionar)

- [ ] `doctor` muestra los argumentos de ComfyUI efectivos para ROCm Windows.
- [ ] `setup` propone la variante GGUF.
- [ ] `quality` genera sin quedarse sin memoria.
- [ ] Con un `llama-server` de un solo modelo cargado, se para, genera y vuelve.

## Lista para fusionar

- [ ] `scripts/check.sh` en verde en Linux.
- [ ] Prueba de contrato `/object_info` en verde, con `sdxl_quality`.
- [ ] Validaciones "Antes de fusionar" de Linux y Windows completadas.
- [ ] Checkpoint SDXL y LoRAs con licencia que permita uso comercial, anotada en `THIRD_PARTY_NOTICES.md`.
- [ ] README, `docs/troubleshooting.md` y `tech-stack.md` actualizados, marcando lo simulado.
- [ ] Roadmap actualizado con las tareas hechas.
- [ ] Cambios revisados por el usuario, que realiza el commit.

## Lista para cerrar la fase

- [ ] Validaciones "Para cerrar la fase" completadas en la AMD de 16 GB.
- [ ] Roadmap con la fase marcada como completada.

## Evidencia

| Comprobación | Resultado | Fecha |
|---|---|---|
| `scripts/check.sh` en Linux | | |
| Prueba de contrato `/object_info` | | |
| `install.sh` y `PATH` (zsh, bash, fish) | | |
| `doctor` sin `PATH` | | |
| `llama-server` de un solo modelo en Linux | | |
| Recuperación con `llama-server` parado | | |
| LM Studio y vLLM: conclusión | | |
| Mediciones RTX 4090 nativa | | |
| Mediciones simulando 16 GB | | |
| Mediciones simulando 8 GB | | |
| Elección de SDXL y LoRAs (candidatos, licencias, motivo) | | |
| Comparación de calidad | | |
| `scripts\check.ps1` y `scripts\contract.ps1` en Windows | | |
| `install.ps1` y `PATH` en Windows | | |
| `llama-server` en Windows | | |
| Mediciones de Windows | | |
| AMD de 16 GB en Windows | | |
