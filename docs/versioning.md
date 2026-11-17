# Versioning and migrations

ImageHearth follows [semantic versioning](https://semver.org): `MAJOR.MINOR.PATCH`. The version you install is the one in `imagehearth-mcp --version`, and the installers pin it, so an install never changes by itself.

## What a version pins

Each release fixes, in `data/models.toml`:

- the ComfyUI version, with the SHA-256 of its archive;
- the revision and SHA-256 of every model and LoRA;
- the commit and SHA-256 of each custom node (ComfyUI-GGUF), with its Python packages;
- the PyTorch packages for each GPU platform.

Nothing is fetched "latest". `update` applies exactly what the installed version pins.

## What each kind of release may change

| Release | May change | Never changes |
|---|---|---|
| **Patch** (1.0.1) | Bug fixes, documentation, messages, tests, a model or node revision when the old one disappears or is broken | The pinned ComfyUI version, the format of `install.json`, the tools an agent sees, the commands |
| **Minor** (1.1.0) | New tools, options, models, LoRAs, profiles and clients. A new pinned ComfyUI version. A new `install.json` format, with its migration | A tool or option that exists keeps working with the same meaning |
| **Major** (2.0.0) | Removing or renaming tools, options or commands. Changes that need the user to act | — |

So a patch can always be applied with `uv tool upgrade imagehearth-mcp` and `imagehearth-mcp update`, with nothing to read first. A change of ComfyUI version or of the install record format only arrives in a minor or major release.

Models are never deleted by the version change itself. When a release changes which file a model uses, `update` downloads and verifies the new one first and only then removes the old one.

## The install record and its migrations

`install.json` (in the data folder) is what `uninstall` trusts. It carries:

- `schema`: the format, currently `1`;
- `imagehearth_version`: the version of ImageHearth that last wrote it (absent in records from before 1.0).

A migration is a function that takes the record of format N and returns the one of format N+1. They live in `provisioner/migrations.py` and are applied in order, so a record several formats behind goes through each step.

- **Loading migrates in memory only.** `doctor` loads the record and reports when it needs migrating; it never writes.
- **`update` saves the result,** and before the first write it keeps the previous record as `install.json.bak-<format>` next to it. Restore it by copying it back over `install.json`.
- **A migration never downloads or deletes models.** It only rewrites the record. Anything that has to change in the models goes through the usual mechanism: download, verify, then remove.
- **A record from a newer ImageHearth is refused** without changing anything, with a message asking you to update ImageHearth (`uv tool upgrade imagehearth-mcp`). An older ImageHearth never guesses at a format it doesn't know.

Format `1` is the only one so far, and every record written since 0.1.0 is format `1`: it loads without changes.

## What `update` tells you first

Before acting, `update` prints:

- the ImageHearth version that wrote the record and the one installed;
- the install record format, when it will be migrated, and where the old copy is kept;
- the pinned ComfyUI version before and after;
- the models that change (missing, wrong size or replaced), with their size.

It asks "Apply these changes?" when there is something to change and you are at a terminal. With `--yes` it doesn't ask; downloading models still needs `--accept-licenses` when it isn't interactive. When nothing changes it says "Nothing to change." and downloads nothing.

## Checking the next ComfyUI

The pinned ComfyUI is only raised on purpose. `scripts/contract_latest.py` runs the contract test against the newest ComfyUI release without touching your installation, as an early warning that a release would break a template. See [releasing.md](releasing.md#scheduled-contract-test).
