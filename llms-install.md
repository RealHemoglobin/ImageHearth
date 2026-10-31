# Installing ImageHearth (instructions for AI agents)

You are helping a user install ImageHearth, an MCP server that generates and edits images locally through ComfyUI. Installing downloads between 14 and 44 GB. **Ask the user before anything that downloads, and never accept a license on their behalf.**

## 1. Check the requirements

- Linux or Windows 11 with an NVIDIA GPU. macOS is untested: don't install there unless the user runs setup themselves with `--experimental`.
- [uv](https://docs.astral.sh/uv/getting-started/installation/). If `uv --version` fails, ask before installing it.

## 2. Install the command

```bash
uv tool install imagehearth-mcp==0.1.0b1
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
- The licenses of the profile, with their links. FLUX models are non-commercial.
- Any existing ComfyUI found, which avoids downloading it again.

Wait for a clear answer naming the profile and accepting the licenses.

## 5. Install

Call `setup_start` with that `profile` and `accept_licenses: true`. Pass `existing_comfyui` only if the user chose to reuse one. It returns at once and continues if you disconnect. Check `setup_status` from time to time: `installation.state` becomes `finished` or `failed`, and `installation.log_tail` shows the latest output. If it is `interrupted`, call `setup_start` again and it continues where it stopped.

Without the tools, run this instead, after the user's answer:

```bash
imagehearth-mcp setup --profile <profile> --accept-licenses --non-interactive --managed
```

## 6. Verify

Call `create_image` with a short prompt and tell the user the path on the first line of the result. If something fails, run `imagehearth-mcp doctor` and report what it says. Common problems are in [docs/troubleshooting.md](https://github.com/RealHemoglobin/ImageHearth/blob/main/docs/troubleshooting.md).
