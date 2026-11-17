# Security review

Review of ImageHearth 1.0.0, done on 2026-11-17 by reading the code, before publishing. It covers the install scripts, the downloads, the editing of agents' configuration, the local paths and the local ComfyUI server. It is a review, not an audit: nobody outside the project has done a penetration test.

**Severity.** *High*: a remote or unprivileged attacker gets code execution or data loss without the user doing anything unusual. *Medium*: a realistic situation leaks data, changes files the user didn't expect, or runs the wrong code. *Low*: needs a hostile local user, a hostile agent the user already trusts, or a setting the user chose; or the harm is small. High and medium findings are fixed in 1.0.0 with a test. Low findings are documented here.

## Summary

| # | Finding | Severity | Status |
|---|---|---|---|
| 1 | `install.sh` taking the current directory for the repository | Medium | Fixed |
| 2 | Agent configuration written world-readable for an instant, and symlinks replaced | Medium | Fixed |
| 3 | `HF_TOKEN` in error messages | Low | Fixed |
| 4 | uv installed with the vendor's script, not pinned | Low | Accepted |
| 5 | GitHub wheel fallback not verified by hash | Low | Accepted |
| 6 | `create_image` reads any image path the agent gives | Low | Accepted |
| 7 | `install_dir` from an agent may be any absolute path | Low | Accepted |
| 8 | `comfy_args` can make ComfyUI listen on the network | Low | Accepted |
| 9 | Backups of agent configuration pile up and keep secrets | Low | Accepted |
| 10 | Local ComfyUI server has no authentication | Low | Accepted |

No high finding was found.

## Findings

### 1. `install.sh` installing from the current directory (Medium, fixed)

**File:** `install.sh`, `main`.

**Scenario.** With `curl ... | sh`, `$0` is `sh`, so `dirname "$0"` is `.`. If the user ran the command from a folder that contains a `pyproject.toml` (any Python project), the script took that folder for a clone of ImageHearth and ran `uv tool install` on it: the code of an unrelated or untrusted project was installed and then run by `setup`.

**Fix.** The repository is used only when `$0` is a file called `install.sh` that exists. `tests/test_security.py` checks the script. `install.ps1` is not affected: `$PSScriptRoot` is empty under `irm | iex`.

### 2. Agent configuration files (Medium, fixed)

**File:** `provisioner/connect.py`, `_write`.

**Scenario.** These files can hold API keys. The temporary file was created with the default permissions and the original mode was copied only afterwards, so on a shared machine another user could read the content in between. Also, a configuration file that was a symbolic link (managed with dotfiles) was replaced by a regular file, breaking the link and leaving the real file stale.

**Fix.** The temporary file is created exclusively with mode `0600`, receives the mode of the original, and replaces the real target of a link, which stays a link. A new file is created private. Tests: `test_agent_config_is_never_written_world_readable`, `test_a_new_agent_config_is_created_private`, `test_agent_config_that_is_a_symlink_keeps_its_link` (POSIX only).

**Checked and fine.** A backup is made before every change (`.imagehearth-<date>.bak`, same mode). Files that are not valid JSON, TOML or YAML, or that have an unexpected structure, are never touched. After editing, the result is parsed again and compared: only ImageHearth's entry may differ. Only the entry named `imagehearth` (or the old `imageengine`) is added or removed, and only if its command is ImageHearth's. `.mcp.json` of a project is never edited.

### 3. `HF_TOKEN` in messages (Low, fixed)

**File:** `provisioner/models.py`.

The token is sent only in the request headers of Hugging Face downloads. It is never written to `install.json`, `config.toml` or the logs. As a precaution, the download error message now replaces the token value if a library ever included it (`models.scrub`).

### 4. uv installed with the vendor's script (Low, accepted)

**File:** `install.ps1`, `install.sh`.

If uv is missing, the installers run uv's official installer from `astral.sh`, over HTTPS. The script is downloaded to a file first on Linux, so a failed download is not run, and in its own process on Windows. The uv version is not pinned. A compromise of that site would affect the installer. The alternative, installing uv by hand first, is documented, and nothing runs with elevated rights.

