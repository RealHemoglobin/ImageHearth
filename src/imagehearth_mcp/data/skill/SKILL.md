---
name: imagehearth
description: Generate, edit and compose images using the centralized ImageHearth MCP service. Use for all image creation and editing tasks.
---

# ImageHearth

## Purpose

ImageHearth is the centralized image generation and editing engine shared by all AI agents.

It uses:
- ComfyUI as the image generation backend.
- SDXL Turbo for fast generation.
- FLUX Dev for high-quality generation.
- FLUX Kontext for image editing and multi-reference composition.

What is available depends on the profile the user installed. Only SDXL Turbo is present with `fast`; `quality` adds FLUX Dev and `full` adds FLUX Kontext.

- A centralized orchestration layer for GPU memory management.
- MCP as the agent-independent interface.

The server's own instructions and tool descriptions are enough to use it. This skill only adds detail.

All agents MUST use ImageHearth MCP tools for image operations.

Never implement a separate ComfyUI integration.

## Main tool: create_image

Prefer `create_image` for normal image generation and editing tasks.

Parameters:

- `prompt` (string, required): Description of the desired image or edit.
- `mode` (string, optional): `auto`, `generate` or `edit`. Default: `auto`.
- `quality` (string, optional): `fast` or `high`. Default: `fast`.
- `image_paths` (array of strings, optional): Up to six reference image paths.
- `workflow` (string, optional): Explicit generation workflow override.
- `width` (integer, optional): Output width. Default: automatic.
- `height` (integer, optional): Output height. Default: automatic.
- `negative_prompt` (string, optional): Elements to avoid during generation. Only SDXL Turbo applies it; other backends return a warning.
- `include_image` (boolean, optional): Also return the picture, for models with vision. Default: false, because it uses context. The path stays on the first line.

### Automatic routing

When `mode="auto"`:

- No reference images: generate a new image.
- One or more reference images: edit or compose using FLUX Kontext.

When `mode="generate"`:

- Generate a new image.
- Reference images are not accepted.

When `mode="edit"`:

- At least one reference image is required.
- Uses FLUX Kontext.
- Supports up to six reference images.

### Quality selection

For generation without references:

- `fast`: SDXL Turbo.
- `high`: FLUX Dev.

Quality does not change the editing backend. Image editing always uses FLUX Kontext.

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

## Other tools

### list_workflows

List the generation workflows whose models are installed.

Use this tool to inspect the available workflow catalog. It is checked on every call, so a later `setup` shows up without a restart.

The internal Kontext template is not listed and cannot be selected. Use `create_image` with `image_paths` for Kontext operations.

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

Before calling `setup_start`, tell the user the profile, download size and licenses, and wait for their clear yes. Never accept licenses on their behalf.

## Image creation guidelines

1. Understand the user's intended subject and purpose.
2. Select the appropriate aspect ratio and dimensions.
3. Use `create_image` by default.
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
- Prefer `create_image` for normal operations.
- Do not invent workflow names or tool parameters.
- Do not modify original images unless explicitly requested.
- Ask for clarification when an essential visual requirement is ambiguous.
- Follow the user's requested style, dimensions and constraints.
- Keep the integration independent of the AI agent using it.
