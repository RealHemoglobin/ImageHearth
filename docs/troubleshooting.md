# Troubleshooting

Start with this, which checks each layer and says how to fix what fails:

```bash
imagehearth-mcp doctor
```

If the command isn't found, it may not be in your `PATH` yet: run `uv tool update-shell` and open a new terminal, or use the full path, in the folder that `uv tool dir --bin` prints.

## Installer

| Message | What to do |
|---|---|
| `No terminal available` | The script can't ask you to accept the licenses, for example in CI or over a pipe with no terminal. Run the commands it prints. `imagehearth-mcp setup --non-interactive` then says which options it needs |
| `Can't install uv` | Check your network and proxy. Or [install uv by hand](https://docs.astral.sh/uv/getting-started/installation/) and run the script again |
| `Can't install imagehearth-mcp==...` | Read uv's error above it. It's usually the network. If an older executable is in the way, run `uv tool install --force imagehearth-mcp` |
| `macOS is prepared but has never been run` | macOS isn't supported. To try it anyway, see the [README](../README.md#macos-untested) |
| `imagehearth-mcp: command not found` in a new terminal | The installer runs `uv tool update-shell`; open a new terminal after it. `imagehearth-mcp doctor` (the `path` check) prints the exact command for your shell. Agents are not affected: `connect` writes the absolute path |
| `Setup did not finish` | Read the error above it, fix it and run the command it prints. It continues where it stopped |

## Setup

Nothing is downloaded until these checks pass. If setup is interrupted, run it again: it continues where it stopped, and doesn't download what's already complete.

| Message | What to do |
|---|---|
| `Not enough disk space` | Free some space, choose a smaller profile with `--profile`, or keep the models on another disk with `--models-dir` |
| `An NVIDIA GPU is present but nvidia-smi does not work` | Install the [current driver](https://www.nvidia.com/drivers), reboot and run setup again |
| `NVIDIA driver ... may be too old` | A warning. Update the driver if ComfyUI can't use the GPU |
| `has ... MiB of memory and the ... profile ... needs` | A warning: the quality model doesn't fit this GPU, and generation may be slow or fail. It's installed anyway; switch to a lighter one with `setup --quality-model flux-schnell` or `sdxl` if it does |
| `Nothing was changed. Non-interactive mode needs --yes to switch the quality model` | Switching replaces the current model. Add `--yes` after reading the plan it printed |
| `An image is being generated, or a session needs recover_engine` | A model switch is refused meanwhile. Wait for the image, or call `recover_engine`, and run the command again |
| `Port ... is already in use` | Close whatever uses it or choose another with `--port`. If it's a ComfyUI you want to use, run setup with `--attach PATH` |
| `Port ... is in use, but it does not respond like ComfyUI` | Close it, or give your ComfyUI's port with `--port` |
| `uv was not found in PATH` | [Install uv](https://docs.astral.sh/uv/getting-started/installation/) and open a new terminal |
| `The ... profile needs a GPU` | Without a GPU, only `--profile fast` works |
| `Non-interactive mode needs ...` | Add the option named in the message. Read the licenses before adding `--accept-licenses` |
| `Nothing was downloaded: the licenses were not accepted` | You answered no. Nothing changed |
| `Another setup, update or uninstall is running` | Wait for it to finish |

**A model switch was interrupted.** The previous model is deleted only after the new one is downloaded and verified, so you keep generating with the previous one (`imagehearth-mcp doctor` shows which is active). Run the same command again: the download resumes and the switch finishes. **Disk space during a switch:** both models are on disk at the same time, so setup needs room for the new one before it frees the old one; if it says `Not enough disk space`, free some or keep the models on another disk with `--models-dir`.

If Hugging Face restricts access to a model, set `HF_TOKEN` and run setup again.

## `doctor` results

| Layer | If it fails | What to do |
|---|---|---|
| `package` | The installation is damaged | `uv tool install --force imagehearth-mcp` |
| `config` | A value in `config.toml` is invalid | Fix the value named in the message |
| `comfyui`, `environment` | ComfyUI or PyTorch is missing or broken | `imagehearth-mcp setup` |
| `node` | The status node is missing or outdated | `imagehearth-mcp setup --install-node`, then restart ComfyUI |
| `custom_nodes` | A node the profile needs is missing or outdated | The command in the message |
| `models` | Files are missing or damaged | `imagehearth-mcp setup --profile <profile>`. Use `doctor --verify-hashes` to compare SHA-256 |
| `gpu` | The driver is missing, or the GPU is experimental | Install the driver. A warning about an experimental GPU only means it hasn't been tested |
| `port` | Something else uses ComfyUI's port | Close it, or set another `comfy_port` in `config.toml` |

## Engine status

Ask your agent to *"check the ImageHearth status"*:

| Status | Meaning | What to do |
|---|---|---|
| `ready` | Everything works | Nothing |
| `not_installed` | ComfyUI or the models are missing | Run the command in `issues`, or ask your agent to install it |
| `busy` | Another image is being generated | Wait |
| `degraded` | Something is missing | Read `issues`. Usually the status node is missing or outdated. Generation still works, but GPU memory is checked less reliably |
| `recovery_required` | A previous session was interrupted | Ask your agent to *"recover the engine"* |

## Common problems

| Problem | What to do |
|---|---|
| The agent doesn't see the tools | Restart it. Then run `imagehearth-mcp connect --print <client>` and compare it with its configuration. See [agents](agents.md) |
| Tool calls stop after a few minutes | Raise the client's tool timeout. See [long generations](agents.md#long-generations) |
| Images with FLUX Schnell or SDXL 1.0 look like paintings or cartoons | Short prompts come out painterly with these models. `style="auto"` (default) adds photographic cues unless the prompt names another medium; use `style="photo"` to force it, and describe the scene like a photograph (subject, light, lens). FLUX Dev needs no help |
| Error about a model that isn't installed | Run the `imagehearth-mcp setup --profile ...` command in the error |
| ComfyUI doesn't start | Read `comfyui.log` in the logs folder below |
| The generation is slow on a card with little memory | ComfyUI moves what doesn't fit into system RAM. `doctor` shows the memory arguments it starts with; add your own with `comfy_args` in `config.toml` (they win over the automatic ones) |
| `llama-server` stopped and came back | With a one-model `llama-server` and `memory_mode = "auto"`, ImageHearth stops it to free the GPU and starts it again with the same command line, directory and environment. Its output goes to `llama-server.log` in the logs folder. A server run by another user, a system service or a container is never touched: use `memory_mode = "manual"` or `off` to stop it from being considered |
| `create_image` with a list of prompts is rejected: `Item N: ...` | Nothing was generated. Each line names an item (counting from 1) and what is wrong with it; fix them and send the batch again |
| `A batch must be all generations or all edits` | Send the new images and the edits (items with `image_paths`) as two batches |
| `A batch can have at most N items` | Split the batch, or raise the limit with `imagehearth-mcp setup --batch-limit N` (or `batch_limit` in `config.toml`). `imagehearth-mcp doctor` shows the limit in use |
| Some lines of a batch say `ERROR: ...` | Those images failed and the rest were made. `not attempted` means ComfyUI stopped before reaching them; ask for those again |
| Out of GPU memory with a language model loaded | Use `memory_mode = "auto"`, or free the memory yourself. See the [README](../README.md#settings-optional) |

## Logs

| System | Folder |
|---|---|
| Linux | `~/.local/state/imagehearth/log/` |
| Windows | `%LOCALAPPDATA%\imagehearth\Logs\` |

## Reporting a problem

[Open an issue](https://github.com/RealHemoglobin/ImageHearth/issues/new/choose) and paste the output of this command:

```bash
imagehearth-mcp doctor --json
```

It includes local paths, which may show your user name: replace it if you prefer. For a security problem, see [`SECURITY.md`](../SECURITY.md) instead.
