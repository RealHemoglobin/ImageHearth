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

- [ ] Combinaciones perfil-modelo: modelos, nodos y licencias resueltos para `quality` y `full` con cada modelo y cada variante de precisión.
- [ ] `full` con `sdxl` incluye T5, CLIP-L y el VAE de FLUX por Kontext.
- [ ] `quality` con `flux-schnell` o `sdxl` sin licencia `flux-dev-non-commercial`.
- [ ] Recomendación por tramos de VRAM y advertencia para un modelo que no cabe.
- [ ] `--quality-model` y pregunta interactiva; sin valor, recomendación anunciada en la salida.
- [ ] La elección se registra en el manifiesto de instalación.
- [ ] El catálogo usa el workflow del modelo instalado.
- [ ] `doctor` (también `--json`), `get_engine_status` y `list_workflows` con modelo y licencia.
- [ ] Metadatos del PNG con modelo y workflow.
- [ ] Migración de registros antiguos con FLUX Dev, FLUX Dev GGUF y RealVisXL; RealVisXL preexistente no se borra.
- [ ] El cambio descarga y verifica antes de borrar.
- [ ] Un fallo a mitad deja el modelo anterior funcionando y el registro sin cambiar; repetir continúa.
- [ ] Archivos compartidos con Kontext o con el modelo nuevo conservados.
- [ ] Modelos preexistentes y del modo adjunto nunca borrados.
- [ ] Espacio comprobado con ambos modelos conviviendo.
- [ ] Cambio rechazado con una generación en curso; ComfyUI gestionado reiniciado.
- [ ] `setup_status` con la lista de modelos y `setup_start` con `quality_model` y advertencia.

## Validaciones manuales (RTX 4090 en Linux)

- [ ] Comparación del refiner de SDXL con los mismos prompts y semillas; decisión anotada en la evidencia.
- [ ] Mismo prompt y semilla con `flux-dev`, `flux-schnell` y `sdxl`, cambiando con `setup`; tiempos y pico de VRAM anotados.
- [ ] Ciclo `flux-dev` → `flux-schnell` → `sdxl` → `flux-dev` en `full`: Kontext funciona tras cada cambio y el disco usado vuelve al de partida.
- [ ] Cambio interrumpido durante la descarga: se sigue generando con el modelo anterior; repetir el comando lo termina.
- [ ] Schnell fp8 con 12 GB de VRAM medido; umbral de la recomendación fijado (y GGUF añadido si hizo falta).
- [ ] Instalación `quality` con Schnell y con SDXL sin archivos de licencia no comercial de FLUX.
- [ ] `setup` interactivo muestra tamaño, VRAM, licencia, uso comercial, recomendada y advertencias.
- [ ] Instalación anterior con FLUX Dev actualizada a la rama: sigue generando y `doctor` muestra `flux-dev`.
- [ ] **Mantenedor:** desde Claude Code, `setup_status` y `setup_start` presentan modelo, licencia y advertencias y el agente deja elegir.
- [ ] Comparativa de los tres modelos en `README.md` y `README.es.md`.

## Lista para fusionar

- [ ] `scripts/check.sh` en verde en Linux.
- [ ] Prueba de contrato `/object_info` en verde con los workflows nuevos.
- [ ] Validaciones manuales completadas.
- [ ] Instrucciones del servidor MCP, skill `imagehearth`, mensajes de "no instalado", `tech-stack.md`, `docs/troubleshooting.md` y `THIRD_PARTY_NOTICES.md` actualizados.
- [ ] README con la tabla, la comparativa y cómo cambiar de modelo.
- [ ] Roadmap con las tareas hechas marcadas y la fase como completada.
- [ ] Cambios revisados por el usuario, que realiza el commit.

## Evidencia

| Comprobación | Resultado | Fecha |
|---|---|---|
| `scripts/check.sh` en Linux | | |
| Prueba de contrato `/object_info` | | |
| Refiner de SDXL | | |
| Comparativa de los tres modelos | | |
| Ciclo de cambios en `full` | | |
| Cambio interrumpido | | |
| Schnell con 12 GB | | |
| Licencias de una instalación comercial | | |
| Migración de una instalación anterior | | |
| Agente real con `setup_start` | | |