### 5. GitHub wheel fallback (Low, accepted)

**File:** `install.ps1`, `install.sh`.

When PyPI doesn't have the pinned version, the installers fall back to the wheel of the same version in the GitHub release, over HTTPS, without a hash. PyPI is the normal path. The fallback exists for a failed publish, and the same maintainer publishes both.

### 6. `image_paths` (Low, accepted)

**File:** `engine/kontext.py`, `normalize_image_paths`.

An agent can pass any path. The file must exist, and Pillow must open it as an image; only then is it uploaded, to the local ComfyUI, and removed when the generation ends. Anything that isn't an image is refused, so this does not read configuration or keys. It can use any image the user can read, which an agent with file access can already do.

### 7. `install_dir` from an agent (Low, accepted)

**File:** `provisioner/agent_setup.py`.

`setup_start` needs the user's accepted licenses, requires an absolute path and checks the folder (room, writable, file system). It creates `<folder>/comfyui` and nothing executable at a path the user didn't choose. `uninstall` refuses protected folders (`_is_safe`) and deletes only what the install record marks as created by ImageHearth.

### 8. `comfy_args` (Low, accepted)

**File:** `engine/comfy_args.py`.

ImageHearth starts ComfyUI with `--listen 127.0.0.1`. `comfy_args` in `config.toml` (or `IMAGEHEARTH_COMFY_ARGS`) is added after, and wins by design, so a user can write `--listen 0.0.0.0` and expose ComfyUI, which has no authentication. It is the user's own configuration, and an agent cannot change it.

### 9. Backups of agent configuration (Low, accepted)

**File:** `provisioner/connect.py`, `_backup`.

Each change keeps a copy next to the original, with the same permissions. They are never deleted by ImageHearth, so a secret that the user later removes from the original remains in an old backup. The message says where each backup is.

### 10. Local ComfyUI server (Low, accepted)

**Files:** `engine/comfyui_client.py`, `data/imagehearth_status/__init__.py`.

ComfyUI listens only on `127.0.0.1`, on a port that is configurable (default 8188). Any program of the same user can talk to it, as with any local development server. Browser protections for local servers are ComfyUI's, not ImageHearth's. The `imagehearth_status` node adds one read-only `GET` route that returns the class names of the loaded models. `remove_output_copy` and `remove_run_inputs` build paths from a base name or a hexadecimal identifier, so a name from ComfyUI cannot point outside its folders.

## Checked, no finding

- **Downloads.** The ComfyUI archive and each custom node are verified against a SHA-256 pinned in `data/models.toml` before anything is extracted; a mismatch deletes the file. Models are verified by SHA-256 after downloading, and a corrupt file is downloaded again. Downloads go to `.part` or `.partial` files in a staging folder and are moved into place only when verified.
- **Extraction.** Archives are extracted with `tarfile`'s `data` filter, which refuses `..`, links that leave the folder and special files, and removes the root of an absolute path. `tests/test_security.py` tries each case on the ComfyUI archive and on a custom node. Nothing is written outside the staging folder, and the target is changed only after extraction succeeds.
- **Install scripts.** Both are wrapped so that a cut-off download can't run half a script, pin the version, never ask for administrator rights and never accept a license for the user. Paths with spaces are quoted. The `--experimental` flag is the only argument `install.sh` reads.
- **Agent-driven setup.** `setup_start` needs `accept_licenses`, validates profile, models and LoRAs against the catalog and the ComfyUI folder against `is_comfy_dir`. Model names reach the child process only after validation.
- **Processes.** ImageHearth stops only the ComfyUI it started, identified by PID and creation time. `uninstall` never deletes a folder that isn't in the install record.
- **YAML and TOML.** Configuration is read with `yaml.safe_load` and `tomllib`.

## What to do if you find something

Report it privately, as [SECURITY.md](../SECURITY.md) says.
