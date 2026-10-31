# ImageHearth

**Give any AI agent the ability to generate and edit images on your own PC.** No subscription, no cloud: your prompts and images stay on your machine.

ImageHearth is an [MCP](https://modelcontextprotocol.io) server that connects agents such as Claude Code or Codex to [ComfyUI](https://github.com/Comfy-Org/ComfyUI).

[Leer en español](README.es.md)

> [!WARNING]
> **Early development.** `imagehearth-mcp setup` targets **Linux and Windows 11 with an NVIDIA GPU**, and has not been verified on clean machines yet. A one-command installer is planned, and macOS is prepared but has never been run: see the [roadmap](specs/roadmap.md).

## What you can ask your agent

- *"Generate a poster of a futuristic city at night"*: quick draft with SDXL Turbo.
- *"Make a high-quality 1536x1024 image of a medieval castle"*: FLUX Dev.
- *"Change the background of `photo.png` to a snowy mountain"*: FLUX Kontext.
- *"Combine these three pictures into one scene"*: up to six reference images.

If you also run local language models, ImageHearth frees them from GPU memory while generating and restores them afterwards. Ollama has been tested for real; LM Studio, llama.cpp and vLLM only against simulated servers.

## Requirements

| | |
|---|---|
| **System** | Linux or Windows 11. macOS on Apple Silicon is prepared but untested, and not supported: see [below](#macos-untested) |
| **GPU** | NVIDIA series 20 or newer with a current driver. Only measured on an RTX 4090 with 24 GB; see the [measurements](#measured-requirements). Less memory may be slow or fail with the FLUX models. Other GPUs are detected and offered as experimental |
| **Disk** | 7.2 GB for ComfyUI and its environment, plus the profile you choose |
| **Software** | [uv](https://docs.astral.sh/uv/getting-started/installation/). Git and Python aren't needed. [Ollama](https://ollama.com/download) is optional |

### Measured requirements

Measured with `scripts/measure_profiles.py` at 1024x1024 (Kontext with one reference): RTX 4090 24 GB, driver 580.178, Linux, ComfyUI 0.43.0, on 2026-10-31.

| Workflow | Profile | Peak VRAM | Peak RAM | First generation | Next generations |
|---|---|---|---|---|---|
| SDXL Turbo | `fast` | 7.0 GB | 2.6 GB | 3.6 s | 1.0 s |
| FLUX Dev | `quality` | 17.8 GB | 2.3 GB | 13.8 s | 10.4 s |
| FLUX Kontext | `full` | 19.3 GB | 2.4 GB | 21.0 s | 18.6 s |

- These are peaks on a 24 GB card, not minimums: ComfyUI uses the memory it finds and can offload on smaller cards. The minimums for other GPUs are only a guide.
- "First generation" comes after unloading the models from the GPU, with the files still in the system's disk cache. Loading from a cold disk takes longer.
- The Windows measurements are still pending.

> [!NOTE]
> Local model servers are optional. If one isn't running, ImageHearth skips it and the status stays `ready`. See `memory_mode` in the [settings](#settings-optional).

### A language model and images on the same GPU

Measured on the same RTX 4090 with `qwen3.5:9b`, which needs 14.3 GB with Ollama's default context and 5.9 GB with `num_ctx` 8192. With `memory_mode = "auto"` it doesn't matter: the model is unloaded while generating and comes back afterwards. To keep both loaded (`manual` or `off`), the card must hold the language model plus the workflow's peak: with 5.9 GB and SDXL Turbo, the GPU peaked at 19.2 GB, about 3 GB of it from the desktop. With 5.9 GB and FLUX Dev it filled the 24 GB and worked, in 14-16 s, with `memory_mode = "off"`. In `manual`, generation is refused if free memory is below 8 GB for SDXL Turbo or 16 GB for FLUX, so that same case is refused there.

## Installation

### 1. Install ImageHearth

```bash
git clone https://github.com/RealHemoglobin/ImageHearth.git
uv tool install ./ImageHearth
```

### 2. Run setup

```bash
imagehearth-mcp setup
```

It detects your hardware and any existing ComfyUI, proposes a profile, and shows the disk space and licenses **before downloading anything**. Then it installs ComfyUI and the models and generates a test image. If it's interrupted, run it again and it continues where it stopped.

| Profile | What you get | Models |
|---|---|---|
| `fast` | Quick generation with SDXL Turbo | 6.9 GB |
| `quality` | `fast` + FLUX Dev | 24.6 GB |
| `full` | `quality` + editing with FLUX Kontext | 36.5 GB |

You can start with `fast` and run `setup --profile full` later: what's already there isn't downloaded again. ImageHearth only offers what's installed: `list_workflows` shows it, a later `setup` is noticed without restarting anything, and asking for something missing fails with the exact `setup` command, never with another model instead.

| Option | Use |
|---|---|
| `--profile fast\|quality\|full` | Choose the profile without asking. On macOS: `mac-fast\|mac-quality\|mac-full` |
| `--experimental` | Required on macOS, which is untested |
| `--accept-licenses` | Accept the licenses without asking. Required with `--non-interactive` |
| `--non-interactive` | Never ask: fail if a decision is missing |
| `--managed` | Install a ComfyUI of its own, even if another exists |
| `--attach PATH` | Use the existing ComfyUI in `PATH` |
| `--install-node` | Allow installing the status node in an attached ComfyUI |
| `--models-dir PATH` | Keep the models in `PATH`, shared through `extra_model_paths.yaml` |
| `--port PORT` | Port ComfyUI listens on |
| `--skip-smoke-test` | Don't generate the test image |

Set `HF_TOKEN` if Hugging Face restricts access to a model.

#### macOS (untested)

**ImageHearth has never been run on a Mac, and macOS is not supported.** Setup is prepared for Apple Silicon behind `--experimental`, with GGUF models (`mac-fast` 6.9 GB, `mac-quality` 19.2 GB, `mac-full` 27.6 GB) and the `ComfyUI-GGUF` node. The GGUF workflows were run on an NVIDIA GPU, which checks the graph and the files but not MPS. Macs with Intel aren't supported. If you try it, please report how it went, with the output of `imagehearth-mcp doctor --json`.

**Using a ComfyUI you already have.** With `--attach`, or by choosing it when asked, ImageHearth uses it instead of installing another, and doesn't download the models it already has. Your ComfyUI is only changed if you allow the status node to be installed. ComfyUI Desktop has to be open, since ImageHearth can't start it.

### 3. Check, update or remove it

```bash
imagehearth-mcp doctor
```

It checks each layer and says how to fix what fails. Add `--json` for a stable format, or `--verify-hashes` to compare the SHA-256 of each model instead of its size. It exits with a non-zero code if something fails.

```bash
imagehearth-mcp update
```

It applies the ComfyUI version and models pinned by this version of ImageHearth. An attached ComfyUI is left alone, except for a status node that setup installed.

```bash
imagehearth-mcp uninstall
```

It shows what it will remove and removes only what setup and `connect` installed. Models need a separate confirmation (`--remove-models` or `--keep-models` to decide in advance, `--yes` to skip the first question). A ComfyUI or models that were already there are never touched. To remove the command itself, run `uv tool uninstall imagehearth-mcp`.

### Settings (optional)

`setup` writes what it needs in `~/.config/imagehearth/config.toml` on Linux and `%APPDATA%\imagehearth\config.toml` on Windows. You can also edit it:

```toml
comfy_dir = "~/AI/ComfyUI"      # where ComfyUI is installed
comfy_port = 8188               # port ComfyUI listens on
output_dir = "~/Pictures/ImageHearth"
ollama_url = "http://127.0.0.1:11434"
memory_mode = "auto"            # "auto", "off" or "manual", see below
lmstudio_url = "http://127.0.0.1:1234"
llamacpp_url = "http://127.0.0.1:8080"
vllm_url = "http://127.0.0.1:8000"
```

Each key can also be set with an environment variable: `IMAGEHEARTH_COMFY_DIR`, `IMAGEHEARTH_COMFY_PORT`, `IMAGEHEARTH_OUTPUT_DIR`, `IMAGEHEARTH_OLLAMA_URL`, `IMAGEHEARTH_LMSTUDIO_URL`, `IMAGEHEARTH_LLAMACPP_URL`, `IMAGEHEARTH_VLLM_URL` and `IMAGEHEARTH_MEMORY_MODE`. Variables win over the file, and the file wins over the defaults.

| `memory_mode` | What happens to your language models |
|---|---|
| `auto` | Unloaded before generating and restored afterwards. If a server can't unload (see below), you get a warning with what to do, or an error before starting if the memory isn't enough |
| `manual` | Never touched. Generation fails with an explanation if the free memory isn't enough |
| `off` | Never touched, and memory isn't checked |

The older `ollama_mode` still works as an alias for `auto` or `off`; `memory_mode` wins if both are set.

| Server | Can ImageHearth free its memory? |
|---|---|
| Ollama | Yes |
| LM Studio | Yes, with its REST API v1. Older versions: warning only |
| llama.cpp | Only in router mode. A single-model `llama-server` can't unload: warning only |
| vLLM | Only when started with `VLLM_SERVER_DEV_MODE=1` and `--enable-sleep-mode`. Otherwise: warning only |

### 4. Connect your agent

```bash
imagehearth-mcp connect --detect
```

It finds the installed clients and offers to connect them. You can also run `connect <client>`, or `connect --print <client>` to see the snippet without changing anything. It makes a backup, keeps your other entries and can be repeated.

**Tested:** Claude Code, Codex, opencode, Hermes and pi. **Untested**, checked against their documentation only: Claude Desktop, Gemini CLI, Cursor, VS Code and JetBrains. Details and snippets are in [`docs/agents.md`](docs/agents.md). You can also ask an agent to do the installation with [`llms-install.md`](llms-install.md).

### 5. Try it

Restart your agent and ask:

> Generate an image of a red bicycle on a beach, using the fast quality.

ComfyUI starts on its own. The first image takes longer because the model has to load. Images are saved in `~/Pictures/ImageHearth/`.

## Troubleshooting

Run `imagehearth-mcp doctor`, or ask your agent to *"check the ImageHearth status"*. The result tells you what is wrong:

| Status | Meaning | What to do |
|---|---|---|
| `ready` | Everything works | Nothing |
| `not_installed` | ComfyUI or the models are missing | Run the command in `issues`, or ask your agent to install it |
| `busy` | Another image is being generated | Wait |
| `degraded` | Something is missing | Read `issues`. Usually the status node is missing or outdated. Without it generation still works, but GPU memory is checked less reliably |
| `recovery_required` | A previous session was interrupted | Ask your agent to *"recover the engine"* |

| Problem | Solution |
|---|---|
| The agent doesn't see the tools | Restart it and check the command path in step 4 |
| Error about a model that isn't installed | Run the `imagehearth-mcp setup --profile ...` command in the error |
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
