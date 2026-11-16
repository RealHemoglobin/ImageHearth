---
name: imagehearth
description: Generate, edit and compose images using the centralized ImageHearth MCP service. Use for all image creation and editing tasks.
---

# ImageHearth

## Purpose

ImageHearth is the centralized image generation and editing engine shared by all AI agents.

It uses ComfyUI as the image generation backend, with models of three kinds ("capabilities"). The user installs one or more of each, and one of them is the default:

- **Fast** (`quality="fast"`): SDXL Turbo, Z-Image-Turbo or FLUX.2 Klein 4B. Seconds per image.
- **High quality** (`quality="high"`): SDXL 1.0 (takes negative prompts and LoRAs), FLUX Dev (non-commercial), FLUX Schnell, Chroma1-HD, Qwen-Image (good at text in images) or HiDream-I1 Full.
- **Editing** (`image_paths`): FLUX.2 Klein 4B (seconds, one reference), Qwen-Image-Edit (minutes, one reference, changes more than asked) or FLUX Kontext (non-commercial, up to six references).

What is available depends on the profile the user installed: `fast` has only the fast models, `quality` adds the quality ones and `full` adds editing. `list_workflows` shows the installed models and which one is the default of each capability. Changing the set is `imagehearth-mcp setup --fast-models ... --quality-models ... --edit-models ...` (names with an optional `:precision`), or `setup_start` with `fast_models`, `quality_models` and `edit_models`: a list fixes the set of that capability, so tell the user what it replaces.

- A centralized orchestration layer for GPU memory management.
- MCP as the agent-independent interface.

The server's own instructions and tool descriptions are enough to use it. This skill only adds detail.

All agents MUST use ImageHearth MCP tools for image operations.

Never implement a separate ComfyUI integration.

## Main tool: create_image

Prefer `create_image` for normal image generation and editing tasks.

Parameters:

- `prompt` (string or array, required): Description of the desired image or edit. An array makes several images in one call (see below).
- `mode` (string, optional): `auto`, `generate` or `edit`. Default: `auto`.
- `quality` (string, optional): `fast` or `high`. Default: `fast`.
- `image_paths` (array of strings, optional): Up to six reference image paths.
- `model` (string, optional): An installed model from `list_workflows` to use instead of the default of what the request needs. See "Choosing a model".
- `workflow` (string, optional): Explicit generation workflow override. Leave empty; it can't be combined with `model`.
- `width` (integer, optional): Output width. Default: automatic.
- `height` (integer, optional): Output height. Default: automatic.
- `negative_prompt` (string, optional): Elements to avoid during generation. SDXL, Chroma1-HD, Qwen-Image and HiDream apply it; the FLUX and Z-Image models and editing return a warning.
- `style` (string, optional): `auto`, `photo` or `none`. Photographic cues for FLUX Schnell and SDXL 1.0. Default: `auto`.
- `loras` (array, optional): Style LoRAs, only with `quality="high"` and the SDXL 1.0 model. See "Style LoRAs".
- `include_image` (boolean, optional): Also return the picture, for models with vision. Default: false, because it uses context. The path stays on the first line.

### Automatic routing

When `mode="auto"`:

- No reference images: generate a new image.
- One or more reference images: edit or compose with the installed editing model (the default one unless you pass `model`).

When `mode="generate"`:

- Generate a new image.
- Reference images are not accepted.

When `mode="edit"`:

- At least one reference image is required.
- Uses the installed editing model (the default one, or `model`).
- FLUX Kontext supports up to six reference images; FLUX.2 Klein 4B and Qwen-Image-Edit take one, and keep its size (`width` and `height` are ignored with a warning).

### Quality selection

For generation without references:

- `fast`: the default fast model.
- `high`: the default quality model. FLUX Schnell and SDXL 1.0 draw painterly unless told otherwise: `style="auto"` (default) adds photographic cues unless the prompt names another medium, but for realism still write the prompt like a photograph (subject, light, lens).

Quality does not change the editing model: editing uses the installed editing model.

