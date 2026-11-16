# ImageHearth

**Dale a cualquier agente de IA la capacidad de generar y editar imágenes en tu propio PC.** Sin suscripciones ni nube: tus prompts e imágenes se quedan en tu equipo.

ImageHearth es un servidor [MCP](https://modelcontextprotocol.io) que conecta agentes como Claude Code o Codex con [ComfyUI](https://github.com/Comfy-Org/ComfyUI).

[Read in English](https://github.com/RealHemoglobin/ImageHearth/blob/main/README.md)

**Beta pública.** Se instala con un comando y, si algo falla, [cuéntanoslo](https://github.com/RealHemoglobin/ImageHearth/blob/main/docs/troubleshooting.md#reporting-a-problem).

```bash
# Linux
curl -LsSf https://raw.githubusercontent.com/RealHemoglobin/ImageHearth/main/install.sh | sh
```

```powershell
# Windows
irm https://raw.githubusercontent.com/RealHemoglobin/ImageHearth/main/install.ps1 | iex
```

## Qué le puedes pedir a tu agente

- *"Genera un póster de una ciudad futurista de noche"*: borrador rápido con el modelo rápido que instalaste (SDXL Turbo, Z-Image-Turbo o FLUX.2 Klein 4B).
- *"Haz una imagen de alta calidad de 1536x1024 de un castillo medieval"*: el modelo de calidad que instalaste (Qwen-Image, Chroma1-HD, HiDream, FLUX o SDXL 1.0).
- *"Cambia el fondo de `foto.png` por una montaña nevada"*: el modelo de edición que instalaste (FLUX.2 Klein 4B, Qwen-Image-Edit o FLUX Kontext).
- *"Hazlo con Chroma"* / *"usa el modelo Klein"*: con varios modelos instalados, el agente puede elegir uno por su nombre.
- *"Combina estas tres fotos en una sola escena"*: hasta seis imágenes de referencia.

### Varias imágenes a la vez

Cuando tu agente ya sabe que necesita varias imágenes independientes, pasa una lista de prompts a `create_image` en una sola llamada, que termina cuando están todas. La GPU se prepara una vez para todo el lote: los modelos de lenguaje se descargan y se restauran una vez y ComfyUI arranca una vez, en lugar de repetirlo con cada imagen.

> Haz cuatro variaciones rápidas de un logotipo y dos pósters de alta calidad, de 1024x768.

Cada elemento de la lista es un prompt, o un objeto con su propio prompt, calidad y tamaño. Un lote es solo de imágenes nuevas o solo de ediciones, nunca mezclado, y sus elementos no pueden depender unos de otros (una cadena de ediciones necesita una llamada tras otra). Todo el lote se comprueba antes de generar nada, y una imagen que falla no detiene las demás: la respuesta trae una línea por imagen, en el orden pedido (`1: /ruta/imagen.png` o `2: ERROR: motivo`).

Por defecto un lote tiene como máximo 20 imágenes, para que un agente no retenga la GPU demasiado tiempo. Se cambia con `imagehearth-mcp setup --batch-limit N`; `imagehearth-mcp doctor` muestra el límite en uso. Medido en una RTX 4090 (24 GB) con un modelo de Ollama de 26B cargado, un lote frente a las mismas imágenes en llamadas separadas:

| Imágenes | Llamadas separadas | Un lote | Ahorro |
|---|---|---|---|
| 4 `fast` + 2 `high` | 86,5 s (6 descargas del modelo) | 42,1 s (1 descarga) | 44,4 s (51 %) |
| 3 ediciones Kontext de una foto de 3536x2352 | 566,2 s | 550,3 s | 15,9 s (3 %) |

Lo que se ahorra es la descarga y recarga del modelo de lenguaje y el arranque de ComfyUI, unos 7 s por imagen aquí. Importa con generaciones rápidas y casi desaparece con las lentas: cada edición de una foto grande tarda unos tres minutos y eclipsa la preparación. Cancelar un lote a mitad conservó las imágenes hechas, restauró el modelo y liberó la GPU.

Si también usas modelos de lenguaje locales, ImageHearth los libera de la memoria de la GPU mientras genera y los restaura después. Ollama se ha probado de verdad; LM Studio, llama.cpp y vLLM, solo con servidores simulados.

## Requisitos

| | |
|---|---|
| **GPU** | NVIDIA serie 20 o posterior con un controlador actual (AMD Radeon RX 7000 y 9000 es experimental en Windows; consulta [Soporte](#soporte)). Solo medido en una RTX 4090 de 24 GB; consulta las [mediciones](#requisitos-medidos). Con menos memoria puede ir lento o fallar con los modelos FLUX |
| **Disco** | 7,2 GB para ComfyUI y su entorno, más el perfil que elijas |
| **Software** | Nada que instalar antes: el script instala [uv](https://docs.astral.sh/uv/), que trae su propio Python. No hace falta Git. [Ollama](https://ollama.com/download) es opcional |

### Soporte

Solo se anuncia como soportado lo que se ha ejecutado en hardware real.

| Sistema y GPU | Nivel |
|---|---|
| Linux, NVIDIA serie 20 o posterior | **Soportado.** Probado en hardware real |
| Windows 11, NVIDIA serie 20 o posterior | **Objetivo de esta beta.** Falta verificarlo en máquinas limpias |
| Windows 11, AMD Radeon RX 7000 y 9000 | **Experimental.** Se instala sola con los paquetes ROCm de AMD (unos 5 GB, estimados), sin probar en una Radeon real. Necesita un controlador de AMD actual. Tarjetas: RX 9060 (gfx1200), RX 9070 (gfx1201), RX 7900 (gfx1100), RX 7800/7700 (gfx1101), RX 7600 (gfx1102), Radeon 780M/760M/740M (gfx1103) |
| Linux, AMD | **Experimental.** Paquetes ROCm 7.2 de PyTorch, sin probar |
| Windows, otras AMD (RX 6000 y anteriores) | **Setup no las instala.** Instala ComfyUI a mano y usa `--attach` |
| NVIDIA serie 10 o anterior, Intel Arc, solo CPU | **Experimental.** Se detecta y se ofrece con un aviso, sin haberse probado. Solo con CPU funciona `fast` |
| macOS con Apple Silicon | **Sin probar.** Preparado tras `--experimental`: consulta [más abajo](#macos-sin-probar) |

### Requisitos medidos

Medido con `scripts/measure_profiles.py` a 1024x1024 (Kontext con una referencia): RTX 4090 de 24 GB, controlador 580.178, Linux, ComfyUI 0.43.0, el 2026-10-31.

| Workflow | Perfil | Pico de VRAM | Pico de RAM | Primera generación | Siguientes |
|---|---|---|---|---|---|
| SDXL Turbo | `fast` | 7,0 GB | 2,6 GB | 3,6 s | 1,0 s |
| FLUX Dev | `quality` | 17,8 GB | 2,3 GB | 13,8 s | 10,4 s |
| FLUX Schnell | `quality` | 19,4 GB | 2,3 GB | 5,2 s | 2,8 s |
| SDXL 1.0 | `quality` | 9,6 GB | 2,7 GB | 5,7 s | 4,0 s |
| FLUX Kontext | `full` | 19,3 GB | 2,4 GB | 21,0 s | 18,6 s |

- Son picos en una tarjeta de 24 GB, no mínimos: ComfyUI usa la memoria que encuentra y puede descargar parte en tarjetas menores. Los mínimos para otras GPU son solo orientativos.
- La «primera generación» es tras descargar los modelos de la GPU, con los archivos aún en la caché de disco del sistema. Cargar desde un disco en frío tarda más.
- FLUX Schnell y SDXL 1.0 se midieron el 2026-11-06 en la misma tarjeta (FLUX Dev de nuevo ese día: 19,4 GB, 12,8 s y 10,3 s; la fila anterior tenía un escritorio más ligero). FLUX Schnell con ComfyUI limitado a unos 12 GB (`--reserve-vram 12`) llegó a 12,3 GB y mantuvo 2,8 s por imagen, así que con 12 GB cabe; se simuló reservando memoria en la tarjeta de 24 GB, no se midió en una tarjeta real de 12 GB.
- Las mediciones de Windows siguen pendientes.

> **Nota:** los servidores de modelos locales son opcionales. Si uno no está en marcha, ImageHearth lo ignora y el estado sigue siendo `ready`. Consulta `memory_mode` en los ajustes.

### Un modelo de lenguaje e imágenes en la misma GPU

Medido en la misma RTX 4090 con `qwen3.5:9b`, que necesita 14,3 GB con el contexto por defecto de Ollama y 5,9 GB con `num_ctx` 8192. Con `memory_mode = "auto"` da igual: el modelo se descarga mientras se genera y vuelve después. Para tener los dos cargados (`manual` u `off`), la tarjeta debe albergar el modelo de lenguaje más el pico del workflow: con 5,9 GB y SDXL Turbo, la GPU llegó a 19,2 GB, unos 3 GB de ellos del escritorio. Con 5,9 GB y FLUX Dev llenó los 24 GB y funcionó, en 14-16 s, con `memory_mode = "off"`. En `manual`, la generación se rechaza si hay menos de 8 GB libres para SDXL Turbo o de 16 GB para FLUX, así que ese mismo caso se rechaza ahí.

## Instalación

### 1. Ejecuta el instalador

Elige el nivel que prefieras. Los tres terminan igual: uv, `imagehearth-mcp`, `setup` y `connect --detect`.

**Lo más simple: un comando.** Usa el de tu sistema del [principio de esta página](#imagehearth).

**Con el repositorio clonado.** Descarga el código y ejecuta `install`; así puedes leer antes lo que va a hacer:

```bash
# Linux
git clone https://github.com/RealHemoglobin/ImageHearth.git
cd ImageHearth
./install.sh
```

```powershell
# Windows
git clone https://github.com/RealHemoglobin/ImageHearth.git
cd ImageHearth
.\install.ps1
```

Sin Git, descarga el ZIP desde GitHub y ejecuta el mismo script dentro de la carpeta. Desde un clon se instala ese código, no el paquete publicado. Si PowerShell bloquea el script, ejecuta `powershell -ExecutionPolicy Bypass -File .\install.ps1`.

**Lo más avanzado: a mano.** Con [uv](https://docs.astral.sh/uv/getting-started/installation/) instalado:

```bash
uv tool install --python 3.13 imagehearth-mcp==0.1.0b3
imagehearth-mcp setup
imagehearth-mcp connect --detect
```

Los scripts son breves: [`install.sh`](https://github.com/RealHemoglobin/ImageHearth/blob/main/install.sh) e [`install.ps1`](https://github.com/RealHemoglobin/ImageHearth/blob/main/install.ps1). Hacen esto:

1. Instalan uv con su instalador oficial, si falta.
2. Instalan `imagehearth-mcp`: en una versión fijada, o el código del clon si lo ejecutas desde uno.
3. Ejecutan `setup` y `connect --detect`, que te preguntan antes de descargar o cambiar nada.

Nunca piden `sudo` ni permisos de administrador, ni aceptan una licencia por ti. Puedes repetirlos sin problema.

### 2. Qué hace setup

Setup detecta tu hardware y cualquier ComfyUI existente, propone un perfil y muestra el espacio y las licencias **antes de descargar nada**. Después instala ComfyUI y los modelos y genera una imagen de prueba. Si se interrumpe, vuelve a ejecutarlo y continúa donde se quedó.

| Perfil | Qué incluye |
|---|---|
| `fast` | Generación rápida: uno o más modelos **rápidos** |
| `quality` | `fast` + uno o más modelos de generación de **alta calidad** |
| `full` | `quality` + uno o más modelos de **edición** |

La descarga depende de los modelos que elijas: desde unos 7 GB (solo SDXL Turbo) hasta bastante más de 100 GB con varios grandes. Setup muestra el total, lo que ya está y el espacio libre antes de pedirte que aceptes nada.

#### Elegir los modelos

**Cómo se responde.** Cada pregunta muestra opciones numeradas: pulsa un número para elegirla (sin Enter), o Enter para la recomendada. Las de sí o no se responden con una tecla (`y`, `s` o `n`). **0 vuelve** a la pregunta anterior conservando tus respuestas; en la primera, sale sin cambiar nada. Cada pregunta indica `Step N of M` y no se escribe ni se descarga nada hasta que aceptes el resumen final. Ctrl+C sale en cualquier momento sin dejar nada a medias. Sin terminal (tubería, algunos IDE) o con `--non-interactive`, setup lee un número y Enter por línea, o necesita las opciones en la línea de comandos.

Cada capacidad del perfil (**rápida**, **calidad** y, con `full`, **edición**) tiene su propia selección múltiple (flechas, Espacio para marcar, Enter para aceptar) con **uno o más** modelos. En una instalación nueva solo sale marcado el recomendado para tu GPU; en una existente, los instalados. Cada línea muestra el tamaño de descarga y el tiempo por imagen medido para el nivel de tu GPU, la licencia y si permite uso comercial. Después, por cada modelo con más de una **precisión**, un menú muestra el tamaño, el tiempo, la memoria de GPU y cuánto pasaría a la RAM del sistema en tu nivel (la recomendada es la mejor que cabe sin pasar pesos a la RAM). Si marcaste varios modelos en una capacidad, eliges cuál es el **predeterminado**: el que usa `create_image` cuando no se le indica modelo. Antes de confirmar, setup muestra el plan con el espacio que necesita frente al libre y, si se sustituyen modelos, qué se borrará y por qué; sin espacio suficiente se niega a continuar.

Los tiempos son segundos por imagen de 1024x1024 con el modelo ya cargado, medidos en una RTX 4090 limitada a 8, 16 y 24 GB (y la tarjeta entera para 32+ GB, que solo difiere donde los pesos dejan de pasar a la RAM). Un `*` indica que parte del modelo pasó a la RAM del sistema en ese nivel. Detalles y método: [el análisis](https://github.com/RealHemoglobin/ImageHearth/blob/main/specs/2026-11-15-analisis-modelos/analysis.md). Un guion largo significa no medido.

| Modelo | `name` | Precisión | Descarga | 8 GB | 16 GB | 24 GB | 32+ GB | Licencia | Uso comercial |
|---|---|---|---|---|---|---|---|---|---|
| **Rápidos** | | | | | | | | | |
| SDXL Turbo | `sdxl-turbo` | fp16 | 6,9 GB | — | — | — | — | [Stability AI Community](https://huggingface.co/stabilityai/sdxl-turbo/blob/main/LICENSE.md) | Con registro; licencia por encima de 1 M USD al año |
| Z-Image-Turbo | `z-image-turbo` | int8 | 12,2 GB | 2,0 s | 2,0 s | 2,0 s | 2,0 s | [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0) | Sí |
| Z-Image-Turbo | `z-image-turbo` | bf16 | 20,7 GB | 4,1 s* | 3,6 s | 3,6 s | 3,6 s | Apache-2.0 | Sí |
| FLUX.2 Klein 4B | `klein-4b` | bf16 | 16,1 GB | 1,5 s | 1,3 s | 1,3 s | 1,3 s | Apache-2.0 | Sí |
| **Calidad** | | | | | | | | | |
| SDXL 1.0 | `sdxl` | fp16 | 7,0 GB | — | — | — | — | [CreativeML Open RAIL++-M](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/blob/main/LICENSE.md) | Sí, con restricciones de uso |
| FLUX.1 Dev | `flux-dev` | fp8 / GGUF Q5 | 17,6 / 12,3 GB | — | — | — | — | [FLUX [dev] Non-Commercial](https://bfl.ai/legal/non-commercial-license-terms) | **No** |
| FLUX.1 Schnell | `flux-schnell` | fp8 | 17,6 GB | — | — | — | — | Apache-2.0 | Sí |
| Chroma1-HD | `chroma-hd` | fp8 | 14,7 GB | 19,3 s | 17,7 s | 17,7 s | 17,7 s | Apache-2.0 | Sí |
| Chroma1-HD | `chroma-hd` | bf16 | 23,3 GB | 37,5 s* | 27,4 s | 25,9 s | 25,9 s | Apache-2.0 | Sí |
| Qwen-Image | `qwen-image` | Q2_K | 16,7 GB | 44,3 s | 35,7 s | 35,8 s | 35,8 s | Apache-2.0 | Sí |
| Qwen-Image | `qwen-image` | Q4_K_M | 22,7 GB | 60,3 s | 39,9 s | 38,3 s | 37,3 s | Apache-2.0 | Sí |
| Qwen-Image | `qwen-image` | fp8 | 30,1 GB | 30,8 s* | 26,2 s* | 24,3 s | 24,3 s | Apache-2.0 | Sí |
| Qwen-Image | `qwen-image` | bf16 | 50,5 GB | 53,6 s* | 40,7 s* | 33,2 s* | 33,6 s* | Apache-2.0 | Sí |
| HiDream-I1 Full | `hidream-full` | Q4_K_M | 27,7 GB | 95,7 s* | 76,7 s | 77,8 s | 78,5 s | [MIT](https://opensource.org/license/mit) + [Llama 3.1](https://www.llama.com/llama3_1/license/) | Sí (condiciones de Llama) |
| HiDream-I1 Full | `hidream-full` | fp8 | 33,3 GB | 73,1 s* | 68,4 s | 67,7 s | 64,4 s | MIT + Llama 3.1 | Sí (condiciones de Llama) |
| **Edición** | | | | | | | | | |
| FLUX.1 Kontext Dev | `kontext` | fp8 / GGUF Q5 | 17,6 / 12,4 GB | — | — | — | — | FLUX [dev] Non-Commercial | **No** |
| FLUX.2 Klein 4B | `klein-4b` | bf16 | 16,1 GB | 2,5 s | 2,5 s | 2,5 s | 2,5 s | Apache-2.0 | Sí |
| Qwen-Image-Edit-2511 | `qwen-image-edit` | Q4_K_M | 22,5 GB | 173 s | 140 s | 137 s | 137 s | Apache-2.0 | Sí |
| Qwen-Image-Edit-2511 | `qwen-image-edit` | fp8 | 30,2 GB | 120,8 s* | 112,5 s* | 112,9 s | 112,9 s | Apache-2.0 | Sí |

Los tamaños de descarga incluyen el codificador de texto y el VAE, que varios modelos comparten (se descargan una sola vez). Las precisiones sin medir no se ofrecen: HiDream fp16 y Qwen-Image-Edit bf16.

**Recomendado para cada nivel de memoria de GPU** (marcado y preseleccionado, pero puedes elegir cualquier otro):

| Memoria de GPU | Rápido | Calidad | Edición |
|---|---|---|---|
| 8 GB | FLUX.2 Klein 4B | Chroma1-HD fp8 | FLUX.2 Klein 4B |
| 16 GB | Z-Image-Turbo bf16 | Qwen-Image Q4_K_M | FLUX.2 Klein 4B |
| 24 GB | Z-Image-Turbo bf16 | Qwen-Image fp8 | Qwen-Image-Edit fp8 |
| 32 GB o más | Z-Image-Turbo bf16 | Qwen-Image fp8 | Qwen-Image-Edit fp8 |

Todas las recomendaciones tienen una licencia que permite el uso comercial, y existe una instalación completa con generación y edición bajo esas licencias en cada nivel.

Notas:

- Aunque un modelo no quepa en tu GPU puedes instalarlo: setup avisa con el mínimo y la memoria que ha detectado, y la última palabra es tuya. La edición y las precisiones GGUF necesitan ComfyUI-GGUF, que setup instala (fijado) cuando un modelo lo necesita.
- Las licencias que setup te pide aceptar son solo las de lo que descarga. El codificador de texto de HiDream es Llama 3.1 8B: se lista su licencia (con el aviso «Built with Llama») y en modo no interactivo hace falta `--accept-licenses`. Si un repositorio pasa a pedir aprobación o un token, setup lo dice y puedes definir `HF_TOKEN`. **FLUX Dev y Kontext son no comerciales.**
- FLUX.1 Dev y Kontext usan fp8 con 20 GB o más y GGUF Q5 con 12 a 20 GB. FLUX.2 Klein 4B y Qwen-Image-Edit editan una imagen de referencia cada vez; FLUX Kontext admite hasta seis.
- Qwen-Image-Edit tarda de dos a tres minutos por imagen en cualquier nivel y cambia más de lo pedido (reilumina la escena); FLUX.2 Klein 4B es el único que edita en segundos. Klein escribió «OPPEN» en el prompt del cartel de la comparativa.
- La comparativa de calidad, las rejillas de imágenes y las mediciones están en [el análisis](https://github.com/RealHemoglobin/ImageHearth/blob/main/specs/2026-11-15-analisis-modelos/analysis.md).

**En la línea de comandos** (también en modo no interactivo), cada capacidad recibe una lista separada por comas de `nombre[:precisión]`; el primero es el predeterminado. Sin precisión, setup usa la que ya está instalada o la recomendada para tu GPU:

```bash
imagehearth-mcp setup --profile full \
  --fast-models klein-4b,sdxl-turbo \
  --quality-models qwen-image:q4_k_m,chroma-hd:fp8 \
  --edit-models klein-4b
```

Un nombre o una precisión equivocados fallan antes de descargar nada y listan los válidos. Sin ninguna de estas opciones, una instalación nueva recibe el modelo recomendado de cada capacidad (y lo indica); una existente conserva lo que tiene. `--quality-model NOMBRE` sigue funcionando como `--quality-models NOMBRE`.

**Cambiar los modelos más adelante.** En una instalación existente una lista **fija el conjunto** de esa capacidad: setup descarga lo que falta, lo verifica y solo entonces borra lo que dejaste fuera o sustituiste (también al cambiar de precisión). Muestra lo que va a descargar y a borrar, y por qué, y te pide confirmar (`--yes` en modo no interactivo). Añadir modelos no necesita confirmación. Las capacidades que no pases se dejan como están. Solo se borran los archivos que instaló ImageHearth y que ningún modelo restante necesita: tus modelos, los de un ComfyUI adjunto y lo compartido se conservan. Se rechaza mientras se genera una imagen. Desde un agente, `setup_start` recibe `fast_models`, `quality_models` y `edit_models` y hace lo mismo.

**Instalaciones anteriores.** Una instalación hecha antes de esta elección sigue generando, sin descargar ni borrar nada: SDXL Turbo es su modelo rápido, su modelo de calidad (FLUX Dev, FLUX Schnell o SDXL 1.0; o un SDXL antiguo con RealVisXL) el de calidad y Kontext, si lo tiene, el de edición, cada uno como predeterminado. RealVisXL ya no se ofrece; `imagehearth-mcp doctor` te dice cómo pasar a SDXL 1.0 (`setup --quality-models sdxl`).

**Pedir un modelo.** `create_image(prompt="un zorro", model="klein-4b")` usa un modelo instalado; `quality: "high"` o `image_paths` indican qué capacidad debe tener, y sin `model` se usa el predeterminado de esa capacidad. `list_workflows` lista cada modelo instalado con su capacidad, precisión, si es el predeterminado, licencia, uso comercial y segundos medidos. Un `model` desconocido, no instalado, de otra capacidad o combinado con `workflow` falla antes de tocar la GPU y dice qué hay instalado y el comando que instala el resto. En una lista de prompts, `model` puede indicarse por elemento o para todos. Las LoRAs solo funcionan con `sdxl`.

Cada imagen generada guarda el modelo (`ImageHearth-Model`, como `nombre:precisión`), el modelo de calidad y el workflow en el texto del PNG (`ImageHearth-Quality-Model`, `ImageHearth-Workflow`), junto a lo que escribe ComfyUI. `list_workflows` y `doctor` muestran los modelos instalados y sus licencias, y `get_engine_status` el modelo de calidad predeterminado.

#### LoRAs de estilo (solo SDXL 1.0)

Con `sdxl` entre los modelos de calidad, setup también ofrece pequeñas **LoRAs de estilo**: pixel art, papel recortado, línea, lápiz, cera, 3D, plastilina y alguna más. Son opcionales y no se instala ninguna si no la eliges. Solo funcionan con SDXL 1.0 (`quality: "high"`, `model: "sdxl"` o como predeterminado): no con los demás modelos, `fast` ni la edición. `setup` interactivo añade un paso tras el modelo con una selección múltiple que muestra categoría, tamaño y licencia de cada una (números separados por comas, Enter para dejar las marcadas, `none` para ninguna, 0 vuelve). En no interactivo: `--loras nombre1,nombre2`, `--loras all` o `--loras none`. En una instalación existente `--loras` **fija el conjunto**: descarga las que faltan y borra las que no están en la lista (solo archivos que descargó ImageHearth; los tuyos en `models/loras` no se tocan nunca). Sin `--loras` las LoRAs se quedan como están. Quitar SDXL 1.0 también las borra, y la confirmación lo dice. Desde un agente, `setup_status` las lista en `loras` y `setup_start` acepta `loras` (`["all"]` o una lista).

El agente ve las instaladas en `list_workflows` (el elemento `sdxl` tiene una lista `loras`) y las usa con `create_image(prompt="un faro al amanecer", quality="high", loras=["pixel-art"])`, o con un peso de 0 a 2: `loras=[{"name": "crayon", "weight": 0.6}]`. Como máximo 3 por imagen, cada una una vez; un nombre solo usa su peso recomendado; en una lista de prompts, `loras` se puede dar por elemento o para todos. Las palabras de activación de la LoRA se añaden al prompt por ti, y `style: "auto"` no añade pistas fotográficas cuando una LoRA pide otro medio. Una petición que no admite LoRAs (otro modelo, `fast`, edición, un nombre no instalado) falla antes de tocar la GPU y dice por qué. Cada PNG las guarda en `ImageHearth-LoRAs`.

Cada una se eligió tras medirla en la RTX 4090 contra el mismo texto sin la LoRA (mismo prompt y semilla), y solo se ofrecen las de licencia que permite uso comercial. Quedan fuera las que no mejoraban el prompt solo: **no hay LoRA de acuarela ni de «detalle»** (SDXL ya dibuja una buena acuarela desde el texto y las candidatas eran peores). Los motivos y todas las candidatas probadas están en [la selección](https://github.com/RealHemoglobin/ImageHearth/blob/main/specs/2026-11-15-loras-sdxl/seleccion-loras.md). Mismo prompt y semilla en cada fila (`a red fox sitting in a snowy forest at dawn`); la LoRA con su peso recomendado. Las licencias son las de cada autor, con restricciones de uso que hay que trasladar: mira [THIRD_PARTY_NOTICES.md](https://github.com/RealHemoglobin/ImageHearth/blob/main/THIRD_PARTY_NOTICES.md).

| Nombre | Categoría | Licencia | Tamaño | Sin LoRA | Con LoRA |
|---|---|---|---|---|---|
| `pixel-art` | pixel-art | [CreativeML OpenRAIL-M](https://huggingface.co/spaces/CompVis/stable-diffusion-license) | 171 MB | <img src="https://raw.githubusercontent.com/RealHemoglobin/ImageHearth/main/docs/images/loras/no-lora.jpg" width="140"> | <img src="https://raw.githubusercontent.com/RealHemoglobin/ImageHearth/main/docs/images/loras/pixel-art.jpg" width="140"> |
| `anime-pop` | anime | [CreativeML OpenRAIL-M](https://huggingface.co/spaces/CompVis/stable-diffusion-license) | 228 MB | <img src="https://raw.githubusercontent.com/RealHemoglobin/ImageHearth/main/docs/images/loras/no-lora.jpg" width="140"> | <img src="https://raw.githubusercontent.com/RealHemoglobin/ImageHearth/main/docs/images/loras/anime-pop.jpg" width="140"> |
| `photorealism` | photo | [CreativeML OpenRAIL-M](https://huggingface.co/spaces/CompVis/stable-diffusion-license) | 456 MB | <img src="https://raw.githubusercontent.com/RealHemoglobin/ImageHearth/main/docs/images/loras/no-lora.jpg" width="140"> | <img src="https://raw.githubusercontent.com/RealHemoglobin/ImageHearth/main/docs/images/loras/photorealism.jpg" width="140"> |
| `papercut` | illustration | [CreativeML OpenRAIL-M](https://huggingface.co/spaces/CompVis/stable-diffusion-license) | 341 MB | <img src="https://raw.githubusercontent.com/RealHemoglobin/ImageHearth/main/docs/images/loras/no-lora.jpg" width="140"> | <img src="https://raw.githubusercontent.com/RealHemoglobin/ImageHearth/main/docs/images/loras/papercut.jpg" width="140"> |
| `flat-illustration` | illustration | [CreativeML OpenRAIL-M](https://huggingface.co/spaces/CompVis/stable-diffusion-license) | 457 MB | <img src="https://raw.githubusercontent.com/RealHemoglobin/ImageHearth/main/docs/images/loras/no-lora.jpg" width="140"> | <img src="https://raw.githubusercontent.com/RealHemoglobin/ImageHearth/main/docs/images/loras/flat-illustration.jpg" width="140"> |
| `lineart` | illustration | [CreativeML OpenRAIL-M](https://huggingface.co/spaces/CompVis/stable-diffusion-license) | 171 MB | <img src="https://raw.githubusercontent.com/RealHemoglobin/ImageHearth/main/docs/images/loras/no-lora.jpg" width="140"> | <img src="https://raw.githubusercontent.com/RealHemoglobin/ImageHearth/main/docs/images/loras/lineart.jpg" width="140"> |
| `pencil-art` | illustration | [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0) | 456 MB | <img src="https://raw.githubusercontent.com/RealHemoglobin/ImageHearth/main/docs/images/loras/no-lora.jpg" width="140"> | <img src="https://raw.githubusercontent.com/RealHemoglobin/ImageHearth/main/docs/images/loras/pencil-art.jpg" width="140"> |
| `crayon` | illustration | [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0) | 48 MB | <img src="https://raw.githubusercontent.com/RealHemoglobin/ImageHearth/main/docs/images/loras/no-lora.jpg" width="140"> | <img src="https://raw.githubusercontent.com/RealHemoglobin/ImageHearth/main/docs/images/loras/crayon.jpg" width="140"> |
| `3d-render` | 3d | [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0) | 85 MB | <img src="https://raw.githubusercontent.com/RealHemoglobin/ImageHearth/main/docs/images/loras/no-lora.jpg" width="140"> | <img src="https://raw.githubusercontent.com/RealHemoglobin/ImageHearth/main/docs/images/loras/3d-render.jpg" width="140"> |
| `clay-animation` | 3d | [CreativeML OpenRAIL-M](https://huggingface.co/spaces/CompVis/stable-diffusion-license) | 171 MB | <img src="https://raw.githubusercontent.com/RealHemoglobin/ImageHearth/main/docs/images/loras/no-lora.jpg" width="140"> | <img src="https://raw.githubusercontent.com/RealHemoglobin/ImageHearth/main/docs/images/loras/clay-animation.jpg" width="140"> |

Puedes empezar con `fast` y ejecutar `setup --profile full` más adelante: lo que ya está no se vuelve a descargar. ImageHearth solo ofrece lo instalado: `list_workflows` lo muestra, un `setup` posterior se nota sin reiniciar nada, y pedir algo que falta da un error con el comando de `setup` exacto, nunca otro modelo en su lugar.

| Opción | Uso |
|---|---|
| `--profile fast\|quality\|full` | Elige el perfil sin preguntar. En macOS: `mac-fast\|mac-quality\|mac-full` |
| `--fast-models`, `--quality-models`, `--edit-models` | Modelos de cada capacidad, como `nombre[:precisión],...`; el primero es el predeterminado. Sin ellas, una instalación nueva usa los recomendados y una existente conserva los suyos. `--quality-model NOMBRE` es la forma antigua |
| `--loras NOMBRES` | LoRAs de estilo para SDXL 1.0: nombres separados por comas, `all` o `none`. En una instalación existente fija el conjunto (descarga las que faltan y borra las demás). Sin ella no cambia nada |
| `--variant fp8\|gguf` | Precisión de los modelos que no indican una con `nombre:precisión`, donde la tengan, en vez de la recomendada |
| `--yes` | Confirma el cambio de modelo de calidad sin preguntar |
| `--experimental` | Obligatorio en macOS, que está sin probar |
| `--accept-licenses` | Acepta las licencias sin preguntar. Obligatoria con `--non-interactive` |
| `--non-interactive` | No pregunta nunca: falla si falta una decisión |
| `--managed` | Instala un ComfyUI propio, aunque exista otro |
| `--attach RUTA` | Usa el ComfyUI que hay en `RUTA` |
| `--install-node` | Permite instalar el nodo de estado en un ComfyUI adjunto |
| `--install-dir RUTA` | Instala ComfyUI en `RUTA/comfyui` y los modelos en `RUTA/comfyui/models`, salvo que `--models-dir` diga otra cosa. No es compatible con `--attach` |
| `--models-dir RUTA` | Guarda los modelos en `RUTA` y los comparte con `extra_model_paths.yaml` |
| `--port PUERTO` | Puerto en el que escucha ComfyUI |
| `--skip-smoke-test` | No genera la imagen de prueba |

Define `HF_TOKEN` si Hugging Face restringe el acceso a un modelo.

#### macOS (sin probar)

**ImageHearth nunca se ha ejecutado en un Mac, y macOS no tiene soporte.** Para probarlo, añade la opción al instalador: `curl -LsSf https://raw.githubusercontent.com/RealHemoglobin/ImageHearth/main/install.sh | sh -s -- --experimental`. `setup` está preparado para Apple Silicon, con modelos GGUF (`mac-fast` 6,9 GB, `mac-quality` 19,2 GB, `mac-full` 27,6 GB) y el nodo `ComfyUI-GGUF`. Los workflows GGUF se han ejecutado en una GPU NVIDIA, lo que comprueba el grafo y los archivos pero no MPS. Los Mac con Intel no tienen soporte. Si lo pruebas, cuéntanos cómo ha ido, con la salida de `imagehearth-mcp doctor --json`.

**Elegir dónde se instala.** ComfyUI y los modelos ocupan decenas de GB. `setup` interactivo pregunta la carpeta después del modo: la de siempre (recomendada), los otros discos que encuentra con su espacio libre, o una ruta que escribas. No se crea nada hasta que confirmes. Con `--install-dir RUTA` no pregunta. Antes de descargar, `setup` comprueba que puede escribir allí, que hay espacio y que el sistema de archivos admite los archivos: FAT32 no admite archivos de más de 4 GB, así que lo rechaza; las unidades de red o extraíbles, y en Windows las rutas con espacios o caracteres no ASCII, solo dan un aviso, y una ruta demasiado larga para Windows se rechaza si las rutas largas no están activadas. La carpeta se guarda en `config.toml` y en `install.json`, así que `update`, `doctor` y `uninstall` la usan; `uninstall` la borra solo si la creó `setup` y queda vacía. Una carpeta distinta sobre una instalación existente se rechaza: usa `update --move-to`. Desde un agente, `setup_status` lista las carpetas y `setup_start` acepta `install_dir`.

**Usar un ComfyUI que ya tienes.** Con `--attach`, o eligiéndolo cuando te pregunte, ImageHearth lo usa en lugar de instalar otro y no descarga los modelos que ya tiene. Tu ComfyUI solo cambia si permites instalar el nodo de estado. ComfyUI Desktop debe estar abierto, porque ImageHearth no puede arrancarlo.

### 3. Compruébalo, actualízalo o elimínalo

El instalador ejecuta `uv tool update-shell` si una terminal nueva no encontraría `imagehearth-mcp`; abre otra terminal después. `imagehearth-mcp doctor` lo comprueba y, si aún falta algo, imprime el comando exacto para tu shell.

```bash
imagehearth-mcp doctor
```

Comprueba cada capa e indica cómo arreglar lo que falle. Añade `--json` para un formato estable, o `--verify-hashes` para comparar el SHA-256 de cada modelo en lugar de su tamaño. Termina con un código distinto de cero si algo falla.

```bash
imagehearth-mcp update
```

**Para tener una versión nueva de ImageHearth**, ejecuta de nuevo el instalador: sustituye la versión instalada por la que fija, conserva tu configuración, tus modelos y los agentes conectados, y no descarga lo que ya está. Luego reinicia tu agente. (A mano: `uv tool install --python 3.13 --force imagehearth-mcp`.) Este comando aplica la versión de ComfyUI y los modelos que fija la versión instalada de ImageHearth. Un ComfyUI adjunto no se toca, salvo el nodo de estado que haya instalado setup.

```bash
imagehearth-mcp update --move-to D:\ImageHearth
```

**Para mover una instalación a otra carpeta o disco**, `update --move-to RUTA` traslada a `RUTA/comfyui` el ComfyUI que instaló ImageHearth y los modelos que descargó. Muestra qué se mueve, su tamaño y el espacio libre, y pregunta una vez (`--yes` lo salta). Se niega mientras se genera una imagen o hay una instalación en curso, y para ComfyUI. En el mismo disco renombra; en otro copia, comprueba tamaño y SHA-256, crea de nuevo el entorno de Python y borra lo viejo solo al final. Hasta entonces sigue funcionando desde la carpeta antigua, así que si se interrumpe (Ctrl+C, corte de luz) ejecuta el mismo comando para continuar, o `update --move-to` con la carpeta actual para cancelarlo. No toca un ComfyUI adjunto ni los modelos que ImageHearth no descargó. Reinicia después tus agentes para que lean la carpeta nueva. `imagehearth-mcp doctor` muestra la carpeta de instalación, el disco y el espacio libre, y avisa de un traslado a medias.

```bash
imagehearth-mcp uninstall
```

Muestra qué va a borrar y borra solo lo que instaló setup. Los modelos necesitan una confirmación aparte (`--remove-models` o `--keep-models` para decidirlo de antemano, `--yes` para saltar la primera pregunta). Un ComfyUI o unos modelos que ya estaban nunca se tocan. También busca en cada agente las entradas de ImageHearth (`imagehearth` y el nombre antiguo `imageengine`) y las skills que `connect` no registró, en todos los ámbitos de Claude Code. Retira las que ejecutan ImageHearth, preguntando antes salvo con `--yes`; una entrada que ejecuta otro programa, una skill modificada y el `.mcp.json` de un proyecto se dejan y se avisan con la orden para quitarlos. Después reinicia los agentes que tengas abiertos. Para quitar el propio comando, ejecuta `uv tool uninstall imagehearth-mcp`. Si algo sigue apareciendo, `imagehearth-mcp doctor` lista todas las entradas que encuentra (véase [solución de problemas](https://github.com/RealHemoglobin/ImageHearth/blob/main/docs/troubleshooting.md#common-problems)).

### Configuración (opcional)

`setup` escribe lo que necesita en `~/.config/imagehearth/config.toml` en Linux y en `%APPDATA%\imagehearth\config.toml` en Windows. También puedes editarlo:

```toml
comfy_dir = "~/AI/ComfyUI"      # dónde está instalado ComfyUI
comfy_port = 8188               # puerto en el que escucha ComfyUI
output_dir = "~/Pictures/ImageHearth"
ollama_url = "http://127.0.0.1:11434"
memory_mode = "auto"            # "auto", "off" o "manual", ver abajo
lmstudio_url = "http://127.0.0.1:1234"
llamacpp_url = "http://127.0.0.1:8080"
vllm_url = "http://127.0.0.1:8000"
batch_limit = 20                # máximo de imágenes por llamada a create_image
```

Cada clave se puede definir también con una variable de entorno: `IMAGEHEARTH_COMFY_DIR`, `IMAGEHEARTH_COMFY_PORT`, `IMAGEHEARTH_OUTPUT_DIR`, `IMAGEHEARTH_OLLAMA_URL`, `IMAGEHEARTH_LMSTUDIO_URL`, `IMAGEHEARTH_LLAMACPP_URL`, `IMAGEHEARTH_VLLM_URL` e `IMAGEHEARTH_MEMORY_MODE`. Las variables ganan al archivo, y el archivo a los valores por defecto.

| `memory_mode` | Qué pasa con tus modelos de lenguaje |
|---|---|
| `auto` | Se descargan antes de generar y se restauran después. Si un servidor no puede descargar (ver abajo), recibes un aviso con qué hacer, o un error antes de empezar si la memoria no basta |
| `manual` | No se tocan. La generación falla con una explicación si la memoria libre no basta |
| `off` | No se tocan y no se comprueba la memoria |

El antiguo `ollama_mode` sigue funcionando como alias de `auto` u `off`; si están los dos, gana `memory_mode`.

| Servidor | ¿Puede ImageHearth liberar su memoria? |
|---|---|
| Ollama | Sí |
| LM Studio | Sí, con su API REST v1. Versiones anteriores: solo aviso |
| llama.cpp | Solo en modo router. Un `llama-server` de un solo modelo no puede descargar: solo aviso |
| vLLM | Solo si arranca con `VLLM_SERVER_DEV_MODE=1` y `--enable-sleep-mode`. Si no: solo aviso |

### 4. Conecta tu agente

El instalador ya ha ejecutado `imagehearth-mcp connect --detect`, que busca los clientes instalados y ofrece conectarlos. Vuelve a ejecutarlo si instalas otro. También puedes usar `connect <cliente>`, o `connect --print <cliente>` para ver el fragmento sin tocar nada. Hace copia de seguridad, conserva tus demás entradas y se puede repetir.

**Probados:** Claude Code, Codex, opencode, Hermes y pi. **Sin probar**, contrastados solo con su documentación: Claude Desktop, Gemini CLI, Cursor, VS Code y JetBrains. Detalles y fragmentos en [`docs/agents.md`](https://github.com/RealHemoglobin/ImageHearth/blob/main/docs/agents.md). También puedes pedirle la instalación a un agente con [`llms-install.md`](https://github.com/RealHemoglobin/ImageHearth/blob/main/llms-install.md).

### 5. Pruébalo

Reinicia tu agente y pídele:

> Genera una imagen de una bicicleta roja en una playa, con calidad rápida.

ComfyUI arranca solo. La primera imagen tarda más porque tiene que cargar el modelo. Las imágenes se guardan en `~/Pictures/ImageHearth/`.

## Solución de problemas

Ejecuta `imagehearth-mcp doctor`, o pide a tu agente que *"compruebe el estado de ImageHearth"*. Los problemas frecuentes y cómo informar de uno están en [`docs/troubleshooting.md`](https://github.com/RealHemoglobin/ImageHearth/blob/main/docs/troubleshooting.md), en inglés.

ImageHearth solo reinicia o detiene un ComfyUI que haya lanzado él mismo (guarda su PID en la carpeta de datos). Si ejecutas ComfyUI en el mismo puerto, lo usa pero nunca lo reinicia.

## Licencias de los modelos

Los modelos no forman parte de este proyecto y tienen sus propias condiciones. **Al descargarlos, las aceptas.** Este resumen no es asesoramiento legal; los detalles están en [`THIRD_PARTY_NOTICES.md`](https://github.com/RealHemoglobin/ImageHearth/blob/main/THIRD_PARTY_NOTICES.md).

| Modelo | Licencia | En resumen |
|---|---|---|
| FLUX.1 Dev | [FLUX.1 [dev] Non-Commercial](https://bfl.ai/legal/non-commercial-license-terms) | Uso no comercial del modelo |
| FLUX.1 Kontext Dev | [FLUX.1 [dev] Non-Commercial](https://bfl.ai/legal/non-commercial-license-terms) | Uso no comercial del modelo |
| SDXL Turbo | [Stability AI Community](https://huggingface.co/stabilityai/sdxl-turbo/blob/main/LICENSE.md) | El uso comercial exige registro y tiene un límite de ingresos |
| Z-Image-Turbo, FLUX.2 Klein 4B, Chroma1-HD, Qwen-Image, Qwen-Image-Edit, FLUX.1 Schnell | [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0) | Permisiva: uso comercial permitido |
| HiDream-I1 Full | [MIT](https://opensource.org/license/mit) | Permisiva. Su codificador de texto es Llama 3.1 (fila siguiente) |
| Llama 3.1 8B (codificador de texto de HiDream) | [Llama 3.1 Community](https://www.llama.com/llama3_1/license/) | Uso comercial con condiciones; muestra «Built with Llama» si lo redistribuyes |

## Desarrollo

```bash
uv sync
uv run ruff check .
uv run pytest
```

Hace falta [uv](https://docs.astral.sh/uv/getting-started/installation/), que crea su propio entorno en `.venv`, separado del de ComfyUI. Los tests usan servidores simulados y no necesitan GPU. Consulta [`CONTRIBUTING.md`](https://github.com/RealHemoglobin/ImageHearth/blob/main/CONTRIBUTING.md) para contribuir y el [roadmap](https://github.com/RealHemoglobin/ImageHearth/blob/main/specs/roadmap.md) para ver qué está previsto. Para ayudar a probar la beta, consulta [`docs/beta-testing.md`](https://github.com/RealHemoglobin/ImageHearth/blob/main/docs/beta-testing.md). Para avisar de una vulnerabilidad, consulta [`SECURITY.md`](https://github.com/RealHemoglobin/ImageHearth/blob/main/SECURITY.md).

## Licencia

[MIT](https://github.com/RealHemoglobin/ImageHearth/blob/main/LICENSE), salvo el nodo personalizado de ComfyUI en [`src/imagehearth_mcp/data/imagehearth_status/`](https://github.com/RealHemoglobin/ImageHearth/blob/main/src/imagehearth_mcp/data/imagehearth_status/LICENSE), que es GPL-3.0. Los componentes y modelos de terceros figuran en [`THIRD_PARTY_NOTICES.md`](https://github.com/RealHemoglobin/ImageHearth/blob/main/THIRD_PARTY_NOTICES.md).
