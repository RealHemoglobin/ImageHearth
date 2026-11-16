# Installing ImageHearth (instructions for AI agents)

You are helping a user install ImageHearth, an MCP server that generates and edits images locally through ComfyUI. Installing downloads between 7 and well over 100 GB, depending on the models chosen. **Ask the user before anything that downloads, and never accept a license on their behalf.**

## 1. Check the requirements

- Linux or Windows 11 with an NVIDIA GPU. macOS is untested: don't install there unless the user runs setup themselves with `--experimental`.
- [uv](https://docs.astral.sh/uv/getting-started/installation/). If `uv --version` fails, ask before installing it.

## 2. Install the command

```bash
uv tool install --python 3.13 imagehearth-mcp==0.1.0b3
```

If `imagehearth-mcp` isn't found afterwards, use the path from `uv tool dir --bin`, or run `uv tool update-shell` and open a new terminal.

## 3. Connect this agent

```bash
imagehearth-mcp connect --list
imagehearth-mcp connect <client>
```

It makes a backup first and keeps the other entries. If your client isn't listed, run `imagehearth-mcp connect --print claude-desktop` and adapt the snippet: see [docs/agents.md](https://github.com/RealHemoglobin/ImageHearth/blob/main/docs/agents.md). Ask the user to restart the agent if the new tools don't appear.

## 4. Choose with the user

Call the `setup_status` tool, or run `imagehearth-mcp setup --non-interactive` to see the profiles. Tell the user:

- The profiles that suit their GPU, and each download size.
- The models of each capability the profile has, from `models` in `setup_status` (`fast`, `high` = quality, and `edit` for `full`): for each model its precisions with download size, seconds per image measured for this GPU's level, license, commercial use, whether it fits the GPU (`warning`) and which one is recommended. The user may pick **several** models per capability; the first they name is the default. Tell them HiDream also downloads Meta's Llama 3.1 text encoder under its own license.
- If they choose SDXL 1.0 (`sdxl`), ask whether they want style LoRAs (pixel art, watercolor, anime...) and which: `loras` in `setup_status` lists each one with category, size and license. None is installed unless they ask. They only work with SDXL 1.0.
- The licenses of what will be downloaded, with their links. FLUX Dev and FLUX Kontext are non-commercial; the other models (Z-Image-Turbo, FLUX.2 Klein 4B, Chroma1-HD, Qwen-Image, Qwen-Image-Edit, HiDream, FLUX Schnell, SDXL 1.0) allow commercial use, some with conditions.
- Any existing ComfyUI found, which avoids downloading it again.
- Where to install: ComfyUI and the models take tens of GB. `setup_status` has `install_folder` with the usual folder (`default`, and the space free there) and the other disks found with their free space. Ask whether they want another one; don't choose it for them.

Wait for a clear answer naming the profile, the models of each capability, the LoRAs if any and the folder (or "the usual one") and accepting the licenses.

## 5. Install

Call `setup_start` with that `profile`, the lists the user chose (`fast_models`, `quality_models`, `edit_models`, each a list of `name` or `name:precision`; omit one to leave that capability as it is, or to get the recommended model on a new installation), `loras` (a list of names, or `["all"]`) only if they chose some, and `accept_licenses: true`. Pass `install_dir` (an absolute path) only if the user chose another folder: it is checked first and refused with the reason if there is no space, no permission or the file system can't hold the models; tell the user and ask for another. Pass `existing_comfyui` only if the user chose to reuse one (it can't be combined with `install_dir`). On an existing installation a list fixes the set of that capability: the models not listed are deleted after the new ones are verified, so include the ones to keep. It returns at once and continues if you disconnect. Check `setup_status` from time to time: `installation.state` becomes `finished` or `failed`, and `installation.log_tail` shows the latest output. If it is `interrupted`, call `setup_start` again and it continues where it stopped.

Without the tools, run this instead, after the user's answer:

```bash
imagehearth-mcp setup --profile <profile> [--fast-models <name[:precision],...>] [--quality-models <name[:precision],...>] [--edit-models <name[:precision],...>] --accept-licenses --non-interactive --managed [--loras <names|all>] [--install-dir <folder>]
```

## 6. Verify

Call `create_image` with a short prompt and tell the user the path on the first line of the result. `list_workflows` shows the installed models; pass one by name in `create_image(model=...)`. If something fails, run `imagehearth-mcp doctor` and report what it says. Common problems are in [docs/troubleshooting.md](https://github.com/RealHemoglobin/ImageHearth/blob/main/docs/troubleshooting.md).
