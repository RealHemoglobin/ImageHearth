# Fase 9: Elección del modelo de `quality`

## Contexto

Fase 9 del [roadmap](../roadmap.md), cuyo objetivo es que al instalar `quality` o `full` el usuario elija el modelo de generación de calidad entre FLUX.1 Dev, FLUX.1 Schnell y SDXL 1.0, y que después pueda cambiarlo con `imagehearth-mcp setup`, que borra el anterior. Depende de las fases 3 y 7.

FLUX.1 Dev y FLUX.1 Kontext Dev tienen licencia no comercial; FLUX.1 Schnell (Apache-2.0) y SDXL 1.0 (OpenRAIL++) permiten uso comercial. `fast` sigue con SDXL Turbo y la edición con Kontext: solo cambia el modelo de `quality`, y solo hay uno instalado a la vez.

Estado de partida, comprobado el 2026-11-06:

- `data/models.toml` define los perfiles `quality`, `full` y sus variantes por VRAM (`quality-gguf`, `quality-sdxl`, `full-gguf`, con `variant_of`). `quality-sdxl` usa RealVisXL V5.0 con la LoRA de detalle `sdxl_offset_lora`, que ya viene del repositorio de SDXL 1.0 base.
- `provisioner/manifest.py` (`Manifest.resolve`, `variants_of`, `licenses_for`) elige la variante según la VRAM; `provisioner/setup.py` (`propose_profile`, `choose_profile`, `require_acceptance`) la propone y pide el consentimiento.
- `provisioner/install_manifest.py` registra lo que instaló ImageHearth (`claim`, `note_preexisting`, `is_owned`, `owned`, `forget`); `provisioner/maintenance.py` ya borra modelos propios en `uninstall`.
- `engine/catalog.py` tiene `VARIANTS["high"] = ("flux_dev", "flux_dev_gguf", "sdxl_quality")` y usa el que esté instalado.
- Workflows en `data/workflows/`: `flux_dev`, `flux_dev_gguf`, `sdxl_quality` (RealVisXL), `sdxl_turbo` y los dos de Kontext.
- `server.py` expone `setup_status`, `setup_start(profile, accept_licenses, existing_comfyui)`, `list_workflows` y `get_engine_status`. `create_image` acepta un prompt o una lista (fase 8).
- No se escriben metadatos propios en los PNG.

## Alcance

Todo lo del roadmap para la fase 9 en una sola rama:

1. **Catálogo y manifiesto:** separar perfil y modelo de `quality`; añadir FLUX.1 Schnell y SDXL 1.0 base (con refiner si la comparación lo justifica); retirar RealVisXL; registrar el modelo elegido.
2. **Workflows:** `flux_schnell` y `sdxl_base`, en `VARIANTS["high"]`; el modelo activo y su licencia visibles en `list_workflows`, `get_engine_status` y `doctor`; modelo y workflow en los metadatos del PNG.
3. **Instalación:** pregunta interactiva, `--quality-model`, `setup_status` y `setup_start(quality_model)`, consentimiento solo de las licencias que se descargan.
4. **Cambio de modelo:** `setup` sobre una instalación existente, descargando antes de borrar y conservando lo compartido.
5. **Migración:** instalaciones anteriores sin modelo de `quality` registrado.
6. **Documentación:** README (tabla y comparativa), skill, errores e instrucciones del servidor.
7. **Pruebas:** simuladas y reales en la RTX 4090.

## Fuera de alcance

- Cambiar el modelo de `fast` (SDXL Turbo) o el de edición (Kontext Dev).
- Tener varios modelos de `quality` instalados a la vez o elegirlo por llamada en `create_image`.
- Descargar FLUX.1 Schnell del repositorio oficial de Black Forest Labs con `HF_TOKEN`.
- Variante GGUF de Schnell, salvo que las mediciones con 12 GB la pidan (ver supuestos).
- Perfiles de macOS (`mac-*`): siguen con FLUX Dev GGUF sin elección; se revisan en la fase 10.
- Mantener RealVisXL como opción elegible.
- Publicar una versión nueva en PyPI.

## Decisiones

