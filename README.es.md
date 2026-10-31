# ImageHearth

**Dale a cualquier agente de IA la capacidad de generar y editar imágenes en tu propio PC.** Sin suscripciones ni nube: tus prompts e imágenes se quedan en tu equipo.

ImageHearth es un servidor [MCP](https://modelcontextprotocol.io) que conecta agentes como Claude Code o Codex con [ComfyUI](https://github.com/Comfy-Org/ComfyUI).

[Read in English](README.md)

> [!WARNING]
> **En desarrollo temprano.** `imagehearth-mcp setup` está pensado para **Linux y Windows 11 con GPU NVIDIA**, y aún no se ha verificado en máquinas limpias. El instalador de un comando está previsto, y macOS está preparado pero nunca se ha ejecutado: consulta el [roadmap](specs/roadmap.md).

## Qué le puedes pedir a tu agente

- *"Genera un póster de una ciudad futurista de noche"*: borrador rápido con SDXL Turbo.
- *"Haz una imagen de alta calidad de 1536x1024 de un castillo medieval"*: FLUX Dev.
- *"Cambia el fondo de `foto.png` por una montaña nevada"*: FLUX Kontext.
- *"Combina estas tres fotos en una sola escena"*: hasta seis imágenes de referencia.

Si también usas modelos de lenguaje locales, ImageHearth los libera de la memoria de la GPU mientras genera y los restaura después. Ollama se ha probado de verdad; LM Studio, llama.cpp y vLLM, solo con servidores simulados.

## Requisitos

| | |
|---|---|
| **Sistema** | Linux o Windows 11. macOS con Apple Silicon está preparado pero sin probar, y no tiene soporte: consulta [más abajo](#macos-sin-probar) |
| **GPU** | NVIDIA serie 20 o posterior con un controlador actual. Solo medido en una RTX 4090 de 24 GB; consulta las [mediciones](#requisitos-medidos). Con menos memoria puede ir lento o fallar con los modelos FLUX. Otras GPU se detectan y se ofrecen como experimentales |
| **Disco** | 7,2 GB para ComfyUI y su entorno, más el perfil que elijas |
| **Software** | [uv](https://docs.astral.sh/uv/getting-started/installation/). No hacen falta Git ni Python. [Ollama](https://ollama.com/download) es opcional |

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

> [!NOTE]
> Los servidores de modelos locales son opcionales. Si uno no está en marcha, ImageHearth lo ignora y el estado sigue siendo `ready`. Consulta `memory_mode` en los ajustes.

### Un modelo de lenguaje e imágenes en la misma GPU

Medido en la misma RTX 4090 con `qwen3.5:9b`, que necesita 14,3 GB con el contexto por defecto de Ollama y 5,9 GB con `num_ctx` 8192. Con `memory_mode = "auto"` da igual: el modelo se descarga mientras se genera y vuelve después. Para tener los dos cargados (`manual` u `off`), la tarjeta debe albergar el modelo de lenguaje más el pico del workflow: con 5,9 GB y SDXL Turbo, la GPU llegó a 19,2 GB, unos 3 GB de ellos del escritorio. Con 5,9 GB y FLUX Dev llenó los 24 GB y funcionó, en 14-16 s, con `memory_mode = "off"`. En `manual`, la generación se rechaza si hay menos de 8 GB libres para SDXL Turbo o de 16 GB para FLUX, así que ese mismo caso se rechaza ahí.

## Instalación

### 1. Instala ImageHearth

```bash
git clone https://github.com/RealHemoglobin/ImageHearth.git
uv tool install ./ImageHearth
```

### 2. Ejecuta setup

```bash
imagehearth-mcp setup
```

Detecta tu hardware y cualquier ComfyUI existente, propone un perfil y muestra el espacio y las licencias **antes de descargar nada**. Después instala ComfyUI y los modelos y genera una imagen de prueba. Si se interrumpe, vuelve a ejecutarlo y continúa donde se quedó.

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

**ImageHearth nunca se ha ejecutado en un Mac, y macOS no tiene soporte.** `setup` está preparado para Apple Silicon tras `--experimental`, con modelos GGUF (`mac-fast` 6,9 GB, `mac-quality` 19,2 GB, `mac-full` 27,6 GB) y el nodo `ComfyUI-GGUF`. Los workflows GGUF se han ejecutado en una GPU NVIDIA, lo que comprueba el grafo y los archivos pero no MPS. Los Mac con Intel no tienen soporte. Si lo pruebas, cuéntanos cómo ha ido, con la salida de `imagehearth-mcp doctor --json`.

**Usar un ComfyUI que ya tienes.** Con `--attach`, o eligiéndolo cuando te pregunte, ImageHearth lo usa en lugar de instalar otro y no descarga los modelos que ya tiene. Tu ComfyUI solo cambia si permites instalar el nodo de estado. ComfyUI Desktop debe estar abierto, porque ImageHearth no puede arrancarlo.

### 3. Compruébalo, actualízalo o elimínalo

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

```bash
imagehearth-mcp connect --detect
```

Busca los clientes instalados y ofrece conectarlos. También puedes usar `connect <cliente>`, o `connect --print <cliente>` para ver el fragmento sin tocar nada. Hace copia de seguridad, conserva tus demás entradas y se puede repetir.

**Probados:** Claude Code, Codex, opencode, Hermes y pi. **Sin probar**, contrastados solo con su documentación: Claude Desktop, Gemini CLI, Cursor, VS Code y JetBrains. Detalles y fragmentos en [`docs/agents.md`](docs/agents.md). También puedes pedirle la instalación a un agente con [`llms-install.md`](llms-install.md).

### 5. Pruébalo

Reinicia tu agente y pídele:

> Genera una imagen de una bicicleta roja en una playa, con calidad rápida.

ComfyUI arranca solo. La primera imagen tarda más porque tiene que cargar el modelo. Las imágenes se guardan en `~/Pictures/ImageHearth/`.

## Solución de problemas

Pide a tu agente que *"compruebe el estado de ImageHearth"*. El resultado te dice qué ocurre:

| Estado | Significado | Qué hacer |
|---|---|---|
| `ready` | Todo funciona | Nada |
| `busy` | Se está generando otra imagen | Esperar |
| `degraded` | Falta algo | Lee `issues`. Normalmente falta el nodo de estado o está desactualizado. Sin él la generación funciona, pero la memoria de la GPU se comprueba con menos fiabilidad |
| `not_installed` | Faltan ComfyUI o los modelos | Ejecuta el comando de `issues`, o pide a tu agente que lo instale |
| `recovery_required` | Se interrumpió una sesión anterior | Pide a tu agente que *"recupere el motor"* |

| Problema | Solución |
|---|---|
| El agente no ve las herramientas | Reinícialo y revisa la ruta del comando del paso 4 |
| Error de un modelo que no está instalado | Ejecuta el comando `imagehearth-mcp setup --profile ...` que indica el error |
| ComfyUI no arranca | Lee `~/.local/state/imagehearth/log/comfyui.log` |
| El puerto 8188 está ocupado | Cierra lo que lo esté usando, o define otro `comfy_port` |

ImageHearth solo reinicia o detiene un ComfyUI que haya lanzado él mismo (guarda su PID en la carpeta de datos). Si ejecutas ComfyUI en el mismo puerto, lo usa pero nunca lo reinicia.

## Licencias de los modelos

Los modelos no forman parte de este proyecto y tienen sus propias condiciones. **Al descargarlos, las aceptas.** Este resumen no es asesoramiento legal; los detalles están en [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

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

Hace falta [uv](https://docs.astral.sh/uv/getting-started/installation/), que crea su propio entorno en `.venv`, separado del de ComfyUI. Los tests usan servidores simulados y no necesitan GPU. Consulta el [roadmap](specs/roadmap.md) para ver qué está previsto.

## Licencia

[MIT](LICENSE), salvo el nodo personalizado de ComfyUI en [`src/imagehearth_mcp/data/imagehearth_status/`](src/imagehearth_mcp/data/imagehearth_status/LICENSE), que es GPL-3.0. Los componentes y modelos de terceros figuran en [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
