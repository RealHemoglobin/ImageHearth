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

- *"Genera un póster de una ciudad futurista de noche"*: borrador rápido con SDXL Turbo.
- *"Haz una imagen de alta calidad de 1536x1024 de un castillo medieval"*: el modelo de calidad que instalaste (FLUX Dev, FLUX Schnell o SDXL 1.0).
- *"Cambia el fondo de `foto.png` por una montaña nevada"*: FLUX Kontext.
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

| Perfil | Qué incluye | Modelos |
|---|---|---|
| `fast` | Generación rápida con SDXL Turbo | 6,9 GB |
| `quality` | `fast` + un modelo de alta calidad **a tu elección** (abajo) | 13,9 a 24,6 GB |
| `full` | `quality` + edición con FLUX Kontext | 31,6 a 36,5 GB |

#### Elegir el modelo de calidad

Con `quality` o `full`, setup pregunta qué modelo instalar para la generación de alta calidad. Solo hay uno instalado a la vez. Muestra de cada uno el tamaño de descarga, la memoria de GPU mínima, la licencia y si permite uso comercial, marca el recomendado para tu GPU y avisa de los que no caben. En modo no interactivo, pasa `--quality-model`; sin él, setup usa el recomendado y lo indica.

| Modelo | `--quality-model` | Licencia | Uso comercial | Descarga | Memoria de GPU | Recomendado desde |
|---|---|---|---|---|---|---|
| FLUX.1 Dev | `flux-dev` | [FLUX [dev] Non-Commercial](https://bfl.ai/legal/non-commercial-license-terms) | **No** | 17,6 GB (fp8) o 12,2 GB (GGUF Q5) | 20 GB (12 GB con GGUF) | 20 GB |
| FLUX.1 Schnell | `flux-schnell` | [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0) | Sí | 17,6 GB | 12 GB (simulado limitando la tarjeta de 24 GB) | 12 GB |
| SDXL 1.0 | `sdxl` | [CreativeML Open RAIL++-M](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/blob/main/LICENSE.md) | Sí, con restricciones de uso | 7,0 GB | 8 GB | cualquiera |

- FLUX Dev da más detalle; FLUX Schnell genera la imagen en 4 pasos; SDXL 1.0 es el más ligero y admite prompt negativo. Aunque un modelo no quepa en tu GPU puedes instalarlo: setup avisa con el mínimo y la memoria que ha detectado, y la última palabra es tuya.
- Las licencias que setup te pide aceptar son solo las de lo que descarga. Con `flux-schnell` o `sdxl` en `quality` no se descarga ningún archivo de FLUX [dev]. **La edición con FLUX Kontext en `full` es no comercial sea cual sea el modelo de calidad.**
- FLUX Dev usa fp8 con 20 GB o más y GGUF Q5 con 12 a 20 GB (ComfyUI pasa a la RAM del sistema lo que no cabe, y eso es más lento). Fuerza una con `--variant fp8|gguf`. Estas opciones pequeñas se han simulado a propósito y aún no se han medido en una tarjeta real de 12 a 20 GB.
- La edición necesita 12 GB: `full` no está disponible por debajo.

**Cambiar de modelo más adelante.** Ejecuta `imagehearth-mcp setup --quality-model flux-schnell` (o elige otro cuando pregunte). Setup muestra lo que va a descargar y a borrar y te pide confirmar (`--yes` en modo no interactivo). El modelo nuevo se descarga y se verifica **antes** de borrar nada, así que si se interrumpe sigues generando con el anterior; vuelve a ejecutar el comando para terminar. Solo se borran los archivos que instaló ImageHearth y que nada más necesita: tus modelos, los de un ComfyUI adjunto y lo compartido (como los codificadores de texto que usa Kontext) se conservan. Se rechaza mientras se genera una imagen. Desde un agente, `setup_start` con otro `quality_model` hace lo mismo.

**Instalaciones anteriores.** Una instalación hecha antes de esta elección sigue generando: se reconoce como `flux-dev` (fp8 o GGUF) o, si tiene RealVisXL, como un SDXL antiguo. RealVisXL ya no se ofrece; `imagehearth-mcp doctor` te dice cómo pasar a SDXL 1.0 (`setup --quality-model sdxl`), que lo descarga y borra RealVisXL si lo instaló ImageHearth.

Cada imagen generada guarda el modelo de calidad y el workflow en el texto del PNG (`ImageHearth-Quality-Model`, `ImageHearth-Workflow`), junto a lo que escribe ComfyUI. `list_workflows`, `get_engine_status` y `doctor` muestran el modelo activo y su licencia.

Comparativa en la RTX 4090 con los mismos tres prompts y la misma semilla (columnas: FLUX Dev, FLUX Schnell, SDXL 1.0), [imágenes completas](https://github.com/RealHemoglobin/ImageHearth/tree/main/specs/2026-11-06-eleccion-modelo-quality/comparison):

![FLUX Dev, FLUX Schnell y SDXL 1.0 con los mismos prompts y semilla](https://raw.githubusercontent.com/RealHemoglobin/ImageHearth/main/specs/2026-11-06-eleccion-modelo-quality/comparison/grid.jpg)

FLUX Dev y Schnell dibujan el cartel que dice OPEN; SDXL 1.0 no representa el texto. También se probó el refiner de SDXL (base con la LoRA de detalle, con y sin refiner, misma semilla): las imágenes fueron prácticamente idénticas, así que no se instala.

Puedes empezar con `fast` y ejecutar `setup --profile full` más adelante: lo que ya está no se vuelve a descargar. ImageHearth solo ofrece lo instalado: `list_workflows` lo muestra, un `setup` posterior se nota sin reiniciar nada, y pedir algo que falta da un error con el comando de `setup` exacto, nunca otro modelo en su lugar.

| Opción | Uso |
|---|---|
| `--profile fast\|quality\|full` | Elige el perfil sin preguntar. En macOS: `mac-fast\|mac-quality\|mac-full` |
| `--quality-model flux-dev\|flux-schnell\|sdxl` | Modelo de calidad de `quality` o `full`. Sin él, una instalación nueva usa el recomendado y una existente conserva el suyo |
| `--variant fp8\|gguf` | Fuerza la precisión en vez de la que cabe en la memoria de tu GPU |
| `--yes` | Confirma el cambio de modelo de calidad sin preguntar |
| `--experimental` | Obligatorio en macOS, que está sin probar |
| `--accept-licenses` | Acepta las licencias sin preguntar. Obligatoria con `--non-interactive` |
| `--non-interactive` | No pregunta nunca: falla si falta una decisión |
| `--managed` | Instala un ComfyUI propio, aunque exista otro |
| `--attach RUTA` | Usa el ComfyUI que hay en `RUTA` |
| `--install-node` | Permite instalar el nodo de estado en un ComfyUI adjunto |
| `--models-dir RUTA` | Guarda los modelos en `RUTA` y los comparte con `extra_model_paths.yaml` |
| `--port PUERTO` | Puerto en el que escucha ComfyUI |
| `--skip-smoke-test` | No genera la imagen de prueba |

Define `HF_TOKEN` si Hugging Face restringe el acceso a un modelo.

#### macOS (sin probar)

**ImageHearth nunca se ha ejecutado en un Mac, y macOS no tiene soporte.** Para probarlo, añade la opción al instalador: `curl -LsSf https://raw.githubusercontent.com/RealHemoglobin/ImageHearth/main/install.sh | sh -s -- --experimental`. `setup` está preparado para Apple Silicon, con modelos GGUF (`mac-fast` 6,9 GB, `mac-quality` 19,2 GB, `mac-full` 27,6 GB) y el nodo `ComfyUI-GGUF`. Los workflows GGUF se han ejecutado en una GPU NVIDIA, lo que comprueba el grafo y los archivos pero no MPS. Los Mac con Intel no tienen soporte. Si lo pruebas, cuéntanos cómo ha ido, con la salida de `imagehearth-mcp doctor --json`.

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
imagehearth-mcp uninstall
```

Muestra qué va a borrar y borra solo lo que instaló setup. Los modelos necesitan una confirmación aparte (`--remove-models` o `--keep-models` para decidirlo de antemano, `--yes` para saltar la primera pregunta). Un ComfyUI o unos modelos que ya estaban nunca se tocan. Para quitar el propio comando, ejecuta `uv tool uninstall imagehearth-mcp`.

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

## Desarrollo

```bash
uv sync
uv run ruff check .
uv run pytest
```

Hace falta [uv](https://docs.astral.sh/uv/getting-started/installation/), que crea su propio entorno en `.venv`, separado del de ComfyUI. Los tests usan servidores simulados y no necesitan GPU. Consulta [`CONTRIBUTING.md`](https://github.com/RealHemoglobin/ImageHearth/blob/main/CONTRIBUTING.md) para contribuir y el [roadmap](https://github.com/RealHemoglobin/ImageHearth/blob/main/specs/roadmap.md) para ver qué está previsto. Para ayudar a probar la beta, consulta [`docs/beta-testing.md`](https://github.com/RealHemoglobin/ImageHearth/blob/main/docs/beta-testing.md). Para avisar de una vulnerabilidad, consulta [`SECURITY.md`](https://github.com/RealHemoglobin/ImageHearth/blob/main/SECURITY.md).

## Licencia

[MIT](https://github.com/RealHemoglobin/ImageHearth/blob/main/LICENSE), salvo el nodo personalizado de ComfyUI en [`src/imagehearth_mcp/data/imagehearth_status/`](https://github.com/RealHemoglobin/ImageHearth/blob/main/src/imagehearth_mcp/data/imagehearth_status/LICENSE), que es GPL-3.0. Los componentes y modelos de terceros figuran en [`THIRD_PARTY_NOTICES.md`](https://github.com/RealHemoglobin/ImageHearth/blob/main/THIRD_PARTY_NOTICES.md).
