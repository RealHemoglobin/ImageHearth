# Changelog

## 2026-11-06

- Bumped the version to `0.1.0b3` (package, installers, `server.json` and docs).
- Choice of the quality model: `quality` and `full` now install FLUX.1 Dev, FLUX.1 Schnell (Apache-2.0) or SDXL 1.0 (OpenRAIL++), chosen in `setup` (`--quality-model`) or by an agent (`setup_start(quality_model)`), recommended by GPU memory. Changing it downloads the new model first and then deletes the old one. RealVisXL is no longer offered; older installations keep generating and `doctor` says how to move to SDXL 1.0.
- The active quality model and its license show in `list_workflows`, `get_engine_status` and `doctor`, and each PNG records the model and workflow.
- Added the `style` option of `create_image`: with FLUX Schnell and SDXL 1.0, `auto` adds photographic cues (and, for SDXL, a negative prompt against illustration) unless the prompt asks for another medium, because short prompts came out painterly.

## 2026-11-04

- Bumped the version to `0.1.0b2` (package, installers, `server.json` and docs).
- Hardware adaptation: `doctor` checks the PATH, and llama.cpp runs a single model that is stopped and restored around image generation. The installer test no longer needs `sh` on Windows.

## 2026-10-31

- Prepared the public beta `0.1.0b1`: `install.sh` and `install.ps1`, package metadata, `server.json` for the MCP Registry, rewritten READMEs, troubleshooting, release and beta testing guides, contribution and security policies, and issue templates.
- Connected agents with `connect`, with `connect --print` for any other client and `docs/agents.md`, and reported progress so long generations aren't cut off.
- Replaced `generate_image` and `edit_image` with a single `create_image`, and made the essential instructions part of the server, for agents without skills.
- Added `setup_status` and `setup_start`, so an agent can run the installation after asking the user.
- Added `memory_mode` and memory providers for LM Studio, llama.cpp and vLLM, alongside Ollama.
- Made the catalog depend on what's installed: errors name the exact `setup` command, never another model. Added measured profiles, and macOS prepared without testing behind `--experimental`.
- Added `setup`, `doctor`, `update` and `uninstall`: pinned ComfyUI, resumable and verified model downloads, consent before downloading, and checks before starting.
- Made the core portable to Windows and macOS, and made Ollama optional. Fixed the status node, and never restarts a ComfyUI it didn't start.
- Packaged the project as `imagehearth-mcp`, with its configuration in `config.toml`. Added the licenses and third-party notices, and local checks with `scripts/check.sh`.

## 2026-10-30

- First state of the project as ImageEngine: session recovery, deadlines and validation, configuration, rotating logs, persistent state and the status node.
