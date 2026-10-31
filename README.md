# ImageHearth

**Give any AI agent the ability to generate and edit images on your own PC.** No subscription, no cloud: your prompts and images stay on your machine.

ImageHearth is an [MCP](https://modelcontextprotocol.io) server that connects agents such as Claude Code or Codex to [ComfyUI](https://github.com/Comfy-Org/ComfyUI).

[Leer en español](README.es.md)

> [!WARNING]
> **Early development.** Today it only works on **Linux with an NVIDIA GPU**, and installation is manual. One-command installation for Linux, macOS and Windows is planned: see the [roadmap](specs/roadmap.md).

## What you can ask your agent

- *"Generate a poster of a futuristic city at night"*: quick draft with SDXL Turbo.
- *"Make a high-quality 1536x1024 image of a medieval castle"*: FLUX Dev.
- *"Change the background of `photo.png` to a snowy mountain"*: FLUX Kontext.
- *"Combine these three pictures into one scene"*: up to six reference images.

If you also use [Ollama](https://ollama.com), ImageHearth frees its models from GPU memory while generating and restores them afterwards.

## Requirements

| | |
|---|---|
| **System** | Linux. Windows 10/11 with NVIDIA: the code is portable but not verified yet (see the note below). macOS is not supported yet |
| **GPU** | NVIDIA. Only tested on an RTX 4090 with 24 GB; less memory may be slow or fail with the FLUX models |
| **Disk** | About 45 GB for everything (36.5 GB of models). SDXL Turbo alone needs about 15 GB |
| **Software** | Git, [uv](https://docs.astral.sh/uv/getting-started/installation/), an up-to-date NVIDIA driver and, optionally, [Ollama](https://ollama.com/download) |

> [!NOTE]
> Ollama is optional. If it isn't running, ImageHearth skips it and the status stays `ready`. Set `ollama_mode = "off"` to never touch it.
>
> On Windows you install ComfyUI by hand (its venv uses `Scripts\python.exe`) and run `scripts\check.ps1` to verify the checkout. This path is not yet validated on a real machine, so treat it as experimental.

## Installation

Open a terminal and run each step in order.

### 1. Install ComfyUI

```bash
mkdir -p ~/AI && cd ~/AI
git clone https://github.com/Comfy-Org/ComfyUI.git
cd ComfyUI
python3.13 -m venv venv
venv/bin/pip install torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cu130
venv/bin/pip install -r requirements.txt
```

### 2. Install ImageHearth

```bash
cd ~/AI
git clone https://github.com/RealHemoglobin/ImageHearth.git
cd ImageHearth
uv tool install ./
cp -r src/imagehearth_mcp/data/imagehearth_status ~/AI/ComfyUI/custom_nodes/imagehearth_status
```

### 3. Configure (optional)

ImageHearth looks for ComfyUI in its own data folder (`~/.local/share/imagehearth/comfyui` on Linux). If you installed it elsewhere, create `~/.config/imagehearth/config.toml`:

```toml
comfy_dir = "~/AI/ComfyUI"      # where ComfyUI is installed
comfy_port = 8188               # port ComfyUI listens on
output_dir = "~/Pictures/ImageHearth"
ollama_url = "http://127.0.0.1:11434"
ollama_mode = "auto"            # "auto" uses Ollama if it responds; "off" never touches it
```

Each key can also be set with an environment variable: `IMAGEHEARTH_COMFY_DIR`, `IMAGEHEARTH_COMFY_PORT`, `IMAGEHEARTH_OUTPUT_DIR`, `IMAGEHEARTH_OLLAMA_URL` and `IMAGEHEARTH_OLLAMA_MODE`. Variables win over the file, and the file wins over the defaults.

### 4. Download the models

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

### 5. Connect your agent

**Claude Code**

```bash
claude mcp add --scope user imagehearth -- ~/.local/bin/imagehearth-mcp
```

**Codex**: add this to `~/.codex/config.toml`, replacing `YOUR_USER`:

```toml
[mcp_servers.imagehearth]
command = "/home/YOUR_USER/.local/bin/imagehearth-mcp"
```

**Other MCP-compatible agents**: find their MCP settings file and add:

```json
{
  "mcpServers": {
    "imagehearth": {
      "command": "/home/YOUR_USER/.local/bin/imagehearth-mcp"
    }
  }
}
```

**Optional:** the file [`SKILL.md`](src/imagehearth_mcp/data/skill/SKILL.md) tells agents how to get the best results. In Claude Code, enable it with:

```bash
mkdir -p ~/.claude/skills
ln -s "$("$(uv tool dir)/imagehearth-mcp/bin/python" -c 'from imagehearth_mcp.engine import config; print(config.data_path("skill"))')" ~/.claude/skills/imagehearth
```

### 6. Try it

Restart your agent and ask:

> Generate an image of a red bicycle on a beach, using the fast quality.

ComfyUI starts on its own. The first image takes longer because the model has to load. Images are saved in `~/Pictures/ImageHearth/`.

## Troubleshooting

Ask your agent to *"check the ImageHearth status"*. The result tells you what is wrong:

| Status | Meaning | What to do |
|---|---|---|
| `ready` | Everything works | Nothing |
| `busy` | Another image is being generated | Wait |
| `degraded` | Something is missing | Read `issues`. Usually the custom node from step 2 is missing or outdated. Without it generation still works, but GPU memory is checked less reliably |
| `recovery_required` | A previous session was interrupted | Ask your agent to *"recover the engine"* |

| Problem | Solution |
|---|---|
| The agent doesn't see the tools | Restart it and check the command path in step 5 |
| Error about a missing model | Check that the step 4 file is in the right folder |
| ComfyUI doesn't start | Read `~/.local/state/imagehearth/log/comfyui.log` |
| Port 8188 is busy | Close whatever is using it, or set another `comfy_port` |

ImageHearth only restarts or stops a ComfyUI it started itself (it records its PID in the data folder). If you run ComfyUI on the same port, ImageHearth uses it but never restarts it.

## Model licenses

The models are not part of this project and have their own terms. **By downloading them, you accept those terms.** This summary is not legal advice; see [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) for details.

| Model | License | Short version |
|---|---|---|
| FLUX.1 Dev | [FLUX.1 [dev] Non-Commercial](https://bfl.ai/legal/non-commercial-license-terms) | Non-commercial use of the model |
| FLUX.1 Kontext Dev | [FLUX.1 [dev] Non-Commercial](https://bfl.ai/legal/non-commercial-license-terms) | Non-commercial use of the model |
| SDXL Turbo | [Stability AI Community](https://huggingface.co/stabilityai/sdxl-turbo/blob/main/LICENSE.md) | Commercial use requires registration and has a revenue limit |

## Development

```bash
uv sync
uv run ruff check .
uv run pytest
```

This needs [uv](https://docs.astral.sh/uv/getting-started/installation/), which creates its own environment in `.venv`, separate from ComfyUI's. The tests use simulated servers and don't need a GPU. Read the [roadmap](specs/roadmap.md) to see what's planned.

## License

[MIT](LICENSE), except the ComfyUI custom node in [`src/imagehearth_mcp/data/imagehearth_status/`](src/imagehearth_mcp/data/imagehearth_status/LICENSE), which is GPL-3.0. Third-party components and models are listed in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
