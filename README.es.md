# ImageHearth

**Dale a cualquier agente de IA la capacidad de generar y editar imágenes en tu propio PC.** Sin suscripciones ni nube: tus prompts e imágenes se quedan en tu equipo.

ImageHearth es un servidor [MCP](https://modelcontextprotocol.io) que conecta agentes como Claude Code o Codex con [ComfyUI](https://github.com/Comfy-Org/ComfyUI).

[Read in English](README.md)

> [!WARNING]
> **En desarrollo temprano.** Hoy solo funciona en **Linux con GPU NVIDIA**, y la instalación es manual. Está prevista la instalación con un solo comando para Linux, macOS y Windows: consulta el [roadmap](specs/roadmap.md).

## Qué le puedes pedir a tu agente

- *"Genera un póster de una ciudad futurista de noche"*: borrador rápido con SDXL Turbo.
- *"Haz una imagen de alta calidad de 1536x1024 de un castillo medieval"*: FLUX Dev.
- *"Cambia el fondo de `foto.png` por una montaña nevada"*: FLUX Kontext.
- *"Combina estas tres fotos en una sola escena"*: hasta seis imágenes de referencia.

Si también usas [Ollama](https://ollama.com), ImageHearth libera sus modelos de la memoria de la GPU mientras genera y los restaura después.

## Requisitos

| | |
|---|---|
| **Sistema** | Linux |
| **GPU** | NVIDIA. Solo se ha probado en una RTX 4090 de 24 GB; con menos memoria, los modelos FLUX pueden ir lentos o fallar |
| **Disco** | Unos 45 GB para todo (36,5 GB de modelos). Solo con SDXL Turbo, unos 15 GB |
| **Software** | Git, [uv](https://docs.astral.sh/uv/getting-started/installation/), driver de NVIDIA actualizado y [Ollama](https://ollama.com/download) |

> [!NOTE]
> Por ahora, Ollama debe estar instalado y en marcha aunque no lo uses. [Este requisito desaparecerá](specs/roadmap.md#fase-2-portabilidad-del-núcleo).

## Instalación

Abre una terminal y ejecuta cada paso en orden.

### 1. Instala ComfyUI

```bash
mkdir -p ~/AI && cd ~/AI
git clone https://github.com/Comfy-Org/ComfyUI.git
cd ComfyUI
python3.13 -m venv venv
venv/bin/pip install torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cu130
venv/bin/pip install -r requirements.txt
```

### 2. Instala ImageHearth

```bash
cd ~/AI
git clone https://github.com/RealHemoglobin/ImageHearth.git
cd ImageHearth
uv tool install ./
cp -r src/imagehearth_mcp/data/comfyui_node ~/AI/ComfyUI/custom_nodes/imageengine_status
```

### 3. Configura (opcional)

ImageHearth busca ComfyUI en su propia carpeta de datos (`~/.local/share/imagehearth/comfyui` en Linux). Si lo instalaste en otro sitio, crea `~/.config/imagehearth/config.toml`:

```toml
comfy_dir = "~/AI/ComfyUI"      # dónde está instalado ComfyUI
comfy_port = 8188               # puerto en el que escucha ComfyUI
output_dir = "~/Pictures/ImageHearth"
ollama_url = "http://127.0.0.1:11434"
```

Cada clave también se puede definir con una variable de entorno: `IMAGEHEARTH_COMFY_DIR`, `IMAGEHEARTH_COMFY_PORT`, `IMAGEHEARTH_OUTPUT_DIR` e `IMAGEHEARTH_OLLAMA_URL`. Las variables tienen prioridad sobre el archivo, y el archivo sobre los valores por defecto.

### 4. Descarga los modelos

Descarga solo lo que necesites. Antes, consulta las [licencias](#licencias-de-los-modelos).

```bash
cd ~/AI/ComfyUI/models
HF=https://huggingface.co

# Generación rápida: SDXL Turbo (6,9 GB)
curl -L -C - -o checkpoints/sd_xl_turbo_1.0_fp16.safetensors \
  $HF/stabilityai/sdxl-turbo/resolve/main/sd_xl_turbo_1.0_fp16.safetensors

# Necesarios para FLUX Dev y FLUX Kontext (5,7 GB)
mkdir -p text_encoders vae diffusion_models
curl -L -C - -o text_encoders/clip_l.safetensors \
  $HF/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors
curl -L -C - -o text_encoders/t5xxl_fp8_e4m3fn_scaled.safetensors \
  $HF/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn_scaled.safetensors
curl -L -C - -o vae/ae.safetensors \
  $HF/Comfy-Org/Lumina_Image_2.0_Repackaged/resolve/main/split_files/vae/ae.safetensors

# Alta calidad: FLUX Dev (11,9 GB)
curl -L -C - -o diffusion_models/flux_dev_fp8_scaled_diffusion_model.safetensors \
  $HF/comfyanonymous/flux_dev_scaled_fp8_test/resolve/main/flux_dev_fp8_scaled_diffusion_model.safetensors

# Edición de imágenes: FLUX Kontext (11,9 GB)
curl -L -C - -o diffusion_models/flux1-dev-kontext_fp8_scaled.safetensors \
  $HF/Comfy-Org/flux1-kontext-dev_ComfyUI/resolve/main/split_files/diffusion_models/flux1-dev-kontext_fp8_scaled.safetensors
```

Si se interrumpe una descarga, repite el mismo comando y continuará.

### 5. Conecta tu agente

**Claude Code**

```bash
claude mcp add --scope user imagehearth -- ~/.local/bin/imagehearth-mcp
```

**Codex**: añade esto a `~/.codex/config.toml`, sustituyendo `TU_USUARIO`:

```toml
[mcp_servers.imagehearth]
command = "/home/TU_USUARIO/.local/bin/imagehearth-mcp"
```

**Otros agentes compatibles con MCP**: busca su archivo de configuración de MCP y añade:

```json
{
  "mcpServers": {
    "imagehearth": {
      "command": "/home/TU_USUARIO/.local/bin/imagehearth-mcp"
    }
  }
}
```

**Opcional:** el archivo [`SKILL.md`](src/imagehearth_mcp/data/skill/SKILL.md) enseña a los agentes a sacar mejores resultados. En Claude Code se activa así:

```bash
mkdir -p ~/.claude/skills
ln -s "$("$(uv tool dir)/imagehearth-mcp/bin/python" -c 'from imagehearth_mcp.engine import config; print(config.data_path("skill"))')" ~/.claude/skills/imagehearth
```

### 6. Pruébalo

Reinicia tu agente y pídele:

> Genera una imagen de una bicicleta roja en una playa, con calidad rápida.

ComfyUI arranca solo. La primera imagen tarda más porque tiene que cargar el modelo. Las imágenes se guardan en `~/Pictures/ImageHearth/`.

## Solución de problemas

Pide a tu agente que *"compruebe el estado de ImageHearth"*. El resultado te dice qué ocurre:

| Estado | Significado | Qué hacer |
|---|---|---|
| `ready` | Todo funciona | Nada |
| `busy` | Se está generando otra imagen | Esperar |
| `degraded` | Falta algo | Lee `issues`. Normalmente Ollama no está en marcha o falta el nodo del paso 2 |
| `recovery_required` | Se interrumpió una sesión anterior | Pide a tu agente que *"recupere el motor"* |

| Problema | Solución |
|---|---|
| El agente no ve las herramientas | Reinícialo y revisa la ruta del comando del paso 5 |
| Error de modelo no encontrado | Comprueba que el archivo del paso 4 esté en su carpeta |
| ComfyUI no arranca | Lee `~/.local/state/imagehearth/log/comfyui.log` |
| El puerto 8188 está ocupado | Cierra lo que lo esté usando, o define otro `comfy_port` |

El log de ComfyUI muestra `imageengine_status` como `IMPORT FAILED`. Es un [problema conocido](specs/analysis.md) e inofensivo: el nodo funciona.

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

[MIT](LICENSE), salvo el nodo personalizado de ComfyUI en [`src/imagehearth_mcp/data/comfyui_node/`](src/imagehearth_mcp/data/comfyui_node/LICENSE), que es GPL-3.0. Los componentes y modelos de terceros figuran en [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
