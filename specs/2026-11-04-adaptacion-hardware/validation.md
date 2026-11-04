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
| Prueba de contrato `/object_info` | `scripts/contract.sh` en verde: existen los 20 tipos de nodo, con `sdxl_quality` | 2026-11-04 |
| `install.sh` y `PATH` (zsh, bash, fish) | `ensure_in_path` con `HOME` aislado y la herramienta fuera del `PATH`: en bash crea `.bash_profile` y `.bashrc`, en zsh `.zshenv`, y un shell de login nuevo encuentra el comando. Probada la función con un `imagehearth-mcp` de mentira, no el instalador completo. fish 4.9.3 (binario oficial, SHA-256 verificado): crea `config.fish` y un fish de login nuevo encuentra el comando | 2026-11-04 |
| `doctor` sin `PATH` | Con `PATH=/usr/bin:/bin` el check `path` da WARN con la orden `uv tool update-shell` y abrir un terminal nuevo. Con el comando en el `PATH` da OK | 2026-11-04 |
| `llama-server` de un solo modelo en Linux | `llama-server` b12110 (build CPU, SHA-256 verificado) con Qwen2.5-0.5B Q4_K_M en el puerto 8099: `loaded()` lee la línea de comandos, el directorio y el entorno; `unload` lo para al instante y `restore` lo vuelve a lanzar en 2 s con los mismos argumentos, directorio y variable de entorno, y responde. Build CPU, no CUDA. Descubrió un fallo: un servidor lanzado desde una terminal que corre como servicio de systemd heredaba `INVOCATION_ID` y se tomaba por servicio; ahora se distingue por el cgroup (`.service` frente a `.scope`) | 2026-11-04 |
| Recuperación con `llama-server` parado | | |
| LM Studio y vLLM: conclusión | **No se implementa el relanzado.** LM Studio: con su API REST v1 ya se descarga y se recarga por HTTP; sin ella, la salida es `lms unload --all`, porque matar el proceso de LM Studio cerraría su interfaz y sus sesiones, y no es un servidor que se relance sin más. vLLM: el modo de reposo (`/sleep`, `/wake_up`) ya libera la GPU y es la vía soportada; relanzarlo cuesta minutos (carga de pesos y grafos CUDA) y suele correr en contenedor, que el método del proceso por puerto no ve. En ambos casos se mantiene el aviso con el consejo exacto. Valorado leyendo el código y la API, sin probarlo con LM Studio ni vLLM reales | 2026-11-04 |
| Mediciones RTX 4090 nativa | `flux_dev` (fp8): pico 19352 MiB con 3175 de base (≈16,2 GB propios), 2,2 GB de RAM, 15,1 s en frío y 11,1 s en caliente. `flux_dev_gguf` (Q5): pico 14395 con 3129 de base (≈11,3 GB), 6,8 GB de RAM, 27,4 s en frío y 24,5 s en caliente. `sdxl_quality` (1024×1024, 2 pasadas): pico 9584 MiB con 3146 de base (≈6,4 GB propios), 2826 MiB de RAM, 6,3 s en frío y 4,8 s en caliente. 1024×1024, 2 pasadas | 2026-11-04 |
| Mediciones simulando 16 GB | Con `--reserve-vram=8` (tope ≈16,5 GB): fp8 pico 16572 MiB y 11,1 s (sin cambio); GGUF pico 10950 MiB y 25,3 s. Aún no se ha probado un caso en el que fp8 no quepa y desborde a RAM | 2026-11-04 |
| Mediciones simulando 8 GB | `sdxl_quality` con `--reserve-vram=16`: pico 8327 MiB, 4,8 s en caliente. `--reserve-vram` no limita el uso real de una tarjeta que tiene memoria libre, así que esto prueba que cabe en 8 GB, no el comportamiento con desbordamiento a RAM | 2026-11-04 |
| Elección de SDXL y LoRAs (candidatos, licencias, motivo) | RealVisXL V5.0 fp16 (openrail++) y LoRA offset oficial de SDXL 1.0 (openrail++). Descartados: Juggernaut XL v9 (OpenRAIL-M original), Playground v2.5 (licencia propia), slider de ntc-ai (terceros). Descargados con SHA-256 verificado; `sdxl_quality` genera 1024×1024 en la RTX 4090 (16 s en total con el arranque de ComfyUI). Sin comparar aún con FLUX | 2026-11-04 |
| Comparación de calidad | Mismas 3 indicaciones y semilla 42, 1024×1024: `comparison.jpg` (filas fp8, GGUF Q5, SDXL). fp8 y GGUF Q5 son casi indistinguibles (composición y texto «OPEN» correctos en ambos); GGUF tarda 2,2 veces más. SDXL RealVisXL es más rápido (4,8 s) y fotográfico, pero con menos detalle y peor texto (letras deformadas en el segundo cartel). Juicio visual de una sola persona, sin métrica | 2026-11-04 |
| `scripts\check.ps1` y `scripts\contract.ps1` en Windows | | |
| `install.ps1` y `PATH` en Windows | | |
| `llama-server` en Windows | | |
| Mediciones de Windows | | |
| AMD de 16 GB en Windows | | |
