# Validación: Fase 15

Una sola puerta: la rama no se fusiona hasta que estén en verde los tests simulados, `scripts/check.sh`, la prueba de contrato, las pruebas reales rápidas del asistente con los modelos pequeños y las del usuario con los modelos grandes.

## Criterios de finalización

- Cada modelo y precisión de la [decisión de la fase 14](../2026-11-15-analisis-modelos/analysis.md) se instala con `setup`, genera (o edita) con `create_image` y su forma de lista, y se puede quitar.
- En cada capacidad del perfil (`fast`, `quality`, `full`) se pueden instalar varios modelos, con una precisión cada uno y un predeterminado.
- `setup` muestra por opción tamaño, tiempo y VRAM medidos para el nivel de la GPU, recomienda sin impedir elegir otra, y enseña el resumen de espacio antes de confirmar.
- Sin `model` se usa el predeterminado; con una instalación migrada de la fase 13 el comportamiento es idéntico al de hoy.
- El agente ve con `list_workflows` los modelos instalados (capacidad, precisión, predeterminado, licencia, tiempo) y elige uno con `model`, también por elemento de un lote.
- Errores de `model` (no instalado, de otra capacidad, con `workflow`) y de LoRAs con un modelo que no es SDXL 1.0 llegan antes de tocar la GPU.
- Hay al menos una opción recomendada y medida para 8, 16, 24 y 32+ GB, y existe una instalación completa (generación y edición) con licencia comercial.
- Los componentes compartidos se descargan una vez y solo se borran cuando ningún modelo los usa.

## Validaciones automáticas

Desde la raíz del repositorio, en Linux:

```bash
scripts/check.sh
```

Ejecuta `uv sync --locked`, `ruff`, `pytest` y los tests contra el wheel instalado. Es la puerta de calidad obligatoria de [tech-stack](../tech-stack.md).

```bash
scripts/contract.sh
```

Prueba de contrato: esta fase añade workflows y tipos de nodo.

Los tests deben cubrir:

- [x] Catálogo por capacidad válido y rechazos: nombre repetido, capacidad desconocida, precisión repetida, workflow o peso inexistente, licencia ausente.
- [x] `Manifest.resolve` con varios modelos por capacidad; componentes compartidos deduplicados (Klein en `fast` y edición, Qwen3-4B, T5/VAE con Chroma).
- [x] Migración de manifiestos de instalación de las fases 9–13 sin descargas ni borrados, con predeterminados correctos.
- [x] Workflow de cada modelo y precisión nuevos: nodos, conexiones y marcadores rellenos (prompt, negativo, tamaño, semilla e imágenes en edición).
- [x] `create_image` sin `model` idéntico a hoy; con `model` válido; no instalado (con comando de instalación); de otra capacidad; con `workflow`. Ninguno arranca ComfyUI ni toca memoria.
- [x] Lotes con `model` común y por elemento; un elemento inválido rechaza la lista antes de generar.
- [x] LoRAs con `sdxl` y rechazadas con otro modelo; quitar `sdxl` borra las LoRAs.
- [x] Metadatos PNG `ImageHearth-Model`.
- [x] `list_workflows` con uno y varios modelos por capacidad, predeterminado y `loras`.
- [x] `setup` interactivo: selección múltiple por capacidad (nueva sin más marca que la recomendada, existente con las instaladas), precisión con datos medidos, predeterminado, 0 vuelve atrás, `Step N of M` correcto, nada escrito antes de confirmar.
- [x] `--fast-models`, `--quality-models`, `--edit-models` con `nombre[:precisión]`, primero predeterminado, alias `--quality-model`, nombres y precisiones desconocidos.
- [x] Conjunto fijo: añade lo que falta, borra lo que sobra, cambia precisión descargando antes de borrar, no toca capacidades no pasadas ni componentes en uso.
- [x] Resumen de espacio y rechazo cuando no cabe.
- [x] Licencia de Llama 3.1 en el consentimiento al elegir HiDream; no interactivo sin `--accept-licenses` falla.
- [x] `uninstall`, `update --move-to` y `doctor` (también `--json`) con varios modelos y compartidos; archivos ajenos intactos.
- [x] `setup_status` y `setup_start` con las listas nuevas, `quality_model` compatible, listas vacías sin cambios.
- [x] Tests existentes sin cambios de comportamiento; si cambian las secuencias de teclas de `setup` por los pasos nuevos, se ajustan y se anotan aquí. Ningún test toca el `HOME` real ni descarga nada. Ajustes hechos (los 881 tests anteriores pasan con ellos y se añaden los de `tests/test_model_sets.py`, `test_model_choice.py` y `test_model_install.py`):
  - `setup_args` (tests/test_provisioner.py) fija, en modo no interactivo, `fast_models=sdxl-turbo`, `quality_models=flux-dev` y `edit_models=kontext` si el test no dice otra cosa, que era lo que `setup` instalaba por defecto antes; `legacy_models=False` pide el comportamiento nuevo (el modelo recomendado de cada capacidad).
  - Secuencias de teclas de `setup` interactivo (test_setup_steps, test_lora_install, test_install_dir, test_quality_model): el paso del modelo de calidad pasó a selección múltiple, a lo que se añaden los pasos de modelos rápidos, precisión, predeterminado y edición; las pruebas de carpeta y LoRAs fijan `fast_models` para no preguntarlo.
  - `propose_profile`: a 8 GB se propone `full` (FLUX.2 Klein 4B edita en 8 GB); antes `quality`.
  - `list_workflows` devuelve un item por modelo (`model`, `capability`, ... en vez de `name`, `file`, `active`, `quality_model`).
  - Mensajes: `--quality-model` pasa a `--quality-models` en las ayudas y avisos; «no quality model» pasa a «has no high models»; el plan de cambio muestra `+`, `~` y `-` por modelo en vez de «FLUX.1 Dev -> FLUX.1 Schnell».
  - `swap_models` (tests/harness.py) cambia también los pesos del catálogo; `test_config` y `test_provisioner` listan los workflows y pesos nuevos.


