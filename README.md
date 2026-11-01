# ImageHearth

**Give any AI agent the ability to generate and edit images on your own PC.** No subscription, no cloud: your prompts and images stay on your machine.

ImageHearth is an [MCP](https://modelcontextprotocol.io) server that connects agents such as Claude Code or Codex to [ComfyUI](https://github.com/Comfy-Org/ComfyUI).

<!-- mcp-name: io.github.RealHemoglobin/imagehearth -->

[Leer en español](https://github.com/RealHemoglobin/ImageHearth/blob/main/README.es.md)

**Public beta.** Install it with one command, and if something fails, [tell us](https://github.com/RealHemoglobin/ImageHearth/blob/main/docs/troubleshooting.md#reporting-a-problem).

```bash
# Linux
curl -LsSf https://raw.githubusercontent.com/RealHemoglobin/ImageHearth/main/install.sh | sh
```

```powershell
# Windows
irm https://raw.githubusercontent.com/RealHemoglobin/ImageHearth/main/install.ps1 | iex
```

## What you can ask your agent

- *"Generate a poster of a futuristic city at night"*: quick draft with SDXL Turbo.
- *"Make a high-quality 1536x1024 image of a medieval castle"*: FLUX Dev.
- *"Change the background of `photo.png` to a snowy mountain"*: FLUX Kontext.
- *"Combine these three pictures into one scene"*: up to six reference images.

If you also run local language models, ImageHearth frees them from GPU memory while generating and restores them afterwards. Ollama has been tested for real; LM Studio, llama.cpp and vLLM only against simulated servers.

## Requirements

| | |
|---|---|
| **GPU** | NVIDIA series 20 or newer with a current driver. Only measured on an RTX 4090 with 24 GB; see the [measurements](#measured-requirements). Less memory may be slow or fail with the FLUX models |
| **Disk** | 7.2 GB for ComfyUI and its environment, plus the profile you choose |
| **Software** | Nothing to install first: the script installs [uv](https://docs.astral.sh/uv/), which brings its own Python. Git isn't needed. [Ollama](https://ollama.com/download) is optional |

### Support

Only what has run on real hardware is announced as supported.

| System and GPU | Level |
|---|---|
| Linux, NVIDIA series 20 or newer | **Supported.** Tested on real hardware |
| Windows 11, NVIDIA series 20 or newer | **Target of this beta.** Its verification on clean machines is pending |
| NVIDIA series 10 or older, AMD, Intel Arc, CPU only | **Experimental.** Detected and offered with a warning, never tested. CPU only runs `fast` |
| macOS on Apple Silicon | **Untested.** Prepared behind `--experimental`: see [below](#macos-untested) |

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

> **Note:** local model servers are optional. If one isn't running, ImageHearth skips it and the status stays `ready`. See `memory_mode` in the [settings](#settings-optional).

### A language model and images on the same GPU

Measured on the same RTX 4090 with `qwen3.5:9b`, which needs 14.3 GB with Ollama's default context and 5.9 GB with `num_ctx` 8192. With `memory_mode = "auto"` it doesn't matter: the model is unloaded while generating and comes back afterwards. To keep both loaded (`manual` or `off`), the card must hold the language model plus the workflow's peak: with 5.9 GB and SDXL Turbo, the GPU peaked at 19.2 GB, about 3 GB of it from the desktop. With 5.9 GB and FLUX Dev it filled the 24 GB and worked, in 14-16 s, with `memory_mode = "off"`. In `manual`, generation is refused if free memory is below 8 GB for SDXL Turbo or 16 GB for FLUX, so that same case is refused there.

## Installation

### 1. Run the installer

Pick the level you prefer. All three end the same way: uv, `imagehearth-mcp`, `setup` and `connect --detect`.

**Simplest: one command.** Use the one for your system from the [top of this page](#imagehearth).

**From a cloned repository.** Download the code and run `install`, so you can read what it will do first:

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

Without Git, download the ZIP from GitHub and run the same script inside the folder. From a clone, it installs that code, not the published package. If PowerShell blocks the script, run `powershell -ExecutionPolicy Bypass -File .\install.ps1`.

**Most advanced: by hand.** With [uv](https://docs.astral.sh/uv/getting-started/installation/) installed:

```bash
uv tool install imagehearth-mcp==0.1.0b1
imagehearth-mcp setup
imagehearth-mcp connect --detect
```

The scripts are short: [`install.sh`](https://github.com/RealHemoglobin/ImageHearth/blob/main/install.sh) and [`install.ps1`](https://github.com/RealHemoglobin/ImageHearth/blob/main/install.ps1). They:

1. Install uv with its official installer, if it's missing.
2. Install `imagehearth-mcp`: at a pinned version, or the clone's code if run from one.
3. Run `setup` and `connect --detect`, which ask you before downloading or changing anything.

They never ask for `sudo` or administrator rights, and never accept a license for you. You can run them again safely.

### 2. What setup does

Setup detects your hardware and any existing ComfyUI, proposes a profile, and shows the disk space and licenses **before downloading anything**. Then it installs ComfyUI and the models and generates a test image. If it's interrupted, run it again and it continues where it stopped.

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

**ImageHearth has never been run on a Mac, and macOS is not supported.** To try it, add the flag to the installer: `curl -LsSf https://raw.githubusercontent.com/RealHemoglobin/ImageHearth/main/install.sh | sh -s -- --experimental`. Setup is prepared for Apple Silicon, with GGUF models (`mac-fast` 6.9 GB, `mac-quality` 19.2 GB, `mac-full` 27.6 GB) and the `ComfyUI-GGUF` node. The GGUF workflows were run on an NVIDIA GPU, which checks the graph and the files but not MPS. Macs with Intel aren't supported. If you try it, please report how it went, with the output of `imagehearth-mcp doctor --json`.

**Using a ComfyUI you already have.** With `--attach`, or by choosing it when asked, ImageHearth uses it instead of installing another, and doesn't download the models it already has. Your ComfyUI is only changed if you allow the status node to be installed. ComfyUI Desktop has to be open, since ImageHearth can't start it.

### 3. Check, update or remove it

The installer doesn't change your `PATH`. If `imagehearth-mcp` isn't found, run `uv tool update-shell` and open a new terminal.

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

The installer already ran `imagehearth-mcp connect --detect`, which finds the installed clients and offers to connect them. Run it again after installing a new one. You can also run `connect <client>`, or `connect --print <client>` to see the snippet without changing anything. It makes a backup, keeps your other entries and can be repeated.

**Tested:** Claude Code, Codex, opencode, Hermes and pi. **Untested**, checked against their documentation only: Claude Desktop, Gemini CLI, Cursor, VS Code and JetBrains. Details and snippets are in [`docs/agents.md`](https://github.com/RealHemoglobin/ImageHearth/blob/main/docs/agents.md). You can also ask an agent to do the installation with [`llms-install.md`](https://github.com/RealHemoglobin/ImageHearth/blob/main/llms-install.md).

### 5. Try it

Restart your agent and ask:

> Generate an image of a red bicycle on a beach, using the fast quality.

ComfyUI starts on its own. The first image takes longer because the model has to load. Images are saved in `~/Pictures/ImageHearth/`.

## Troubleshooting

Run `imagehearth-mcp doctor`, or ask your agent to *"check the ImageHearth status"*. Common problems and how to report one are in [`docs/troubleshooting.md`](https://github.com/RealHemoglobin/ImageHearth/blob/main/docs/troubleshooting.md).

ImageHearth only restarts or stops a ComfyUI it started itself (it records its PID in the data folder). If you run ComfyUI on the same port, ImageHearth uses it but never restarts it.

## Model licenses

The models are not part of this project and have their own terms. **By downloading them, you accept those terms.** This summary is not legal advice; see [`THIRD_PARTY_NOTICES.md`](https://github.com/RealHemoglobin/ImageHearth/blob/main/THIRD_PARTY_NOTICES.md) for details.

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

This needs [uv](https://docs.astral.sh/uv/getting-started/installation/), which creates its own environment in `.venv`, separate from ComfyUI's. The tests use simulated servers and don't need a GPU. See [`CONTRIBUTING.md`](https://github.com/RealHemoglobin/ImageHearth/blob/main/CONTRIBUTING.md) to contribute, and the [roadmap](https://github.com/RealHemoglobin/ImageHearth/blob/main/specs/roadmap.md) for what's planned. To help test the beta, see [`docs/beta-testing.md`](https://github.com/RealHemoglobin/ImageHearth/blob/main/docs/beta-testing.md). To report a vulnerability, see [`SECURITY.md`](https://github.com/RealHemoglobin/ImageHearth/blob/main/SECURITY.md).

## License

[MIT](https://github.com/RealHemoglobin/ImageHearth/blob/main/LICENSE), except the ComfyUI custom node in [`src/imagehearth_mcp/data/imagehearth_status/`](https://github.com/RealHemoglobin/ImageHearth/blob/main/src/imagehearth_mcp/data/imagehearth_status/LICENSE), which is GPL-3.0. Third-party components and models are listed in [`THIRD_PARTY_NOTICES.md`](https://github.com/RealHemoglobin/ImageHearth/blob/main/THIRD_PARTY_NOTICES.md).
