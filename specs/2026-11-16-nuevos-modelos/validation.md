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

- [ ] Catálogo por capacidad válido y rechazos: nombre repetido, capacidad desconocida, precisión repetida, workflow o peso inexistente, licencia ausente.
- [ ] `Manifest.resolve` con varios modelos por capacidad; componentes compartidos deduplicados (Klein en `fast` y edición, Qwen3-4B, T5/VAE con Chroma).
- [ ] Migración de manifiestos de instalación de las fases 9–13 sin descargas ni borrados, con predeterminados correctos.
- [ ] Workflow de cada modelo y precisión nuevos: nodos, conexiones y marcadores rellenos (prompt, negativo, tamaño, semilla e imágenes en edición).
- [ ] `create_image` sin `model` idéntico a hoy; con `model` válido; no instalado (con comando de instalación); de otra capacidad; con `workflow`. Ninguno arranca ComfyUI ni toca memoria.
- [ ] Lotes con `model` común y por elemento; un elemento inválido rechaza la lista antes de generar.
- [ ] LoRAs con `sdxl` y rechazadas con otro modelo; quitar `sdxl` borra las LoRAs.
- [ ] Metadatos PNG `ImageHearth-Model`.
- [ ] `list_workflows` con uno y varios modelos por capacidad, predeterminado y `loras`.
- [ ] `setup` interactivo: selección múltiple por capacidad (nueva sin más marca que la recomendada, existente con las instaladas), precisión con datos medidos, predeterminado, 0 vuelve atrás, `Step N of M` correcto, nada escrito antes de confirmar.
- [ ] `--fast-models`, `--quality-models`, `--edit-models` con `nombre[:precisión]`, primero predeterminado, alias `--quality-model`, nombres y precisiones desconocidos.
- [ ] Conjunto fijo: añade lo que falta, borra lo que sobra, cambia precisión descargando antes de borrar, no toca capacidades no pasadas ni componentes en uso.
- [ ] Resumen de espacio y rechazo cuando no cabe.
- [ ] Licencia de Llama 3.1 en el consentimiento al elegir HiDream; no interactivo sin `--accept-licenses` falla.
- [ ] `uninstall`, `update --move-to` y `doctor` (también `--json`) con varios modelos y compartidos; archivos ajenos intactos.
- [ ] `setup_status` y `setup_start` con las listas nuevas, `quality_model` compatible, listas vacías sin cambios.
- [ ] Tests existentes sin cambios de comportamiento; si cambian las secuencias de teclas de `setup` por los pasos nuevos, se ajustan y se anotan aquí. Ningún test toca el `HOME` real ni descarga nada.

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

En Windows:

- [ ] **Mantenedor (opcional):** `setup` con varios modelos, generar con `model` y `uninstall`, en PowerShell.

## Lista para fusionar

- [ ] `scripts/check.sh` en verde en Linux.
- [ ] `scripts/contract.sh` en verde.
- [ ] Validaciones manuales del asistente completadas.
- [ ] **Usuario:** pruebas con los modelos grandes.
- [ ] `README.md`, `README.es.md`, `llms-install.md`, `THIRD_PARTY_NOTICES.md`, skill e instrucciones del servidor actualizados.
- [ ] Roadmap con la fase 15 actualizada (varios modelos por capacidad y `model`), tareas marcadas y fase completada.
- [ ] Cambios revisados por el usuario, que realiza el commit.

## Evidencia

| Comprobación | Resultado | Fecha |
|---|---|---|
| `scripts/check.sh` | Pendiente | — |
| `scripts/contract.sh` | Pendiente | — |
| Instalación de modelos pequeños con componentes compartidos | Pendiente | — |
| Generación y edición con `model` y predeterminado | Pendiente | — |
| Conjunto fijo y `doctor` | Pendiente | — |
| `setup` interactivo en pty | Pendiente | — |
| Cliente MCP | Pendiente | — |
| `uninstall` | Pendiente | — |
| Modelos grandes (usuario) | Pendiente | — |
| Windows (mantenedor) | Pendiente | — |
