# ImageEngine

**Dale a cualquier agente de IA la capacidad de generar y editar imágenes en tu propio PC.** Sin suscripciones ni nube: tus prompts e imágenes se quedan en tu equipo.

ImageEngine es un servidor [MCP](https://modelcontextprotocol.io) que conecta agentes como Claude Code o Codex con [ComfyUI](https://github.com/Comfy-Org/ComfyUI).

[Read in English](README.md)

> [!WARNING]
> **En desarrollo temprano.** Hoy solo funciona en **Linux con GPU NVIDIA**, y la instalación es manual. Está prevista la instalación con un solo comando para Linux, macOS y Windows: consulta el [roadmap](specs/roadmap.md).

## Qué le puedes pedir a tu agente

- *"Genera un póster de una ciudad futurista de noche"*: borrador rápido con SDXL Turbo.
- *"Haz una imagen de alta calidad de 1536x1024 de un castillo medieval"*: FLUX Dev.
- *"Cambia el fondo de `foto.png` por una montaña nevada"*: FLUX Kontext.
- *"Combina estas tres fotos en una sola escena"*: hasta seis imágenes de referencia.

Si también usas [Ollama](https://ollama.com), ImageEngine libera sus modelos de la memoria de la GPU mientras genera y los restaura después.

## Requisitos

| | |
|---|---|
| **Sistema** | Linux |
| **GPU** | NVIDIA. Solo se ha probado en una RTX 4090 de 24 GB; con menos memoria, los modelos FLUX pueden ir lentos o fallar |
| **Disco** | Unos 45 GB para todo (36,5 GB de modelos). Solo con SDXL Turbo, unos 15 GB |
| **Software** | Git, Python 3.13, driver de NVIDIA actualizado y [Ollama](https://ollama.com/download) |

> [!NOTE]
> Por ahora, Ollama debe estar instalado y en marcha aunque no lo uses. [Este requisito desaparecerá](specs/roadmap.md#fase-2-portabilidad-del-núcleo).

## Instalación

Abre una terminal y ejecuta cada paso en orden. De momento las rutas son fijas, así que déjalas como están.

### 1. Instala ComfyUI

```bash
mkdir -p ~/AI && cd ~/AI
git clone https://github.com/Comfy-Org/ComfyUI.git
cd ComfyUI
python3.13 -m venv venv
venv/bin/pip install torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cu130
venv/bin/pip install -r requirements.txt
```

### 2. Instala ImageEngine

Sustituye `OWNER` por el dueño del repositorio.

```bash
cd ~/AI
git clone https://github.com/OWNER/ImageEngine.git
cd ImageEngine
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp -r extras/comfyui_custom_nodes/imageengine_status ~/AI/ComfyUI/custom_nodes/
```

### 3. Descarga los modelos

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

### 4. Conecta tu agente

**Claude Code**

```bash
claude mcp add --scope user imageengine -- ~/AI/ImageEngine/.venv/bin/python ~/AI/ImageEngine/mcp/server.py
```

**Codex**: añade esto a `~/.codex/config.toml`, sustituyendo `TU_USUARIO`:

```toml
[mcp_servers.imageengine]
command = "/home/TU_USUARIO/AI/ImageEngine/.venv/bin/python"
args = ["/home/TU_USUARIO/AI/ImageEngine/mcp/server.py"]
```

**Otros agentes compatibles con MCP**: busca su archivo de configuración de MCP y añade:

```json
{
  "mcpServers": {
    "imageengine": {
      "command": "/home/TU_USUARIO/AI/ImageEngine/.venv/bin/python",
      "args": ["/home/TU_USUARIO/AI/ImageEngine/mcp/server.py"]
    }
  }
}
```

**Opcional:** el archivo [`skill/SKILL.md`](skill/SKILL.md) enseña a los agentes a sacar mejores resultados. En Claude Code se activa así:

```bash
mkdir -p ~/.claude/skills && ln -s ~/AI/ImageEngine/skill ~/.claude/skills/imageengine
```

### 5. Pruébalo

Reinicia tu agente y pídele:

> Genera una imagen de una bicicleta roja en una playa, con calidad rápida.

ComfyUI arranca solo. La primera imagen tarda más porque tiene que cargar el modelo. Las imágenes se guardan en `~/AI/ImageEngine/output/`.

## Solución de problemas

Pide a tu agente que *"compruebe el estado de ImageEngine"*. El resultado te dice qué ocurre:

| Estado | Significado | Qué hacer |
|---|---|---|
| `ready` | Todo funciona | Nada |
| `busy` | Se está generando otra imagen | Esperar |
| `degraded` | Falta algo | Lee `issues`. Normalmente Ollama no está en marcha o falta el nodo del paso 2 |
| `recovery_required` | Se interrumpió una sesión anterior | Pide a tu agente que *"recupere el motor"* |

| Problema | Solución |
|---|---|
| El agente no ve las herramientas | Reinícialo y revisa las rutas del paso 4 |
| Error de modelo no encontrado | Comprueba que el archivo del paso 3 esté en su carpeta |
| ComfyUI no arranca | Lee `~/AI/ImageEngine/logs/comfyui.log` |
| El puerto 8188 está ocupado | Cierra lo que lo esté usando; todavía no se puede cambiar |

El log de ComfyUI muestra `imageengine_status` como `IMPORT FAILED`. Es un [problema conocido](specs/analysis.md) e inofensivo: el nodo funciona.

## Licencias de los modelos

Los modelos no forman parte de este proyecto y tienen sus propias condiciones. **Al descargarlos, las aceptas.** Este resumen no es asesoramiento legal.

| Modelo | Licencia | En resumen |
|---|---|---|
| FLUX.1 Dev | [FLUX.1 [dev] Non-Commercial](https://huggingface.co/black-forest-labs/FLUX.1-dev/blob/main/LICENSE.md) | Uso no comercial del modelo |
| FLUX.1 Kontext Dev | [FLUX.1 [dev] Non-Commercial](https://huggingface.co/black-forest-labs/FLUX.1-Kontext-dev/blob/main/LICENSE.md) | Uso no comercial del modelo |
| SDXL Turbo | [Stability AI Community](https://huggingface.co/stabilityai/sdxl-turbo/blob/main/LICENSE.md) | El uso comercial exige registro y tiene un límite de ingresos |

## Desarrollo

```bash
.venv/bin/python -m unittest discover -s tests
```

Los tests usan servidores simulados y no necesitan GPU. Consulta el [roadmap](specs/roadmap.md) para ver qué está previsto.

## Licencia

Aún sin definir. Hasta que se añada una licencia, este código no se puede reutilizar.
