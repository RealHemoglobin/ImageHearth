# ImageHearth

**Give any AI agent the ability to generate and edit images on your own PC.** No subscription, no cloud: your prompts and images stay on your machine.

ImageHearth is an [MCP](https://modelcontextprotocol.io) server that connects agents such as Claude Code or Codex to [ComfyUI](https://github.com/Comfy-Org/ComfyUI).

<!-- mcp-name: io.github.RealHemoglobin/imagehearth -->

[Leer en español](https://github.com/RealHemoglobin/ImageHearth/blob/main/README.es.md)

Install it with one command, and if something fails, [tell us](https://github.com/RealHemoglobin/ImageHearth/blob/main/docs/troubleshooting.md#reporting-a-problem). Versions follow [semantic versioning](https://github.com/RealHemoglobin/ImageHearth/blob/main/docs/versioning.md).

```bash
# Linux
curl -LsSf https://raw.githubusercontent.com/RealHemoglobin/ImageHearth/main/install.sh | sh
```

```powershell
# Windows
irm https://raw.githubusercontent.com/RealHemoglobin/ImageHearth/main/install.ps1 | iex
```

## What you can ask your agent

- *"Generate a poster of a futuristic city at night"*: quick draft with the fast model you installed (SDXL Turbo, Z-Image-Turbo or FLUX.2 Klein 4B).
- *"Make a high-quality 1536x1024 image of a medieval castle"*: the quality model you installed (Qwen-Image, Chroma1-HD, HiDream, FLUX or SDXL 1.0).
- *"Change the background of `photo.png` to a snowy mountain"*: the editing model you installed (FLUX.2 Klein 4B, Qwen-Image-Edit or FLUX Kontext).
- *"Do it with Chroma"* / *"use the Klein model"*: with several models installed, the agent can pick one by name.
- *"Combine these three pictures into one scene"*: up to six reference images.

### Several images at once

When your agent already knows it needs several independent images, it passes a list of prompts to `create_image` in a single call. The GPU is prepared once for the whole batch: language models are unloaded and restored once and ComfyUI starts once, instead of repeating that for every image.

> Make four fast variations of a logo, and two high-quality posters, 1024x768.

Each list item is a prompt, or an object with its own prompt, quality and size. A batch is all new images or all edits, never both, and its items cannot depend on each other (a chain of edits needs one call after another). The whole batch is checked before anything is generated, and one failing image does not stop the rest: the answer has one line per image, in the order asked (`1: /path/image.png` or `2: ERROR: reason`).

By default a batch has at most 20 images, so one agent does not hold the GPU for too long. Change it with `imagehearth-mcp setup --batch-limit N`; `imagehearth-mcp doctor` shows the limit in use. Measured on an RTX 4090 (24 GB) with a 26B Ollama model loaded, one batch against the same images in separate calls:

| Images | Separate calls | One batch | Saved |
|---|---|---|---|
| 4 `fast` + 2 `high` | 86.5 s (6 unloads of the model) | 42.1 s (1 unload) | 44.4 s (51 %) |
| 3 Kontext edits of a 3536x2352 photo | 566.2 s | 550.3 s | 15.9 s (3 %) |

The saving is the language model's unload and reload and ComfyUI's startup, roughly 7 s per image here. It matters for quick generations and almost disappears for slow ones: each edit of a large photo takes about three minutes, which dwarfs the setup. Cancelling a batch halfway kept the finished images, restored the model and freed the GPU.

If you also run local language models, ImageHearth frees them from GPU memory while generating and restores them afterwards. Ollama has been tested for real; LM Studio, llama.cpp and vLLM only against simulated servers.

## Requirements

| | |
|---|---|
| **GPU** | NVIDIA series 20 or newer with a current driver (AMD Radeon RX 7000 and 9000 series is experimental on Windows; see [Support](#support)). Only measured on an RTX 4090 with 24 GB; see the [measurements](#measured-requirements). Less memory may be slow or fail with the FLUX models |
| **Disk** | 7.2 GB for ComfyUI and its environment, plus the profile you choose |
| **Software** | Nothing to install first: the script installs [uv](https://docs.astral.sh/uv/), which brings its own Python. Git isn't needed. [Ollama](https://ollama.com/download) is optional |

### Support

Only what has run on real hardware is announced as supported. Level 1 is supported, level 2 is expected to work, and level 3 is experimental or untested.

| System and GPU | Level |
|---|---|
| Windows 11, NVIDIA series 20 or newer | **1. Supported.** Tested on real hardware |
| Linux, NVIDIA series 20 or newer | **1. Supported.** Tested on real hardware (RTX 4090) |
| Windows 11, AMD Radeon RX 7000 and 9000 series | **3. Experimental.** Installed automatically with AMD's own ROCm packages (about 5 GB, estimated), never tested on a real Radeon. Needs a current AMD driver. Cards: RX 9060 (gfx1200), RX 9070 (gfx1201), RX 7900 (gfx1100), RX 7800/7700 (gfx1101), RX 7600 (gfx1102), Radeon 780M/760M/740M (gfx1103) |
| Linux, AMD | **3. Experimental.** ROCm 7.2 packages from PyTorch, never tested |
| Windows, other AMD cards (RX 6000 and older) | **Not installed by setup.** Install ComfyUI by hand and use `--attach` |
| NVIDIA series 10 or older, Intel Arc, CPU only | **3. Experimental.** Detected and offered with a warning, never tested. CPU only runs `fast` |
| macOS on Apple Silicon | **3. Untested.** Prepared behind `--experimental`: see [below](#macos-untested) |

### Measured requirements

Measured with `scripts/measure_profiles.py` at 1024x1024 (Kontext with one reference): RTX 4090 24 GB, driver 580.178, Linux, ComfyUI 0.43.0, on 2026-10-31.

| Workflow | Profile | Peak VRAM | Peak RAM | First generation | Next generations |
|---|---|---|---|---|---|
| SDXL Turbo | `fast` | 7.0 GB | 2.6 GB | 3.6 s | 1.0 s |
| FLUX Dev | `quality` | 17.8 GB | 2.3 GB | 13.8 s | 10.4 s |
| FLUX Schnell | `quality` | 19.4 GB | 2.3 GB | 5.2 s | 2.8 s |
| SDXL 1.0 | `quality` | 9.6 GB | 2.7 GB | 5.7 s | 4.0 s |
| FLUX Kontext | `full` | 19.3 GB | 2.4 GB | 21.0 s | 18.6 s |

- These are peaks on a 24 GB card, not minimums: ComfyUI uses the memory it finds and can offload on smaller cards. The minimums for other GPUs are only a guide.
- "First generation" comes after unloading the models from the GPU, with the files still in the system's disk cache. Loading from a cold disk takes longer.
- FLUX Schnell and SDXL 1.0 were measured on 2026-11-06 on the same card (FLUX Dev again on that day: 19.4 GB, 12.8 s and 10.3 s; the earlier row used a lighter desktop). FLUX Schnell with ComfyUI limited to about 12 GB (`--reserve-vram 12`) peaked at 12.3 GB and kept 2.8 s per image, so 12 GB holds; that was simulated by reserving memory on the 24 GB card, not measured on a real 12 GB card.
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
uv tool install --python 3.13 imagehearth-mcp==1.0.0
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

| Profile | What you get |
|---|---|
| `fast` | Quick generation: one or more **fast** models |
| `quality` | `fast` + one or more models for **high-quality** generation |
| `full` | `quality` + one or more **editing** models |

The download size depends on the models you choose, from about 7 GB (SDXL Turbo alone) to well over 100 GB with several large ones. Setup shows the total, what is already there and the free space before it asks you to accept anything.

#### Choosing the models

**Answering the questions.** Each question lists numbered options: press a number to choose it (no Enter), or Enter for the recommended one. Yes/no questions take one key (`y`, `s` or `n`). **0 goes back** to the previous question with your answers kept; on the first one it exits without changing anything. Every question shows `Step N of M`, and nothing is written or downloaded until you accept the final summary. Ctrl+C leaves at any point without a trace. Without a terminal (a pipe, some IDEs) or with `--non-interactive`, setup reads a number and Enter per line, or needs the options on the command line.

Each capability the profile has (**fast**, **quality** and, with `full`, **editing**) gets its own multiple choice (arrow keys, Space to mark, Enter to accept) with **one or more** models. On a new installation only the model recommended for your GPU is marked; on an existing one, the installed ones are. Each line shows the download size and the time per image measured for your GPU level, the license and whether it allows commercial use. Then, for each model with more than one **precision**, a menu shows each precision's size, time, GPU memory and how much would move to system RAM at your level (the recommended one is the best that fits without moving weights to RAM). If you marked several models in a capability, you pick which is the **default**: what `create_image` uses when it isn't told a model. Before you confirm, setup shows the plan with the space it needs against the free space and, if models are replaced, what will be deleted and why; without enough space it refuses to continue.

Times are seconds per 1024x1024 image with the model already loaded, measured on an RTX 4090 limited to 8, 16 and 24 GB (and the whole card for 32+ GB, which only differs where weights no longer move to RAM). A `*` means part of the model went to system RAM at that level. Details and method: [the analysis](https://github.com/RealHemoglobin/ImageHearth/blob/main/specs/2026-11-15-analisis-modelos/analysis.md). An em dash means not measured.

| Model | `name` | Precision | Download | 8 GB | 16 GB | 24 GB | 32+ GB | License | Commercial use |
|---|---|---|---|---|---|---|---|---|---|
| **Fast** | | | | | | | | | |
| SDXL Turbo | `sdxl-turbo` | fp16 | 6.9 GB | — | — | — | — | [Stability AI Community](https://huggingface.co/stabilityai/sdxl-turbo/blob/main/LICENSE.md) | With registration; license needed above USD 1M a year |
| Z-Image-Turbo | `z-image-turbo` | int8 | 12.2 GB | 2.0 s | 2.0 s | 2.0 s | 2.0 s | [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0) | Yes |
| Z-Image-Turbo | `z-image-turbo` | bf16 | 20.7 GB | 4.1 s* | 3.6 s | 3.6 s | 3.6 s | Apache-2.0 | Yes |
| FLUX.2 Klein 4B | `klein-4b` | bf16 | 16.1 GB | 1.5 s | 1.3 s | 1.3 s | 1.3 s | Apache-2.0 | Yes |
| **Quality** | | | | | | | | | |
| SDXL 1.0 | `sdxl` | fp16 | 7.0 GB | — | — | — | — | [CreativeML Open RAIL++-M](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/blob/main/LICENSE.md) | Yes, with use restrictions |
| FLUX.1 Dev | `flux-dev` | fp8 / GGUF Q5 | 17.6 / 12.3 GB | — | — | — | — | [FLUX [dev] Non-Commercial](https://bfl.ai/legal/non-commercial-license-terms) | **No** |
| FLUX.1 Schnell | `flux-schnell` | fp8 | 17.6 GB | — | — | — | — | Apache-2.0 | Yes |
| Chroma1-HD | `chroma-hd` | fp8 | 14.7 GB | 19.3 s | 17.7 s | 17.7 s | 17.7 s | Apache-2.0 | Yes |
| Chroma1-HD | `chroma-hd` | bf16 | 23.3 GB | 37.5 s* | 27.4 s | 25.9 s | 25.9 s | Apache-2.0 | Yes |
| Qwen-Image | `qwen-image` | Q2_K | 16.7 GB | 44.3 s | 35.7 s | 35.8 s | 35.8 s | Apache-2.0 | Yes |
| Qwen-Image | `qwen-image` | Q4_K_M | 22.7 GB | 60.3 s | 39.9 s | 38.3 s | 37.3 s | Apache-2.0 | Yes |
| Qwen-Image | `qwen-image` | fp8 | 30.1 GB | 30.8 s* | 26.2 s* | 24.3 s | 24.3 s | Apache-2.0 | Yes |
| Qwen-Image | `qwen-image` | bf16 | 50.5 GB | 53.6 s* | 40.7 s* | 33.2 s* | 33.6 s* | Apache-2.0 | Yes |
| HiDream-I1 Full | `hidream-full` | Q4_K_M | 27.7 GB | 95.7 s* | 76.7 s | 77.8 s | 78.5 s | [MIT](https://opensource.org/license/mit) + [Llama 3.1](https://www.llama.com/llama3_1/license/) | Yes (Llama conditions) |
| HiDream-I1 Full | `hidream-full` | fp8 | 33.3 GB | 73.1 s* | 68.4 s | 67.7 s | 64.4 s | MIT + Llama 3.1 | Yes (Llama conditions) |
| **Editing** | | | | | | | | | |
| FLUX.1 Kontext Dev | `kontext` | fp8 / GGUF Q5 | 17.6 / 12.4 GB | — | — | — | — | FLUX [dev] Non-Commercial | **No** |
| FLUX.2 Klein 4B | `klein-4b` | bf16 | 16.1 GB | 2.5 s | 2.5 s | 2.5 s | 2.5 s | Apache-2.0 | Yes |
| Qwen-Image-Edit-2511 | `qwen-image-edit` | Q4_K_M | 22.5 GB | 173 s | 140 s | 137 s | 137 s | Apache-2.0 | Yes |
| Qwen-Image-Edit-2511 | `qwen-image-edit` | fp8 | 30.2 GB | 120.8 s* | 112.5 s* | 112.9 s | 112.9 s | Apache-2.0 | Yes |

Download sizes include the text encoder and the VAE, which several models share (they are downloaded once). Unmeasured precisions are not offered: HiDream fp16 and Qwen-Image-Edit bf16.

**Recommended for each level of GPU memory** (marked and preselected, but you can choose anything):

| GPU memory | Fast | Quality | Editing |
|---|---|---|---|
| 8 GB | FLUX.2 Klein 4B | Chroma1-HD fp8 | FLUX.2 Klein 4B |
| 16 GB | Z-Image-Turbo bf16 | Qwen-Image Q4_K_M | FLUX.2 Klein 4B |
| 24 GB | Z-Image-Turbo bf16 | Qwen-Image fp8 | Qwen-Image-Edit fp8 |
| 32 GB or more | Z-Image-Turbo bf16 | Qwen-Image fp8 | Qwen-Image-Edit fp8 |

Every recommendation has a license that allows commercial use, and a complete installation with generation and editing under such licenses exists at every level.

Notes:

- With a model that doesn't fit your GPU you can still install it: setup warns you with the minimum and the memory it found, and the last word is yours. Editing and the GGUF precisions need ComfyUI-GGUF, which setup installs (pinned) when a model needs it.
- The licenses setup asks you to accept are only those of what it downloads. HiDream's text encoder is Llama 3.1 8B: its license (with the "Built with Llama" notice) is listed, and in non-interactive mode `--accept-licenses` is required. If a repository starts asking for approval or a token, setup says so and you can set `HF_TOKEN`. **FLUX Dev and Kontext are non-commercial.**
- FLUX.1 Dev and Kontext use fp8 with 20 GB or more and GGUF Q5 with 12 to 20 GB. FLUX.2 Klein 4B and Qwen-Image-Edit edit one reference image at a time; FLUX Kontext takes up to six.
- Qwen-Image-Edit takes two to three minutes per image at any level and changes more than it is asked to (it relights the scene); FLUX.2 Klein 4B is the only one that edits in seconds. Klein wrote "OPPEN" in the sign prompt of the comparison.
- Quality comparison, image grids and the measurements are in [the analysis](https://github.com/RealHemoglobin/ImageHearth/blob/main/specs/2026-11-15-analisis-modelos/analysis.md).

**On the command line** (non-interactive mode too), each capability takes a comma-separated list of `name[:precision]`; the first is the default. Without a precision, setup uses the one already installed or the one recommended for your GPU:

```bash
imagehearth-mcp setup --profile full \
  --fast-models klein-4b,sdxl-turbo \
  --quality-models qwen-image:q4_k_m,chroma-hd:fp8 \
  --edit-models klein-4b
```

A wrong name or precision fails before anything is downloaded and lists the valid ones. Without any of these options, a new installation gets the recommended model of each capability (and says so); an existing one keeps what it has. `--quality-model NAME` still works as `--quality-models NAME`.

**Changing the models later.** On an existing installation a list **fixes the set** of that capability: setup downloads what is missing, verifies it, and only then deletes what you left out or replaced (also when you change a precision). It shows what it will download and delete, and why, and asks you to confirm (`--yes` in non-interactive mode). Adding models needs no confirmation. Capabilities you don't pass are left alone. Only files that ImageHearth installed and that no remaining model needs are deleted: your own models, the models of an attached ComfyUI and anything shared stay. It's refused while an image is being generated. From an agent, `setup_start` takes `fast_models`, `quality_models` and `edit_models` and does the same.

**Older installations.** An installation made before this choice keeps generating, with nothing downloaded or deleted: SDXL Turbo is its fast model, its quality model (FLUX Dev, FLUX Schnell or SDXL 1.0; or an old SDXL with RealVisXL) the quality one and Kontext, if it has it, the editing one, each as the default. RealVisXL is no longer offered; `imagehearth-mcp doctor` tells you how to move to SDXL 1.0 (`setup --quality-models sdxl`).

**Asking for a model.** `create_image(prompt="a fox", model="klein-4b")` uses an installed model; `quality: "high"` or `image_paths` say which capability it must have, and without `model` the default of that capability is used. `list_workflows` lists every installed model with its capability, precision, whether it is the default, license, commercial use and measured seconds. An unknown, not installed, wrong-capability or `workflow`-combined `model` fails before touching the GPU and says what is installed and the command that installs the rest. In a list of prompts, `model` can be set per item or for all. LoRAs only work with `sdxl`.

Every generated image records the model (`ImageHearth-Model`, as `name:precision`), the quality model and the workflow in its PNG text (`ImageHearth-Quality-Model`, `ImageHearth-Workflow`), next to what ComfyUI writes. `list_workflows` and `doctor` show the installed models and their licenses, and `get_engine_status` the default quality model.

#### Style LoRAs (SDXL 1.0 only)

With `sdxl` among the quality models, setup also offers small **style LoRAs**: pixel art, paper cut, line art, pencil, crayon, 3D, clay and a few more. They are optional and none is installed unless you choose it. They only work with SDXL 1.0 (`quality: "high"`, `model: "sdxl"` or as the default): not with the other models, `fast` or editing. Interactive setup adds a step after the model with a multiple choice that shows each one's category, size and license (numbers separated by commas, Enter to keep the marked ones, `none` for none, 0 goes back). Non-interactive: `--loras name1,name2`, `--loras all` or `--loras none`. On an existing installation `--loras` **fixes the set**: it downloads the ones that are missing and deletes the ones that aren't listed (only files that ImageHearth downloaded; your own files in `models/loras` are never touched). Without `--loras` the LoRAs stay as they are. Removing SDXL 1.0 deletes them too, and the confirmation says so. Through an agent, `setup_status` lists them under `loras` and `setup_start` takes `loras` (`["all"]` or a list).

The agent finds the installed ones in `list_workflows` (the `sdxl` item has a `loras` list) and uses them with `create_image(prompt="a lighthouse at dawn", quality="high", loras=["pixel-art"])`, or with a weight from 0 to 2: `loras=[{"name": "crayon", "weight": 0.6}]`. At most 3 per image, each once; a name alone uses its recommended weight; in a list of prompts, `loras` can be set per item or for all. The activation words the LoRA needs are added to the prompt for you, and `style: "auto"` adds no photographic cues when a LoRA asks for another medium. A request that can't use LoRAs (another model, `fast`, editing, a name that isn't installed) fails before touching the GPU and says why. Each PNG records them in `ImageHearth-LoRAs`.

Each one was chosen after measuring it on the RTX 4090 against the same text without the LoRA (same prompt and seed), and only those whose license allows commercial use are offered. Left out because they didn't beat the prompt alone: there is **no watercolor and no "detail" LoRA** (SDXL already draws a good watercolor from the text, and the candidates were worse). The reasons and every candidate tried are in [the selection](https://github.com/RealHemoglobin/ImageHearth/blob/main/specs/2026-11-15-loras-sdxl/seleccion-loras.md). Same prompt and seed in every row (`a red fox sitting in a snowy forest at dawn`); the LoRA at its recommended weight. The licenses are those of each publisher, with use restrictions that must be passed on: see [THIRD_PARTY_NOTICES.md](https://github.com/RealHemoglobin/ImageHearth/blob/main/THIRD_PARTY_NOTICES.md).

| Name | Category | License | Size | Without | With |
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

You can start with `fast` and run `setup --profile full` later: what's already there isn't downloaded again. ImageHearth only offers what's installed: `list_workflows` shows it, a later `setup` is noticed without restarting anything, and asking for something missing fails with the exact `setup` command, never with another model instead.

| Option | Use |
|---|---|
| `--profile fast\|quality\|full` | Choose the profile without asking. On macOS: `mac-fast\|mac-quality\|mac-full` |
| `--fast-models`, `--quality-models`, `--edit-models` | Models of each capability, as `name[:precision],...`; the first is the default. Without them, a new install uses the recommended ones and an existing one keeps its models. `--quality-model NAME` is the old form |
| `--loras NAMES` | Style LoRAs for SDXL 1.0: names separated by commas, `all` or `none`. On an existing installation it fixes the set (downloads the missing ones, deletes the others). Without it, nothing changes |
| `--variant fp8\|gguf` | Precision for the models that don't name one with `name:precision`, where they have it, instead of the recommended one |
| `--yes` | Confirm switching the quality model without asking |
| `--experimental` | Required on macOS, which is untested |
| `--accept-licenses` | Accept the licenses without asking. Required with `--non-interactive` |
| `--non-interactive` | Never ask: fail if a decision is missing |
| `--managed` | Install a ComfyUI of its own, even if another exists |
| `--attach PATH` | Use the existing ComfyUI in `PATH` |
| `--install-node` | Allow installing the status node in an attached ComfyUI |
| `--install-dir PATH` | Install ComfyUI in `PATH/comfyui`, and the models in `PATH/comfyui/models` unless `--models-dir` says otherwise. Not compatible with `--attach` |
| `--models-dir PATH` | Keep the models in `PATH`, shared through `extra_model_paths.yaml` |
| `--port PORT` | Port ComfyUI listens on |
| `--skip-smoke-test` | Don't generate the test image |

Set `HF_TOKEN` if Hugging Face restricts access to a model.

#### macOS (untested)

**ImageHearth has never been run on a Mac, and macOS is not supported.** To try it, add the flag to the installer: `curl -LsSf https://raw.githubusercontent.com/RealHemoglobin/ImageHearth/main/install.sh | sh -s -- --experimental`. Setup is prepared for Apple Silicon, with GGUF models (`mac-fast` 6.9 GB, `mac-quality` 19.2 GB, `mac-full` 27.6 GB) and the `ComfyUI-GGUF` node. The GGUF workflows were run on an NVIDIA GPU, which checks the graph and the files but not MPS. Macs with Intel aren't supported. If you try it, please report how it went, with the output of `imagehearth-mcp doctor --json`.

**Choosing where it is installed.** ComfyUI and the models take tens of GB. Interactive `setup` asks for the folder after the mode: the usual place (recommended), the other disks it finds with their free space, or a path you type. Nothing is created until you confirm. With `--install-dir PATH` it doesn't ask. Before downloading, `setup` checks that it can write there, that there is room, and that the file system holds the files: FAT32 can't hold files over 4 GB, so it refuses; network and removable drives, and on Windows paths with spaces or non-ASCII characters, only get a warning, and a path too long for Windows is refused unless long paths are enabled. The folder is saved in `config.toml` and `install.json`, so `update`, `doctor` and `uninstall` use it; `uninstall` deletes it only if `setup` created it and it ends up empty. A different folder on an existing installation is refused: use `update --move-to`. Through an agent, `setup_status` lists the folders and `setup_start` accepts `install_dir`.

**Using a ComfyUI you already have.** With `--attach`, or by choosing it when asked, ImageHearth uses it instead of installing another, and doesn't download the models it already has. Your ComfyUI is only changed if you allow the status node to be installed. ComfyUI Desktop has to be open, since ImageHearth can't start it.

### 3. Check, update or remove it

The installer runs `uv tool update-shell` if a new terminal wouldn't find `imagehearth-mcp`; open a new terminal afterwards. `imagehearth-mcp doctor` checks it and prints the exact command for your shell if something is still missing.

```bash
imagehearth-mcp doctor
```

It checks each layer and says how to fix what fails. Add `--json` for a stable format, or `--verify-hashes` to compare the SHA-256 of each model instead of its size. It exits with a non-zero code if something fails.

```bash
imagehearth-mcp update
```

**To get a new version of ImageHearth itself**, run the installer again: it replaces the installed version with the one it pins, keeps your configuration, models and connected agents, and doesn't download what is already there. Then restart your agent. (By hand: `uv tool install --python 3.13 --force imagehearth-mcp`.) This command applies the ComfyUI version and models pinned by the installed version of ImageHearth. An attached ComfyUI is left alone, except for a status node that setup installed.

```bash
imagehearth-mcp update --move-to D:\ImageHearth
```

**To move an installation to another folder or disk**, `update --move-to PATH` moves the ComfyUI that ImageHearth installed and the models it downloaded to `PATH/comfyui`. It shows what moves, its size and the free space, and asks once (`--yes` skips it). It refuses while an image is being generated or an installation is running, and stops ComfyUI. On the same disk it renames; on another it copies, checks size and SHA-256, creates the Python environment again and deletes the old files only at the end. Until then it keeps working from the old folder, so if it is interrupted (Ctrl+C, power cut) run the same command to continue, or `update --move-to` with the current folder to cancel it. It leaves alone an attached ComfyUI and models ImageHearth didn't download. Restart your agents afterwards so they read the new folder. `imagehearth-mcp doctor` shows the install folder, the disk and the free space, and warns about a move left half done.

```bash
imagehearth-mcp uninstall
```

It shows what it will remove and removes only what setup and `connect` installed. Models need a separate confirmation (`--remove-models` or `--keep-models` to decide in advance, `--yes` to skip the first question). A ComfyUI or models that were already there are never touched. It also looks in every agent for ImageHearth entries (`imagehearth` and the old name `imageengine`) and skills that `connect` didn't record, in every Claude Code scope. It removes the ones that run ImageHearth, asking first unless you pass `--yes`; an entry that runs another program, a modified skill and a project's `.mcp.json` are left alone and reported with the command to remove them. Restart the agents you have open afterwards. To remove the command itself, run `uv tool uninstall imagehearth-mcp`. If something still shows up, `imagehearth-mcp doctor` lists every entry it finds (see [troubleshooting](https://github.com/RealHemoglobin/ImageHearth/blob/main/docs/troubleshooting.md#common-problems)).

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
batch_limit = 20                # most images per create_image call
```

Each key can also be set with an environment variable: `IMAGEHEARTH_COMFY_DIR`, `IMAGEHEARTH_COMFY_PORT`, `IMAGEHEARTH_OUTPUT_DIR`, `IMAGEHEARTH_OLLAMA_URL`, `IMAGEHEARTH_LMSTUDIO_URL`, `IMAGEHEARTH_LLAMACPP_URL`, `IMAGEHEARTH_VLLM_URL`, `IMAGEHEARTH_BATCH_LIMIT` and `IMAGEHEARTH_MEMORY_MODE`. Variables win over the file, and the file wins over the defaults.

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
| Z-Image-Turbo, FLUX.2 Klein 4B, Chroma1-HD, Qwen-Image, Qwen-Image-Edit, FLUX.1 Schnell | [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0) | Permissive: commercial use allowed |
| HiDream-I1 Full | [MIT](https://opensource.org/license/mit) | Permissive. Its text encoder is Llama 3.1 (next row) |
| Llama 3.1 8B (HiDream's text encoder) | [Llama 3.1 Community](https://www.llama.com/llama3_1/license/) | Commercial use with conditions; show "Built with Llama" if you redistribute |

## Development

```bash
uv sync
uv run ruff check .
uv run pytest
```

This needs [uv](https://docs.astral.sh/uv/getting-started/installation/), which creates its own environment in `.venv`, separate from ComfyUI's. The tests use simulated servers and don't need a GPU. See [`CONTRIBUTING.md`](https://github.com/RealHemoglobin/ImageHearth/blob/main/CONTRIBUTING.md) to contribute, and the [roadmap](https://github.com/RealHemoglobin/ImageHearth/blob/main/specs/roadmap.md) for what's planned. To help test the beta, see [`docs/beta-testing.md`](https://github.com/RealHemoglobin/ImageHearth/blob/main/docs/beta-testing.md). To report a vulnerability, see [`SECURITY.md`](https://github.com/RealHemoglobin/ImageHearth/blob/main/SECURITY.md).

## License

[MIT](https://github.com/RealHemoglobin/ImageHearth/blob/main/LICENSE), except the ComfyUI custom node in [`src/imagehearth_mcp/data/imagehearth_status/`](https://github.com/RealHemoglobin/ImageHearth/blob/main/src/imagehearth_mcp/data/imagehearth_status/LICENSE), which is GPL-3.0. Third-party components and models are listed in [`THIRD_PARTY_NOTICES.md`](https://github.com/RealHemoglobin/ImageHearth/blob/main/THIRD_PARTY_NOTICES.md).
