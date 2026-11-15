# Validación: Fase 13

Una sola puerta: la rama no se fusiona hasta que estén en verde los tests simulados, `scripts/check.sh`, la prueba de contrato y las pruebas reales en Linux, y el mantenedor haya hecho la de Windows.

## Criterios de finalización

- El catálogo tiene entre 6 y 10 LoRAs de SDXL 1.0 con licencia de uso comercial, y la elección está documentada en [selección de LoRAs](seleccion-loras.md).
- Con SDXL 1.0 instalado, un agente lista las LoRAs con `list_workflows` y genera una imagen con una de ellas sin ayuda.
- Las LoRAs se instalan y se quitan con `setup` (interactivo y `--loras`) y con `setup_start`, y se borran con `uninstall` y al cambiar a FLUX.
- Pedir una LoRA con FLUX, con `fast`, en una edición o con un nombre no instalado da un error claro antes de tocar la GPU.
- Sin `loras`, la generación y los workflows son idénticos a los de hoy, y `setup` sin `--loras` no cambia las LoRAs.
- El PNG generado con LoRAs lleva `ImageHearth-LoRAs` con nombres y pesos.
- El README muestra cada LoRA con su categoría, licencia y ejemplo con y sin LoRA.

## Validaciones automáticas

Desde la raíz del repositorio, en Linux:

```bash
scripts/check.sh
```

Ejecuta `uv sync --locked`, `ruff`, `pytest` y los tests contra el wheel instalado en un entorno aparte. Es la puerta de calidad obligatoria de [tech-stack](../tech-stack.md).

```bash
scripts/contract.sh
```

Prueba de contrato: esta fase cambia cómo se construye el workflow `sdxl_base`, así que se ejecuta aunque no añada tipos de nodo.

Los tests deben cubrir:

- [x] Catálogo `[[loras]]` válido y rechazos: nombre repetido, `dest` fuera de `loras/`, peso fuera de rango, campo obligatorio ausente.
- [x] Workflow con 0 LoRAs idéntico al actual; con 1 y 3 LoRAs, nodos `LoraLoader` encadenados tras la de detalle y conexiones de `CLIPTextEncode` y muestreador correctas.
- [x] Rechazos: 4 LoRAs, nombre repetido, peso fuera de 0–2, nombre desconocido, nombre del catálogo no instalado (con el comando para instalarlo), FLUX, `fast`, edición, RealVisXL `legacy`. Ninguno arranca ComfyUI ni toca memoria.
- [x] Parámetro como nombre y como objeto con peso; peso recomendado por defecto.
- [x] Lotes: LoRAs distintas por elemento, `loras` común, elemento inválido rechaza la lista antes de generar.
- [x] Palabras de activación añadidas solo si faltan; `style: "auto"` sin pistas fotográficas con LoRAs de otro medio.
- [x] Metadatos PNG `ImageHearth-LoRAs`.
- [x] `list_workflows` con LoRAs instaladas, sin ninguna y con FLUX activo.
- [x] `setup --loras` con lista, `all`, `none`, nombre desconocido y con FLUX; paso interactivo en instalación nueva (sin marcar) y existente (marcadas), 0 vuelve, `Step N of M` correcto; nada escrito antes de confirmar.
- [x] Conjunto fijo sobre una instalación existente: añade las que faltan y borra las que sobran; sin `--loras` no cambia nada.
- [x] Cambio de SDXL 1.0 a FLUX borra las LoRAs y el resumen lo dice.
- [x] `uninstall` y `update --move-to` tratan las LoRAs registradas; un archivo ajeno en `models/loras` no se toca.
- [x] `doctor` lista las LoRAs y avisa si falta o no coincide una, también en `--json`.
- [x] `setup_status` con catálogo e instaladas; `setup_start` con lista válida, `["all"]`, vacía, nombre desconocido y con FLUX.
- [x] Tests existentes sin cambios de comportamiento; ningún test toca el `HOME` real ni descarga nada. Si `setup` interactivo gana el paso `LoRAs` al elegir SDXL, se ajustan las secuencias de teclas afectadas y se anota aquí. **Anotado:** con SDXL 1.0 hay un paso más (`LoRAs`, tras el modelo), así que se ajustaron las teclas y los «Step N of M» de `test_setup_steps.py::test_full_run_only_with_keys`, `test_zero_goes_back_and_keeps_answers`, `test_profile_without_quality_removes_the_model_step`, `test_zero_from_every_step_goes_back_one_at_a_time` y `test_quality_model_argument_hides_its_step`, y de `test_quality_model.py::test_interactive_choice_shows_size_vram_license_and_recommendation`, `test_interactive_switch_declined_changes_nothing` y `test_interactive_switch_confirmed`. El resto no cambia. Los tests nuevos están en `tests/test_loras.py`, `tests/test_lora_install.py` y al final de `tests/test_batch.py`.

## Validaciones manuales

En Linux, por el asistente, con `HOME` temporal y la RTX 4090:

- [x] Medición de candidatas con `scripts/measure_loras.py` y elección documentada en `seleccion-loras.md`.
- [x] `setup --profile quality --quality-model sdxl --loras all`: descarga verificada y registrada.
- [x] Cada LoRA del catálogo genera con el mismo prompt y semilla; la imagen cambia de forma visible respecto a la de sin LoRA; metadatos PNG correctos.
- [x] `setup` interactivo en un pty real: la selección múltiple muestra categoría, tamaño y licencia.
- [x] `setup --loras a,b` sobre la instalación: añade y borra lo esperado; `doctor` lo refleja.
- [x] Cambio a FLUX Schnell con `setup`: las LoRAs se borran.
- [ ] Un agente (y un modelo local pequeño si está disponible) usa `list_workflows` y `create_image` con la LoRA adecuada a un estilo pedido, sin ayuda. **Pendiente:** solo se comprobó con un cliente MCP escrito a mano (instrucciones, esquema de `loras` en `create_image` y `setup_start`, salida de `list_workflows`, error con `fast`); falta una prueba con un agente de verdad.
- [x] Pedir una LoRA con FLUX o con `fast` da error antes de tocar la GPU.
- [x] `uninstall`: no queda ninguna LoRA del catálogo.
- [x] Imágenes de ejemplo en `docs/images/loras/` de menos de 100 KB cada una.

En Windows:

- [ ] **Mantenedor:** `setup` con `--loras`, generar con una LoRA y `uninstall`, en PowerShell.

## Lista para fusionar

- [x] `scripts/check.sh` en verde en Linux.
- [x] `scripts/contract.sh` en verde.
- [ ] Validaciones manuales en Linux completadas. Falta solo la prueba con un agente de verdad (ver arriba).
- [ ] **Mantenedor:** validación en Windows.
- [x] `README.md`, `README.es.md`, `llms-install.md`, `THIRD_PARTY_NOTICES.md`, skill e instrucciones del servidor actualizados.
- [x] `seleccion-loras.md` completo.
- [ ] Roadmap con las tareas hechas marcadas y la fase como completada.
- [ ] Cambios revisados por el usuario, que realiza el commit.

## Evidencia

| Comprobación | Resultado | Fecha |
|---|---|---|
| Selección de LoRAs medida | Hecho: 18 candidatas medidas con los mismos 3 prompts y semilla (sin LoRA, mismo texto sin LoRA, peso recomendado y la mitad), 10 elegidas. Hojas y mediciones en [comparison/](comparison/); decisión en [seleccion-loras.md](seleccion-loras.md). Dos candidatas (`old-book`, `anime-cel-shaded`) no cargan en ComfyUI (diferencia 0,0 respecto al control) | 2026-11-15 |
| `scripts/check.sh` | 850 tests y `ruff` en verde, y 850 tests contra el wheel instalado | 2026-11-15 |
| `scripts/contract.sh` | En verde (se ejecutó `scripts/contract.py`, que es lo que lanza `contract.sh`) con ComfyUI 0.43.0 en CPU: 20 tipos de nodo y los 5 inputs de la cadena `sdxl_base` con 3 LoRAs encadenadas (comprobación nueva en `scripts/contract.py`) | 2026-11-15 |
| `setup --loras all` y generación de cada LoRA | `setup --profile quality --quality-model sdxl --loras all` con `HOME` temporal (primero con 10 candidatas y después, de forma incremental, con 16 y 18): descarga verificada por SHA-256 y registrada (también un archivo con espacios en el nombre). Un lote de 10 imágenes con una LoRA distinta cada una en una sola sesión, mismo prompt: 10 PNG con `ImageHearth-LoRAs` (`nombre:peso`) y `ImageHearth-Workflow` correctos. Las imágenes con semilla fija de cada una están en las hojas de contacto | 2026-11-15 |
| Añadir y quitar con `setup --loras`; `doctor` | Sobre la instalación anterior, `--loras pixel-art,papercut` mostró qué se borraba y borró el resto; `doctor` lista `LoRAs: pixel-art, papercut` (y en `--json`, en `details.loras` de `models`). El paso interactivo se vio en un pty real: categoría, tamaño y licencia, con las instaladas marcadas | 2026-11-15 |
| Cambio a FLUX borra las LoRAs | `setup --quality-model flux-schnell --yes` desde SDXL 1.0: el resumen listó `pixel-art-xl.safetensors (LoRA)` y `papercut-sdxl.safetensors (LoRA)` bajo «To delete afterwards», se borraron tras verificar FLUX y `doctor` quedó en verde | 2026-11-15 |
| Agente sin ayuda | **Pendiente.** Con un cliente MCP escrito a mano contra el servidor real: las instrucciones traen el apartado de estilos, `create_image` y `setup_start` tienen `loras`, `list_workflows` da el item `sdxl_base` con sus `loras` (551 caracteres con 2 instaladas) y `setup_status` el catálogo. No se ha probado con un agente ni un modelo local | 2026-11-15 |
| Errores antes de tocar la GPU | Con SDXL 1.0 (`fast`, nombre desconocido, repetida, 4 LoRAs) y con FLUX Schnell instalado: error en 0,0–0,02 s, sin arrancar ComfyUI. Además, los tests comprueban que ComfyUI y Ollama no reciben ninguna petición | 2026-11-15 |
| `uninstall` | `uninstall --yes --remove-models` quitó ComfyUI y la carpeta `models/loras` (tras el cambio a FLUX ya no había LoRAs del catálogo); con LoRAs del catálogo instaladas lo cubre `test_uninstall_removes_the_loras_and_keeps_foreign_files`, que además comprueba que un archivo ajeno se conserva | 2026-11-15 |
| Windows | Pendiente: lo hace el mantenedor | — |