## Validaciones manuales

En Linux, por el asistente, con `HOME` temporal y la RTX 4090, **solo con los modelos pequeños**:

- [ ] `setup --profile full --fast-models klein-4b,sdxl-turbo --quality-models chroma-hd:fp8 --edit-models klein-4b`: Klein se descarga una vez; descarga verificada y registrada.
- [ ] Generar con `fast` sin `model` (Klein, predeterminado) y con `model: "sdxl-turbo"`; con `quality: "high"` (Chroma fp8); editar con Klein 4B. PNG con `ImageHearth-Model` correcto.
- [ ] Añadir Z-Image-Turbo int8 con `--fast-models z-image-turbo:int8,klein-4b`: comparte Qwen3-4B; un lote con `model` distinto por elemento en una sola sesión.
- [ ] Quitar un modelo con conjunto fijo: se borra solo lo suyo; los compartidos en uso se conservan; `doctor` lo refleja.
- [ ] `setup` interactivo en un pty real: selección múltiple, precisión con tamaño/tiempo/VRAM, predeterminado y resumen de espacio.
- [ ] Un cliente MCP contra el servidor real: `list_workflows` publica los modelos y `create_image(model=...)` los usa; errores de `model` antes de tocar la GPU.
- [ ] `uninstall`: no queda nada registrado.

En Linux, por el usuario, con los modelos grandes:

- [ ] **Usuario:** Z-Image-Turbo bf16, Chroma1-HD bf16, Qwen-Image (Q2_K, Q4_K_M, fp8, bf16), HiDream-I1 Full (Q4_K_M y fp8, con la licencia de Llama) y Qwen-Image-Edit-2511 (Q4_K_M y fp8): instalar, generar o editar, cambiar de precisión y quitar.

Con `HOME` temporal para no tocar tu instalación (`export HOME=$(mktemp -d)`), una tanda por modelo grande. `<modelo>` es el nombre del catálogo y `<precisión>` una de las ofrecidas:

