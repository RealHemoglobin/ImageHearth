# Changelog

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
