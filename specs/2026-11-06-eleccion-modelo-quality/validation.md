# Validación: Fase 9

Una sola puerta: la rama no se fusiona hasta que estén en verde los tests simulados, las comprobaciones locales, las pruebas reales en la RTX 4090 y la comparativa del README.

## Criterios de finalización

- Instalar `quality` o `full` permite elegir entre FLUX.1 Dev, FLUX.1 Schnell y SDXL 1.0, mostrando tamaño, VRAM mínima, licencia y uso comercial antes de descargar, tanto en la CLI como desde un agente con `setup_start`.
- La recomendación sigue la VRAM y el usuario puede instalar cualquiera de los tres; uno que no cabe se instala con una advertencia que da el mínimo medido y la memoria detectada.
- `imagehearth-mcp setup` cambia el modelo de `quality`, libera el espacio del anterior y, en `full`, la edición con Kontext sigue funcionando.
- Un cambio interrumpido deja el sistema generando con el modelo anterior y repetir el comando lo termina.
- Una instalación `quality` con Schnell o SDXL no incluye ningún componente con licencia no comercial de FLUX, y el consentimiento no la muestra.
- `list_workflows`, `get_engine_status` y `doctor` muestran el modelo activo y su licencia; cada PNG lleva modelo y workflow en sus metadatos.
- Las instalaciones anteriores (FLUX Dev fp8, FLUX Dev GGUF, RealVisXL) siguen generando tras actualizar y `setup` las lleva al esquema nuevo.
- El README contiene la tabla y la comparativa de los tres modelos con los mismos prompts y semillas.

## Validaciones automáticas

Desde la raíz del repositorio, en Linux:

```bash
scripts/check.sh
```

Ejecuta `uv sync --locked`, `ruff`, `pytest` y los tests contra el wheel instalado en un entorno aparte.

```bash
scripts/contract.sh
```

Prueba de contrato con `/object_info`; debe incluir `flux_schnell` y `sdxl_base`.

La puerta de calidad obligatoria de [tech-stack](../tech-stack.md) es `scripts/check.sh` más la prueba de contrato.

Los tests deben cubrir:

- [x] Combinaciones perfil-modelo: modelos, nodos y licencias resueltos para `quality` y `full` con cada modelo y cada variante de precisión.
- [x] `full` con `sdxl` incluye T5, CLIP-L y el VAE de FLUX por Kontext.
- [x] `quality` con `flux-schnell` o `sdxl` sin licencia `flux-dev-non-commercial`.
- [x] Recomendación por tramos de VRAM y advertencia para un modelo que no cabe.
- [x] `--quality-model` y pregunta interactiva; sin valor, recomendación anunciada en la salida.
- [x] La elección se registra en el manifiesto de instalación.
- [x] El catálogo usa el workflow del modelo instalado.
- [x] `doctor` (también `--json`), `get_engine_status` y `list_workflows` con modelo y licencia.
- [x] Metadatos del PNG con modelo y workflow.
- [x] Migración de registros antiguos con FLUX Dev, FLUX Dev GGUF y RealVisXL; RealVisXL preexistente no se borra.
- [x] El cambio descarga y verifica antes de borrar.
- [x] Un fallo a mitad deja el modelo anterior funcionando y el registro sin cambiar; repetir continúa.
- [x] Archivos compartidos con Kontext o con el modelo nuevo conservados.
- [x] Modelos preexistentes y del modo adjunto nunca borrados.
- [x] Espacio comprobado con ambos modelos conviviendo.
- [x] Cambio rechazado con una generación en curso; ComfyUI gestionado reiniciado.
- [x] `setup_status` con la lista de modelos y `setup_start` con `quality_model` y advertencia.

## Validaciones manuales (RTX 4090 en Linux)