```bash
# Instalar (HiDream muestra la licencia de Llama y necesita --accept-licenses)
imagehearth-mcp setup --profile quality --fast-models klein-4b --quality-models <modelo>:<precisión> --accept-licenses --non-interactive --managed
# Generar: PNG con ImageHearth-Model = <modelo>:<precisión>
imagehearth-mcp doctor
# Desde el agente: list_workflows y create_image(prompt="...", quality="high", model="<modelo>")
# Cambiar de precisión (descarga la nueva y borra la anterior) y quitar el modelo
imagehearth-mcp setup --profile quality --quality-models <modelo>:<otra> --yes --accept-licenses --non-interactive
imagehearth-mcp setup --profile quality --quality-models sdxl --yes --accept-licenses --non-interactive
```

Para edición: `--profile full --edit-models qwen-image-edit:<q4_k_m|fp8>` y `create_image(prompt="...", image_paths=["foto.png"], model="qwen-image-edit")`. Modelos y precisiones a probar: `z-image-turbo:bf16`, `chroma-hd:bf16`, `qwen-image:{q2_k,q4_k_m,fp8,bf16}`, `hidream-full:{q4_k_m,fp8}` y `qwen-image-edit:{q4_k_m,fp8}`.

En Windows:

- [ ] **Mantenedor (opcional):** `setup` con varios modelos, generar con `model` y `uninstall`, en PowerShell.

## Lista para fusionar

- [x] `scripts/check.sh` en verde en Linux.
- [x] `scripts/contract.sh` en verde.
- [x] Validaciones manuales del asistente completadas, salvo `setup` interactivo en un pty real y un cliente MCP real.
- [ ] **Usuario:** pruebas con los modelos grandes.
- [x] `README.md`, `README.es.md`, `llms-install.md`, `THIRD_PARTY_NOTICES.md`, skill e instrucciones del servidor actualizados.
- [ ] Roadmap con la fase 15 actualizada (varios modelos por capacidad y `model`), tareas marcadas y fase completada.
- [ ] Cambios revisados por el usuario, que realiza el commit.

## Evidencia

| Comprobación | Resultado | Fecha |
|---|---|---|
| `scripts/check.sh` | **Verde**: `ruff`, 1008 tests y los mismos tests contra el wheel instalado | 2026-11-16 |
| `scripts/contract.sh` | **Verde** contra ComfyUI 0.43.0 (el de las mediciones, con su `.venv` enlazado como `venv`): los 37 tipos de nodo y las entradas de los 19 workflows existen | 2026-11-16 |
| Instalación de modelos pequeños con componentes compartidos | **Real, RTX 4090, `HOME` temporal**: `setup --profile full --fast-models klein-4b,sdxl-turbo --quality-models chroma-hd:fp8 --edit-models klein-4b` (Klein una sola vez; codificadores compartidos reutilizados); después `--fast-models klein-4b,z-image-turbo:int8,sdxl-turbo` añade Z-Image int8 y su codificador fp8 sin tocar lo demás | 2026-11-17 |
| Generación y edición con `model` y predeterminado | **Real**: sin `model` Klein (predeterminado), `model=sdxl-turbo`, `quality=high` (Chroma fp8), edición con Klein 4B y lote con `model` distinto por elemento en una sesión; PNG con `ImageHearth-Model` correcto (`klein-4b:bf16`, `sdxl-turbo:fp16`, `chroma-hd:fp8`) y workflow esperado; imágenes revisadas a ojo. Errores de `model` (desconocido, otra capacidad, no instalado, con `workflow`) antes de tocar la GPU | 2026-11-17 |
| Conjunto fijo y `doctor` | **Real**: quitar `sdxl-turbo` sin `--yes` se rechaza; con `--yes` se borra solo su archivo y se conservan los compartidos; `doctor` lista los modelos por capacidad | 2026-11-17 |
| `setup` interactivo en pty | Con teclas inyectadas en tests: verde. En un pty real: **pendiente** | 2026-11-16 |
| Cliente MCP | Esquema de herramientas y llamadas a `list_workflows`/`create_image` en tests: verde. Contra el servidor real: **pendiente** | 2026-11-16 |
| `uninstall` | **Real**: no queda ningún peso descargado; solo los archivos que ya estaban (los codificadores que dejé antes) | 2026-11-17 |
| Modelos grandes (usuario) | Pendiente | — |
| Windows (mantenedor) | Pendiente | — |