### Choosing a model

Several models can be installed for each capability. Without `model`, `create_image` uses the default of the capability the request needs (fast, high quality, or editing when there are `image_paths`).

1. When the user asks for a specific model ("use Chroma", "with Klein"), or you want to know what is installed (speed, license, what each is for), call `list_workflows` once. Each item has `model` (the name to pass), `capability`, `precision`, `default`, `license`, `commercial_use` and, when measured, `seconds` per image on this GPU.
2. Pass the `model` name: `create_image(prompt="a fox", quality="high", model="chroma-hd")`. In a list of prompts, `model` can be set per item or as a common value.
3. The model must be installed and have the capability the request needs. Otherwise the call fails before touching the GPU, says what is installed and the `imagehearth-mcp setup` command that installs the rest: tell the user, it needs them to run it. Never invent a name, never use another model without being asked, and don't combine `model` with `workflow`.
4. If the user doesn't care, don't pass `model`. Use the `commercial_use` field when the user needs commercial images: FLUX Dev and Kontext are not.

### Style LoRAs

With SDXL 1.0 as the quality model, the user can install small style LoRAs (pixel art, watercolor, anime, extra detail...). When the user asks for a style:

1. Call `list_workflows` and look at the item with `model: "sdxl"`. It has a `loras` list of the installed ones: `name`, `description`, `category`, `trigger_words` and the recommended `weight`.
2. If one fits, pass it in `create_image` with `quality="high"` (and `model="sdxl"` if SDXL 1.0 isn't the default): `loras=["pixel-art"]`, or with a weight (0 to 2): `loras=[{"name": "watercolor", "weight": 0.6}]`. At most 3 per image, each once. A name alone uses its recommended weight.
3. Do not add the activation words yourself: they are added to the prompt if missing. `style="auto"` adds no photographic cues when a LoRA asks for another medium.
4. Never invent a name. If none fits or the list is empty, generate without LoRAs. If the user wants a LoRA that is not installed, the error names the command (`imagehearth-mcp setup --loras ...`): tell the user, it needs them to run it.

LoRAs do not work with `quality="fast"`, with any model but SDXL 1.0, or with editing: the call fails before touching the GPU and the error says why. In a list of prompts, `loras` can be set per item or as a common value, like the other fields. The PNG records them in `ImageHearth-LoRAs`.

### Dimensions

For generation:
- Default: 1024x1024.
- Specify width and height when a different aspect ratio is required.
- Limits: 64 to 4096 per side and 8,388,608 pixels in total.

For editing:
- Default: preserve the dimensions of the first reference image.
- Explicit width and height override the output dimensions.
- A reference above the limits is reduced, keeping its proportions, and the result includes a warning.

### Examples

Fast generation:

    create_image(
        prompt="A futuristic city at night, cinematic lighting",
        quality="fast"
    )

High-quality generation:

    create_image(
        prompt="A detailed photorealistic medieval castle",
        quality="high",
        width=1536,
        height=1024
    )

Edit one image:

    create_image(
        prompt="Change the background to a snowy mountain landscape",
        image_paths=["/path/to/image.png"]
    )

Combine multiple references:

    create_image(
        prompt="Combine the main subjects into one coherent scene. Do not create a collage.",
        image_paths=[
            "/path/to/reference1.png",
            "/path/to/reference2.png",
            "/path/to/reference3.png"
        ]
    )

## Several images: a list of prompts

`create_image` is the only image tool. When you need two or more independent images, make ONE `create_image` call and pass a list as `prompt`. Never call it once per image. The call returns when every image is done, and the GPU is prepared only once for the whole list (language models unloaded and restored once, ComfyUI started once), which is much faster.

- `prompt` (string or array): a list item is either a string, or an object with its own `prompt` and, if needed, `quality`, `width`, `height`, `negative_prompt`, `image_paths`, `workflow`, `mode`.
- `quality`, `width`, `height`, `negative_prompt`, `image_paths`, `workflow`, `mode` at the top level are common values for every item that does not set its own. A value in an item wins.
- `include_image` is not accepted with a list: open the files you need to look at.

Rules:

- Items are independent. An item cannot use the result of another one: a chain of edits (edit A, then edit the result) must be successive calls.
- A list is all generations or all edits (`image_paths`), never both. Send generations and edits as separate calls.
- The whole list is validated before anything runs. If one item is invalid, nothing is generated and the error lists every problem as `Item N: ...` (N starts at 1).
- At most 20 items by default; the user can change it with `imagehearth-mcp setup --batch-limit N`. The error says the limit.

Example:

    create_image(
        prompt=[
            "A red fox in a snowy forest",
            {"prompt": "A detailed medieval castle", "quality": "high"},
            {"prompt": "A lighthouse at dawn", "negative_prompt": "people"}
        ],
        quality="fast",
        width=1024,
        height=768
    )

The result has one line per item, in the order you gave:

    1: /home/user/Pictures/ImageHearth/a1b2c3.png
    2: ERROR: ComfyUI error: ...
    3: /home/user/Pictures/ImageHearth/d4e5f6.png | WARNING: sdxl_turbo ignores negative_prompt.
    WARNING: ...

- `N: /path` is an image that exists; `N: ERROR: reason` is one that failed. A failure does not affect the other items: retry only the failed ones.
- `| WARNING:` after a path is a warning for that image; do not retry because of it.
- `WARNING:` lines at the end apply to the whole call.
- If the engine stops or the request is cancelled, the items not run say `ERROR: not attempted` or `ERROR: cancelled`; the finished ones are kept.
- Tell the user every path.

## Other tools

### list_workflows

List the installed models, one item per model (`model`, `capability`, `precision`, `default`, `license`, `commercial_use`, `seconds`). The `sdxl` item also has the installed style `loras`.

Use this tool to inspect what is installed and to pick a `model` for `create_image`. It is checked on every call, so a later `setup` shows up without a restart.

The editing templates are internal and cannot be selected as a workflow. Use `create_image` with `image_paths` (and `model`) for editing.

### get_engine_status

Check the current state of:
- ComfyUI.
- Ollama and the other local model servers, under `memory`, with the `memory_mode` in use.
- Loaded models.
- GPU devices and VRAM information exposed by ComfyUI.
- The overall `imageengine.status`:
  - `ready`: operational.
  - `not_installed`: see `imageengine.issues`, or call `setup_status`.
  - `busy`: another generation holds the engine.
  - `degraded`: a dependency has a problem; see `imageengine.issues`.
  - `recovery_required`: an earlier session left work pending; see `imageengine.session`.

Use this tool when:
- A generation fails.
- A service appears unavailable.
- The current engine state needs verification.

### ensure_comfyui

Start ComfyUI if it is not already running.

Use when ComfyUI is stopped or unavailable.

### recover_engine

Resolve a pending session: release ComfyUI and restore the interrupted language models. It never reloads them while ComfyUI may still hold GPU memory.

Use only when `get_engine_status` reports `recovery_required`.

### setup_status and setup_start

`setup_status` shows what is installed, what is missing, each profile's size and licenses, and the progress of an installation. It changes nothing.

`setup_start` installs ComfyUI and a profile. It needs `profile` and `accept_licenses`, refuses experimental profiles, and keeps running if the agent disconnects.

Before calling `setup_start`, tell the user the profile, the models of each capability (`models` in `setup_status`: precisions with size, measured seconds per image on this GPU, license, commercial use, fit and which is recommended; they can choose several, the first is the default), the total download size and the licenses (HiDream also downloads Meta's Llama 3.1 text encoder under its own license), and wait for their clear yes. Never accept licenses or choose models on their behalf. Pass the choice in `fast_models`, `quality_models` and `edit_models`, each a list of `name` or `name:precision`. On an existing installation a list fixes the set of that capability: what isn't listed is deleted after the new models are verified, so list the installed ones to keep. Omitted or empty: that capability is left as it is.

If the user chooses SDXL 1.0 (`sdxl`), also ask whether they want style LoRAs and which: `setup_status` lists them under `loras` with category, size and license. Pass the chosen names in `loras` (`["all"]` for every one). On an existing installation `loras` fixes the set: the ones not listed are deleted, so include the installed ones to keep. An empty list changes nothing.

## Image creation guidelines

1. Understand the user's intended subject and purpose.
2. Select the appropriate aspect ratio and dimensions.
3. Use `create_image`. For several independent images, pass a list of prompts in one call.
4. Choose `fast` for drafts and quick iterations.
5. Choose `high` for detailed final images.
6. Write precise prompts describing composition, lighting, style, environment and constraints.
7. Avoid adding unrequested text, logos or unrelated elements.

## Image editing guidelines

1. Use `create_image` with reference images.
2. Supply the exact source image paths.
3. Describe the requested modifications precisely.
4. Explicitly identify elements that must remain unchanged.
5. For multiple references, explain how their visual elements should be combined.
6. Request a coherent composition rather than a collage when appropriate.
7. Maintain visual consistency across iterative design tasks.

## GPU memory management

ImageHearth manages GPU memory centrally.

The orchestration layer:
- Serializes generation sessions.
- Follows `memory_mode` (`auto`, `off` or `manual`, in `config.toml` or `IMAGEHEARTH_MEMORY_MODE`; `ollama_mode` still works as an alias, and `memory_mode` wins):
  - `auto`: unloads the models of Ollama, LM Studio, llama.cpp router mode and vLLM with sleep mode before generating, and restores them afterwards. A server that isn't running is skipped and the status is not `degraded`. If a server can't unload its model, a warning says what to do, or the generation fails before starting if the memory is not enough.
  - `manual`: never touches the user's models and fails before generating, with an explanation, if the free memory is not enough.
  - `off`: never touches the user's models and doesn't check memory.
- Executes ComfyUI workflows.
- Releases ComfyUI models after generation.
- Records each session on disk so an interrupted one can be recovered.
- If ComfyUI does not release the GPU memory, restarts it once when its queue is empty (only if ImageHearth started that ComfyUI; a ComfyUI started by someone else is never restarted). If that fails, the language models stay unloaded and the status becomes `recovery_required`.

Agents MUST NOT:
- Stop or restart ComfyUI during an ImageHearth operation.
- Unload language models manually.
- Modify GPU memory management.
- Launch separate ComfyUI instances.
- Submit workflows directly to ComfyUI.
- Bypass the MCP interface.

## Output handling

Generated images are stored in:

    ~/Pictures/ImageHearth/ (or the `output_dir` configured by the user)

The first line of the tool result is the generated image path. Any following line starting with `WARNING:` is a warning: the image exists, but something needs attention. Do not retry the generation because of a warning.

Always communicate the resulting path when relevant, and relay any warnings.

Never claim that an image was generated unless the tool returned successfully.

## Error handling

If an operation fails because its models are not installed, the error names the `imagehearth-mcp setup --profile` command to run. Tell the user: the download needs their consent. Do not retry with another model unless they ask.

If it fails because too little GPU memory is free in `manual` mode, tell the user to free it.

If an operation fails for any other reason:

1. Call `get_engine_status`.
2. Check ComfyUI and the model servers.
3. If the status is `recovery_required`, use `recover_engine`.
4. If the status is `busy`, wait instead of retrying immediately.
5. If ComfyUI is stopped, use `ensure_comfyui`.
6. Retry only when the failure appears recoverable.
7. Report the actual error if the operation still fails.

Never silently switch to another image generation backend.

## General rules

- Use ImageHearth as the default image generation and editing backend.
- `create_image` is the only image tool: one call, with a list of prompts for several images.
- Do not invent workflow names or tool parameters.
- Do not modify original images unless explicitly requested.
- Ask for clarification when an essential visual requirement is ambiguous.
- Follow the user's requested style, dimensions and constraints.
- Keep the integration independent of the AI agent using it.