- [x] Comparación del refiner de SDXL con los mismos prompts y semillas; decisión anotada en la evidencia.
- [x] Mismo prompt y semilla con `flux-dev`, `flux-schnell` y `sdxl`, cambiando con `setup`; tiempos y pico de VRAM anotados.
- [x] Ciclo `flux-dev` → `flux-schnell` → `sdxl` → `flux-dev` en `full`: Kontext funciona tras cada cambio y el disco usado vuelve al de partida.
- [x] Cambio interrumpido durante la descarga: se sigue generando con el modelo anterior; repetir el comando lo termina.
- [x] Schnell fp8 con 12 GB de VRAM medido (simulado con `--reserve-vram 12` en la 4090, no en una tarjeta de 12 GB real); umbral de 12 GB mantenido, sin GGUF de Schnell.
- [x] Instalación `quality` con Schnell y con SDXL sin archivos de licencia no comercial de FLUX (comprobado sobre el manifiesto real en los tests; en la máquina solo había un `full`, que incluye Kontext).
- [ ] `setup` interactivo muestra tamaño, VRAM, licencia, uso comercial, recomendada y advertencias.
- [x] Instalación anterior con FLUX Dev actualizada a la rama: sigue generando y `doctor` muestra `flux-dev`.
- [ ] **Mantenedor:** desde Claude Code, `setup_status` y `setup_start` presentan modelo, licencia y advertencias y el agente deja elegir.
- [x] Comparativa de los tres modelos en `README.md` y `README.es.md`.

## Lista para fusionar

- [x] `scripts/check.sh` en verde en Linux.
- [x] Prueba de contrato `/object_info` en verde con los workflows nuevos.
- [ ] Validaciones manuales completadas (faltan `setup` interactivo comprobado a mano y el agente real, del mantenedor).
- [x] Instrucciones del servidor MCP, skill `imagehearth`, mensajes de "no instalado", `tech-stack.md`, `docs/troubleshooting.md` y `THIRD_PARTY_NOTICES.md` actualizados.
- [ ] README con la tabla, la comparativa y cómo cambiar de modelo.
- [ ] Roadmap con las tareas hechas marcadas y la fase como completada.
- [ ] Cambios revisados por el usuario, que realiza el commit.

## Evidencia

| Comprobación | Resultado | Fecha |
|---|---|---|
| `scripts/check.sh` en Linux | 509 tests en verde, en el repositorio y contra el wheel | 2026-11-06 |
| Prueba de contrato `/object_info` | OK: 20 tipos de nodo, con `flux_schnell` y `sdxl_base` | 2026-11-06 |
| Refiner de SDXL | Sin mejora visible (mismas 3 imágenes, misma semilla; `comparison/refiner-grid.jpg`). No se incluye y se retira la entrada del manifiesto | 2026-11-06 |
| Comparativa de los tres modelos | `comparison/grid.jpg`. Pico de VRAM / primera / siguientes: FLUX Dev 19,4 GB / 12,8 s / 10,3 s; Schnell 19,4 GB / 5,2 s / 2,8 s; SDXL 9,6 GB / 5,7 s / 4,0 s (`measurements/*.json`) | 2026-11-06 |
| Ciclo de cambios en `full` | dev → schnell → sdxl → dev: Kontext OK tras cada cambio; disco 36.483.150.072 B antes y después, idéntico | 2026-11-06 |
| Cambio interrumpido | SIGINT a 0,6 GB de SDXL: `doctor` y generación con Schnell intactos, registro sin cambiar; al repetir, «Resuming from 0.6 GB» y termina | 2026-11-06 |
| Schnell con 12 GB | `--reserve-vram 12`: pico 12,3 GB, 2,8 s por imagen; con 14: 10,2 GB y 2,8 s. Simulado, no en una tarjeta de 12 GB real | 2026-11-06 |
| Licencias de una instalación comercial | Tests sobre el manifiesto real: `quality` con Schnell o SDXL sin `flux-dev-non-commercial`; con `full` solo por Kontext | 2026-11-06 |
| Migración de una instalación anterior | La instalación real (registro anterior, FLUX Dev fp8) se dedujo como `flux-dev` y siguió generando; PNG real con `ImageHearth-Quality-Model: flux-dev` | 2026-11-06 |
| Agente real con `setup_start` | | |
