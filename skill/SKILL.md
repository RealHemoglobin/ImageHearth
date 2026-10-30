---
name: imageengine
description: Generate, edit and compose images using the centralized ImageEngine MCP service. Use for all image creation and editing tasks.
---

# ImageEngine

## Purpose

ImageEngine is the centralized image generation and editing engine shared by all AI agents.

It uses:
- ComfyUI as the image generation backend.
- SDXL Turbo for fast generation.
- FLUX Dev for high-quality generation.
- FLUX Kontext for image editing and multi-reference composition.
- Ollama for local LLM inference.
- A centralized orchestration layer for GPU memory management.
- MCP as the agent-independent interface.

All agents MUST use ImageEngine MCP tools for image operations.

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
- `negative_prompt` (string, optional): Elements to avoid during generation.

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

For editing:
- Default: preserve the dimensions of the first reference image.
- Explicit width and height override the output dimensions.

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

## Specialized tools

### generate_image

Generate a new image using an explicitly selected workflow.

Parameters:
- `prompt` (string, required)
- `workflow` (string, optional): Default `sdxl_turbo`.
- `width` (integer, optional): Default 1024.
- `height` (integer, optional): Default 1024.
- `negative_prompt` (string, optional).

Available generation workflows:
- `sdxl_turbo`
- `flux_dev`

Prefer `create_image` unless explicit workflow selection is necessary.

### edit_image

Edit one or more reference images using FLUX Kontext.

Parameters:
- `image_path` (string, required): Primary reference.
- `prompt` (string, required): Requested modifications.
- `additional_images` (array of strings, optional): Up to five additional references.
- `width` (integer, optional): Default 0, preserves primary reference dimensions.
- `height` (integer, optional): Default 0, preserves primary reference dimensions.

Preserve all elements not explicitly requested to change.

### list_workflows

List workflow JSON files available in ImageEngine.

Use this tool to inspect the available workflow catalog.

Important:
- `flux_kontext_dev_basic` is an internal Kontext workflow template.
- Do not use it as a conventional generation workflow.
- Use `create_image` or `edit_image` for Kontext operations.

### get_engine_status

Check the current state of:
- ComfyUI.
- Ollama.
- Loaded Ollama models.
- GPU devices and VRAM information exposed by ComfyUI.

Use this tool when:
- A generation fails.
- A service appears unavailable.
- The current engine state needs verification.

### ensure_comfyui

Start ComfyUI if it is not already running.

Use when ComfyUI is stopped or unavailable.

## Image creation guidelines

1. Understand the user's intended subject and purpose.
2. Select the appropriate aspect ratio and dimensions.
3. Use `create_image` by default.
4. Choose `fast` for drafts and quick iterations.
5. Choose `high` for detailed final images.
6. Write precise prompts describing composition, lighting, style, environment and constraints.
7. Avoid adding unrequested text, logos or unrelated elements.

## Image editing guidelines

1. Use `create_image` with reference images, or `edit_image` for direct editing.
2. Supply the exact source image paths.
3. Describe the requested modifications precisely.
4. Explicitly identify elements that must remain unchanged.
5. For multiple references, explain how their visual elements should be combined.
6. Request a coherent composition rather than a collage when appropriate.
7. Maintain visual consistency across iterative design tasks.

## GPU memory management

ImageEngine manages GPU memory centrally.

The orchestration layer:
- Serializes generation sessions.
- Detects loaded Ollama models.
- Unloads Ollama models before image generation.
- Executes ComfyUI workflows.
- Releases ComfyUI models after generation.
- Restores previously loaded Ollama models.

Agents MUST NOT:
- Stop or restart ComfyUI during an ImageEngine operation.
- Unload Ollama models manually.
- Modify GPU memory management.
- Launch separate ComfyUI instances.
- Submit workflows directly to ComfyUI.
- Bypass the MCP interface.

## Output handling

Generated images are stored in:

    ~/AI/ImageEngine/output/

The tools return the generated image path.

Always communicate the resulting path when relevant.

Never claim that an image was generated unless the tool returned successfully.

## Error handling

If an operation fails:

1. Call `get_engine_status`.
2. Check ComfyUI and Ollama status.
3. If ComfyUI is stopped, use `ensure_comfyui`.
4. Retry only when the failure appears recoverable.
5. Report the actual error if the operation still fails.

Never silently switch to another image generation backend.

## General rules

- Use ImageEngine as the default image generation and editing backend.
- Prefer `create_image` for normal operations.
- Do not invent workflow names or tool parameters.
- Do not modify original images unless explicitly requested.
- Ask for clarification when an essential visual requirement is ambiguous.
- Follow the user's requested style, dimensions and constraints.
- Keep the integration independent of the AI agent using it.
