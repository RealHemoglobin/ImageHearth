# ImageEngine

**Give any AI agent the ability to generate and edit images on your own PC.** No subscription, no cloud: your prompts and images stay on your machine.

ImageEngine is an [MCP](https://modelcontextprotocol.io) server that connects agents such as Claude Code or Codex to [ComfyUI](https://github.com/Comfy-Org/ComfyUI).

[Leer en español](README.es.md)

> [!WARNING]
> **Early development.** Today it only works on **Linux with an NVIDIA GPU**, and installation is manual. One-command installation for Linux, macOS and Windows is planned: see the [roadmap](specs/roadmap.md).

## What you can ask your agent

- *"Generate a poster of a futuristic city at night"*: quick draft with SDXL Turbo.
- *"Make a high-quality 1536x1024 image of a medieval castle"*: FLUX Dev.
- *"Change the background of `photo.png` to a snowy mountain"*: FLUX Kontext.
- *"Combine these three pictures into one scene"*: up to six reference images.

If you also use [Ollama](https://ollama.com), ImageEngine frees its models from GPU memory while generating and restores them afterwards.

## Requirements

| | |
|---|---|
| **System** | Linux |
| **GPU** | NVIDIA. Only tested on an RTX 4090 with 24 GB; less memory may be slow or fail with the FLUX models |
| **Disk** | About 45 GB for everything (36.5 GB of models). SDXL Turbo alone needs about 15 GB |
| **Software** | Git, Python 3.13, an up-to-date NVIDIA driver and [Ollama](https://ollama.com/download) |

> [!NOTE]
> Ollama must be installed and running for now, even if you don't use it. This requirement [will be removed](specs/roadmap.md#fase-2-portabilidad-del-núcleo).

## Installation

Open a terminal and run each step in order. The paths are currently fixed, so please keep them as they are.

### 1. Install ComfyUI

```bash
mkdir -p ~/AI && cd ~/AI
git clone https://github.com/Comfy-Org/ComfyUI.git
cd ComfyUI
python3.13 -m venv venv
venv/bin/pip install torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cu130
venv/bin/pip install -r requirements.txt
```

### 2. Install ImageEngine

Replace `OWNER` with the repository owner.

```bash
cd ~/AI
git clone https://github.com/OWNER/ImageEngine.git
cd ImageEngine
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp -r extras/comfyui_custom_nodes/imageengine_status ~/AI/ComfyUI/custom_nodes/
```

### 3. Download the models

Download only what you need. Check the [licenses](#model-licenses) first.

```bash
cd ~/AI/ComfyUI/models
HF=https://huggingface.co

# Quick generation: SDXL Turbo (6.9 GB)
curl -L -C - -o checkpoints/sd_xl_turbo_1.0_fp16.safetensors \
  $HF/stabilityai/sdxl-turbo/resolve/main/sd_xl_turbo_1.0_fp16.safetensors

# Needed by both FLUX Dev and FLUX Kontext (5.7 GB)
mkdir -p text_encoders vae diffusion_models
curl -L -C - -o text_encoders/clip_l.safetensors \
  $HF/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors
curl -L -C - -o text_encoders/t5xxl_fp8_e4m3fn_scaled.safetensors \
  $HF/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn_scaled.safetensors
curl -L -C - -o vae/ae.safetensors \
  $HF/Comfy-Org/Lumina_Image_2.0_Repackaged/resolve/main/split_files/vae/ae.safetensors

# High quality: FLUX Dev (11.9 GB)
curl -L -C - -o diffusion_models/flux_dev_fp8_scaled_diffusion_model.safetensors \
  $HF/comfyanonymous/flux_dev_scaled_fp8_test/resolve/main/flux_dev_fp8_scaled_diffusion_model.safetensors

# Image editing: FLUX Kontext (11.9 GB)
curl -L -C - -o diffusion_models/flux1-dev-kontext_fp8_scaled.safetensors \
  $HF/Comfy-Org/flux1-kontext-dev_ComfyUI/resolve/main/split_files/diffusion_models/flux1-dev-kontext_fp8_scaled.safetensors
```

If a download is interrupted, run the same command again and it will continue.

### 4. Connect your agent

**Claude Code**

```bash
claude mcp add --scope user imageengine -- ~/AI/ImageEngine/.venv/bin/python ~/AI/ImageEngine/mcp/server.py
```

**Codex**: add this to `~/.codex/config.toml`, replacing `YOUR_USER`:

```toml
[mcp_servers.imageengine]
command = "/home/YOUR_USER/AI/ImageEngine/.venv/bin/python"
args = ["/home/YOUR_USER/AI/ImageEngine/mcp/server.py"]
```

**Other MCP-compatible agents**: find their MCP settings file and add:

```json
{
  "mcpServers": {
    "imageengine": {
      "command": "/home/YOUR_USER/AI/ImageEngine/.venv/bin/python",
      "args": ["/home/YOUR_USER/AI/ImageEngine/mcp/server.py"]
    }
  }
}
```

**Optional:** the file [`skill/SKILL.md`](skill/SKILL.md) tells agents how to get the best results. In Claude Code, enable it with:

```bash
mkdir -p ~/.claude/skills && ln -s ~/AI/ImageEngine/skill ~/.claude/skills/imageengine
```

### 5. Try it

Restart your agent and ask:

> Generate an image of a red bicycle on a beach, using the fast quality.

ComfyUI starts on its own. The first image takes longer because the model has to load. Images are saved in `~/AI/ImageEngine/output/`.

## Troubleshooting

Ask your agent to *"check the ImageEngine status"*. The result tells you what is wrong:

| Status | Meaning | What to do |
|---|---|---|
| `ready` | Everything works | Nothing |
| `busy` | Another image is being generated | Wait |
| `degraded` | Something is missing | Read `issues`. Usually Ollama isn't running or the custom node from step 2 is missing |
| `recovery_required` | A previous session was interrupted | Ask your agent to *"recover the engine"* |

| Problem | Solution |
|---|---|
| The agent doesn't see the tools | Restart it and check the paths in step 4 |
| Error about a missing model | Check that the step 3 file is in the right folder |
| ComfyUI doesn't start | Read `~/AI/ImageEngine/logs/comfyui.log` |
| Port 8188 is busy | Close whatever is using it; the port can't be changed yet |

ComfyUI's log shows `imageengine_status` as `IMPORT FAILED`. This is a [known issue](specs/analysis.md) and it's harmless: the node works.

## Model licenses

The models are not part of this project and have their own terms. **By downloading them, you accept those terms.** This summary is not legal advice.

| Model | License | Short version |
|---|---|---|
| FLUX.1 Dev | [FLUX.1 [dev] Non-Commercial](https://huggingface.co/black-forest-labs/FLUX.1-dev/blob/main/LICENSE.md) | Non-commercial use of the model |
| FLUX.1 Kontext Dev | [FLUX.1 [dev] Non-Commercial](https://huggingface.co/black-forest-labs/FLUX.1-Kontext-dev/blob/main/LICENSE.md) | Non-commercial use of the model |
| SDXL Turbo | [Stability AI Community](https://huggingface.co/stabilityai/sdxl-turbo/blob/main/LICENSE.md) | Commercial use requires registration and has a revenue limit |

## Development

```bash
.venv/bin/python -m unittest discover -s tests
```

The tests use simulated servers and don't need a GPU. Read the [roadmap](specs/roadmap.md) to see what's planned.

## License

Not yet defined. Until a license is added, this code can't be reused.
