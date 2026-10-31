# Contributing

Thanks for helping. Bug reports with the output of `imagehearth-mcp doctor --json` are as useful as code, especially from hardware we don't have.

## Set up

You only need [uv](https://docs.astral.sh/uv/getting-started/installation/). It creates its own environment in `.venv`, separate from ComfyUI's.

```bash
uv sync
uv run pytest
```

The tests use simulated servers and don't need a GPU.

## Quality gate

There's no CI: these local scripts are the gate. Before proposing a change, run on Linux:

```bash
scripts/check.sh
```

Or on Windows:

```powershell
scripts\check.ps1
```

They run the linter and the tests, then repeat the tests against the built wheel. If you change a workflow or the pinned ComfyUI, also run `scripts/contract.sh` or `scripts\contract.ps1`, which start ComfyUI on the CPU and check that every node the workflows use exists. That needs no models.

## Rules for changes

- **The MCP server must start without PyTorch or ComfyUI.** Each tool explains what's missing instead of failing.
- **Keep it portable.** Use `encoding="utf-8"` for text and the helpers in `platform/`, not commands specific to one system.
- **Never redistribute model weights**, and never accept a license on the user's behalf.
- **Only announce what's been tested on real hardware.** A system, GPU or client checked only against its documentation is documented as untested.
- User-facing text is in English. When you change `README.md`, change `README.es.md` too.
- The version lives in `pyproject.toml`, `install.sh`, `install.ps1`, `server.json`, `llms-install.md`, `docs/agents.md` and both READMEs, and a test checks they match.

The project's direction is in [`specs/`](specs/roadmap.md), written in Spanish. For a large change, open an issue first.

## Licenses

By contributing you agree that your work is licensed like the code it touches: MIT for the project, and GPL-3.0 for `src/imagehearth_mcp/data/imagehearth_status/`.
