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

- [ ] Catálogo `[[loras]]` válido y rechazos: nombre repetido, `dest` fuera de `loras/`, peso fuera de rango, campo obligatorio ausente.
- [ ] Workflow con 0 LoRAs idéntico al actual; con 1 y 3 LoRAs, nodos `LoraLoader` encadenados tras la de detalle y conexiones de `CLIPTextEncode` y muestreador correctas.
- [ ] Rechazos: 4 LoRAs, nombre repetido, peso fuera de 0–2, nombre desconocido, nombre del catálogo no instalado (con el comando para instalarlo), FLUX, `fast`, edición, RealVisXL `legacy`. Ninguno arranca ComfyUI ni toca memoria.
- [ ] Parámetro como nombre y como objeto con peso; peso recomendado por defecto.
- [ ] Lotes: LoRAs distintas por elemento, `loras` común, elemento inválido rechaza la lista antes de generar.
- [ ] Palabras de activación añadidas solo si faltan; `style: "auto"` sin pistas fotográficas con LoRAs de otro medio.
- [ ] Metadatos PNG `ImageHearth-LoRAs`.
- [ ] `list_workflows` con LoRAs instaladas, sin ninguna y con FLUX activo.
- [ ] `setup --loras` con lista, `all`, `none`, nombre desconocido y con FLUX; paso interactivo en instalación nueva (sin marcar) y existente (marcadas), 0 vuelve, `Step N of M` correcto; nada escrito antes de confirmar.
- [ ] Conjunto fijo sobre una instalación existente: añade las que faltan y borra las que sobran; sin `--loras` no cambia nada.
- [ ] Cambio de SDXL 1.0 a FLUX borra las LoRAs y el resumen lo dice.
- [ ] `uninstall` y `update --move-to` tratan las LoRAs registradas; un archivo ajeno en `models/loras` no se toca.
- [ ] `doctor` lista las LoRAs y avisa si falta o no coincide una, también en `--json`.
- [ ] `setup_status` con catálogo e instaladas; `setup_start` con lista válida, `["all"]`, vacía, nombre desconocido y con FLUX.
- [ ] Tests existentes sin cambios de comportamiento; ningún test toca el `HOME` real ni descarga nada. Si `setup` interactivo gana el paso `LoRAs` al elegir SDXL, se ajustan las secuencias de teclas afectadas y se anota aquí.

## Validaciones manuales

En Linux, por el asistente, con `HOME` temporal y la RTX 4090:

- [ ] Medición de candidatas con `scripts/measure_loras.py` y elección documentada en `seleccion-loras.md`.
- [ ] `setup --profile quality --quality-model sdxl --loras all`: descarga verificada y registrada.
- [ ] Cada LoRA del catálogo genera con el mismo prompt y semilla; la imagen cambia de forma visible respecto a la de sin LoRA; metadatos PNG correctos.
- [ ] `setup` interactivo en un pty real: la selección múltiple muestra categoría, tamaño y licencia.
- [ ] `setup --loras a,b` sobre la instalación: añade y borra lo esperado; `doctor` lo refleja.
- [ ] Cambio a FLUX Schnell con `setup`: las LoRAs se borran.
- [ ] Un agente (y un modelo local pequeño si está disponible) usa `list_workflows` y `create_image` con la LoRA adecuada a un estilo pedido, sin ayuda.
- [ ] Pedir una LoRA con FLUX o con `fast` da error antes de tocar la GPU.
- [ ] `uninstall`: no queda ninguna LoRA del catálogo.
- [ ] Imágenes de ejemplo en `docs/images/loras/` de menos de 100 KB cada una.

En Windows:

- [ ] **Mantenedor:** `setup` con `--loras`, generar con una LoRA y `uninstall`, en PowerShell.

## Lista para fusionar

- [ ] `scripts/check.sh` en verde en Linux.
- [ ] `scripts/contract.sh` en verde.
- [ ] Validaciones manuales en Linux completadas.
- [ ] **Mantenedor:** validación en Windows.
- [ ] `README.md`, `README.es.md`, `llms-install.md`, `THIRD_PARTY_NOTICES.md`, skill e instrucciones del servidor actualizados.
- [ ] `seleccion-loras.md` completo.
- [ ] Roadmap con las tareas hechas marcadas y la fase como completada.
- [ ] Cambios revisados por el usuario, que realiza el commit.

## Evidencia

| Comprobación | Resultado | Fecha |
|---|---|---|
| Selección de LoRAs medida | Pendiente | — |
| `scripts/check.sh` | Pendiente | — |
| `scripts/contract.sh` | Pendiente | — |
| `setup --loras all` y generación de cada LoRA | Pendiente | — |
| Añadir y quitar con `setup --loras`; `doctor` | Pendiente | — |
| Cambio a FLUX borra las LoRAs | Pendiente | — |
| Agente sin ayuda | Pendiente | — |
| Errores antes de tocar la GPU | Pendiente | — |
| `uninstall` | Pendiente | — |
| Windows | Pendiente: lo hace el mantenedor | — |