| Tema | Decisión |
|---|---|
| Modelos de `quality` | `flux-dev`, `flux-schnell` y `sdxl`. Solo uno instalado a la vez |
| Perfil frente a modelo | El perfil (`fast`, `quality`, `full`) dice qué capacidades se instalan; el modelo de `quality` decide qué pesos componen la generación de calidad. Las variantes por VRAM de la fase 7 se aplican dentro de la familia elegida (FLUX Dev fp8 o GGUF) |
| Origen de Schnell | Checkpoint fp8 reempaquetado para ComfyUI de un repositorio público, sin token, con revisión, SHA-256, tamaño y licencia `apache-2` fijados. Reutiliza T5, CLIP-L y el VAE de FLUX |
| SDXL 1.0 | `stabilityai/stable-diffusion-xl-base-1.0` (`openrail-pp`) con la LoRA de detalle actual. Sustituye a RealVisXL |
| Refiner de SDXL | `stabilityai/stable-diffusion-xl-refiner-1.0` se incluye en el workflow y en el manifiesto solo si mejora la calidad en la comparación con los mismos prompts y semillas; si no, solo base y LoRA |
| RealVisXL | Sale del catálogo, del perfil `quality-sdxl` y de la skill |
| Migración | Una instalación sin modelo de `quality` registrado se interpreta como `flux-dev` si tiene FLUX Dev (fp8 o GGUF) y como `sdxl` si tiene RealVisXL. El `sdxl_quality` con RealVisXL sigue generando hasta el siguiente `setup`, que propone pasar a SDXL 1.0 y borrar RealVisXL si lo instaló ImageHearth |
| Recomendación | Por VRAM: 20 GB o más, `flux-dev`; de 12 a 20 GB, `flux-schnell` (fp8 con descarga parcial a RAM); menos de 12 GB, `sdxl`. Los umbrales definitivos salen de las mediciones. Se marca la recomendada sea cual sea su licencia |
| Última palabra | Del usuario. Se ofrecen siempre los tres; uno que no cabe se instala con una advertencia que da el mínimo medido y la memoria detectada |
| Componentes FLUX en `full` | T5, CLIP-L y el VAE de FLUX se incluyen por Kontext aunque el modelo de `quality` sea `sdxl` |
| Licencias | El consentimiento muestra solo las de lo que se descarga: con Schnell o SDXL en `quality` no aparece la no comercial de FLUX Dev |
| No interactivo | `--quality-model {flux-dev,flux-schnell,sdxl}`. Si falta, se usa la recomendación y se indica en la salida |
| Agentes | `setup_status` lista los tres con tamaño, licencia, uso comercial, recomendación y si caben. `setup_start` acepta `quality_model` opcional y devuelve la advertencia de hardware. Las instrucciones obligan al agente a decir modelo, licencia y advertencias y a dejar elegir al usuario |
| Cambio | Muestra qué se descarga, qué se borra y el espacio liberado; pide confirmación (`--yes` en no interactivo). Descarga y verifica el nuevo antes de borrar el anterior; repetir el comando continúa donde se quedó |
| Qué se borra | Solo archivos propios según el registro de instalación y que no use ningún componente instalado. Los preexistentes y los del modo adjunto nunca |
| Espacio | Se comprueba con ambos modelos conviviendo durante el cambio |
| Concurrencia | El cambio se rechaza con una generación en curso; si el ComfyUI gestionado estaba en marcha, se reinicia |
| Metadatos del PNG | Modelo de `quality` y workflow que generaron la imagen, como texto del PNG |
| Idioma | Código, mensajes, README y docs en inglés; `specs/` en español |

## Restricciones

- Según la [misión](../mission.md) y [tech-stack](../tech-stack.md), el servidor sigue arrancando sin PyTorch ni ComfyUI y lee el catálogo en cada llamada, para que un cambio de modelo se note sin reiniciar el servidor MCP.
- Una instalación `quality` con Schnell o SDXL no puede incluir ningún archivo con licencia no comercial de FLUX.
- Un cambio interrumpido en cualquier punto deja la instalación generando con el modelo anterior.
- Nunca se aceptan licencias en nombre del usuario, ni desde la CLI ni desde un agente.
- Todos los modelos con revisión y SHA-256 fijados, como el resto de `models.toml`.
- Sin `git commit` por parte del asistente: el usuario revisa y confirma los cambios.

## Entregables

- `models.toml`: entradas de Schnell, SDXL 1.0 base (y refiner si procede), sin RealVisXL; perfiles reorganizados con el modelo de `quality`.
- `provisioner/manifest.py`: modelo de `quality` como dimensión aparte del perfil, recomendación, mínimos y licencias por combinación.
- `provisioner/setup.py` y `cli.py`: pregunta interactiva, `--quality-model`, flujo de cambio y migración.
- `provisioner/install_manifest.py`: modelo de `quality` registrado y consulta de qué archivos usa cada componente.
- Workflows `flux_schnell.json` y `sdxl_base.json` (este sustituye a `sdxl_quality.json` tras la migración).
- `engine/catalog.py`, `engine/status.py`, `provisioner/doctor.py` y `server.py` con el modelo activo y su licencia.
- Metadatos del PNG con modelo y workflow.
- Instrucciones de `FastMCP`, `data/skill/SKILL.md`, mensajes de "no instalado", `README.md`, `README.es.md`, `docs/troubleshooting.md` y `tech-stack.md`.
- Tests simulados en `tests/`, script de medición para las pruebas reales y comparativa en el README.
- Roadmap con las tareas hechas marcadas cuando estén verificadas.

## Supuestos abiertos

- **Repositorio de Schnell fp8:** se supone que existe un repositorio público estable con el checkpoint fp8 para ComfyUI (por ejemplo de Comfy-Org). Si no lo hay, se vuelve a preguntar antes de recurrir a `HF_TOKEN`.
- **Schnell con 12 GB:** se supone que fp8 con descarga parcial a RAM genera bien con 12 GB. Si la medición lo desmiente, se añade una variante GGUF y se ajusta la recomendación.
- **Refiner:** queda pendiente de la comparación; ambos resultados están previstos en el plan.
