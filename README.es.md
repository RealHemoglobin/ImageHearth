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
- *"Haz una imagen de alta calidad de 1536x1024 de un castillo medieval"*: FLUX Dev.
- *"Cambia el fondo de `foto.png` por una montaña nevada"*: FLUX Kontext.
- *"Combina estas tres fotos en una sola escena"*: hasta seis imágenes de referencia.

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
| FLUX Kontext | `full` | 19,3 GB | 2,4 GB | 21,0 s | 18,6 s |

- Son picos en una tarjeta de 24 GB, no mínimos: ComfyUI usa la memoria que encuentra y puede descargar parte en tarjetas menores. Los mínimos para otras GPU son solo orientativos.
- La «primera generación» es tras descargar los modelos de la GPU, con los archivos aún en la caché de disco del sistema. Cargar desde un disco en frío tarda más.
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
uv tool install imagehearth-mcp==0.1.0b1
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
| `quality` | `fast` + FLUX Dev | 24,6 GB |
| `full` | `quality` + edición con FLUX Kontext | 36,5 GB |

Puedes empezar con `fast` y ejecutar `setup --profile full` más adelante: lo que ya está no se vuelve a descargar. ImageHearth solo ofrece lo instalado: `list_workflows` lo muestra, un `setup` posterior se nota sin reiniciar nada, y pedir algo que falta da un error con el comando de `setup` exacto, nunca otro modelo en su lugar.

| Opción | Uso |
|---|---|
| `--profile fast\|quality\|full` | Elige el perfil sin preguntar. En macOS: `mac-fast\|mac-quality\|mac-full` |
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

El instalador no cambia tu `PATH`. Si no encuentra `imagehearth-mcp`, ejecuta `uv tool update-shell` y abre otra terminal.

```bash
imagehearth-mcp doctor
```

Comprueba cada capa e indica cómo arreglar lo que falle. Añade `--json` para un formato estable, o `--verify-hashes` para comparar el SHA-256 de cada modelo en lugar de su tamaño. Termina con un código distinto de cero si algo falla.

```bash
imagehearth-mcp update
```

Aplica la versión de ComfyUI y los modelos que fija esta versión de ImageHearth. Un ComfyUI adjunto no se toca, salvo el nodo de estado que haya instalado setup.

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
