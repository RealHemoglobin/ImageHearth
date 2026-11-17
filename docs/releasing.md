# Releasing

Run by the maintainer, by hand, from their own machine: there's no CI and nothing here is automated. Every step that publishes is hard or impossible to undo. Examples use `1.0.0`. The version policy is in [versioning.md](versioning.md).

## Order matters

1. **Merge to `main` first.** The install scripts are served from `main`.
2. **Make the repository public before announcing the scripts.** Their URLs don't work while it's private.
3. **Publish to PyPI before the MCP Registry.** The registry reads the `mcp-name` marker from the README on PyPI.

## 1. Before you start

All of this must be true. Otherwise, stop.

- [ ] Every item of the "Lista para fusionar" in the phase's `validation.md` is checked: `check` and `contract` on Linux and Windows, and a clean Windows 11 machine with NVIDIA.
- [ ] The support table in both READMEs says only what was tested on real hardware. A row is level 1 (supported) only after a real run of this version; otherwise, change it before publishing.
- [ ] The same version in `pyproject.toml`, `install.sh`, `install.ps1`, `server.json`, `llms-install.md`, `docs/agents.md` and both READMEs. A test checks it.
- [ ] `CHANGELOG.md` is up to date.
- [ ] `docs/security-review.md` has no open high or medium finding.
- [ ] `scripts/contract_latest` has been run recently. If it fails because a new ComfyUI release changed something, that doesn't block the release (the version is pinned), but note it.
- [ ] `main` is clean and has what you're about to publish.

```bash
scripts/check.sh
```

```bash
scripts/contract.sh
```

## 2. Build

```bash
rm -rf dist
uv build
```

Look at what went in: there should be no `specs/`, models or local files. The tests check this, but it costs a few seconds.

```bash
tar tzf dist/*.tar.gz
```

```bash
unzip -l dist/*.whl
```

## 3. Rehearse on TestPyPI

Create a token at <https://test.pypi.org/manage/account/token/>. Keep it in the environment only, never in a file in this repository.

```bash
UV_PUBLISH_TOKEN=<test token> uv publish --publish-url https://test.pypi.org/legacy/
```

Install it on Linux and Windows. Dependencies must keep coming from PyPI, and this also checks that the pinned version installs:

```bash
uv tool install imagehearth-mcp==1.0.0 --index https://test.pypi.org/simple/ --index-strategy unsafe-best-match
```

```bash
imagehearth-mcp --version
```

```bash
imagehearth-mcp doctor
```

Check how the page looks on TestPyPI: README links, images and tables. Then remove the rehearsal with `uv tool uninstall imagehearth-mcp`. A version on TestPyPI can't be reused either: if you need another rehearsal with changes, use a temporary version such as `1.0.0.dev1`, and don't commit it.

## 4. Make the repository public

```bash
gh repo edit RealHemoglobin/ImageHearth --visibility public --accept-visibility-change-consequences
```

Then turn on private vulnerability reporting, which `SECURITY.md` relies on, and check that the issue templates appear:

```bash
gh api -X PUT repos/RealHemoglobin/ImageHearth/private-vulnerability-reporting
```

## 5. Publish to PyPI

Use a token from <https://pypi.org/manage/account/token/>, in the environment only.

```bash
UV_PUBLISH_TOKEN=<token> uv publish
```

## 6. Create the GitHub Release

```bash
git tag v1.0.0
git push origin v1.0.0
gh release create v1.0.0 dist/* --title "ImageHearth 1.0.0" --notes-file <file with the changelog entry>
```

## 7. Publish to the MCP Registry

Install `mcp-publisher` following the [registry's quickstart](https://modelcontextprotocol.io/registry/quickstart). Log in as `RealHemoglobin`, since the `io.github.RealHemoglobin/` namespace must match that account:

```bash
mcp-publisher login github
mcp-publisher validate
mcp-publisher publish
```

If the name is refused because of its case, the marker in the README is already on PyPI, so correcting it needs a new version on PyPI first.

```bash
curl "https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.RealHemoglobin/imagehearth"
```

## 8. Final check

From the public URLs, on clean machines:

```bash
curl -LsSf https://raw.githubusercontent.com/RealHemoglobin/ImageHearth/main/install.sh | sh
```

```powershell
irm https://raw.githubusercontent.com/RealHemoglobin/ImageHearth/main/install.ps1 | iex
```

Also check `uv tool install imagehearth-mcp==1.0.0`, and record the results in the phase's `validation.md`. To get reports from other hardware, point people to [`beta-testing.md`](beta-testing.md).

## Scheduled contract test

ComfyUI is pinned, so a new ComfyUI release can't break an installation. The risk is the day you raise the pin. `scripts/contract_latest` tells you earlier: it asks GitHub for the latest ComfyUI release, downloads it to a temporary folder, starts it on the CPU, and checks that every node and input the workflows use still exists. It uses the Python environment of your local ComfyUI, doesn't download models and doesn't change your installation.

```bash
scripts/contract_latest.sh
```

```powershell
scripts\contract_latest.ps1
```

It exits with 0 if it passes and 1 if it fails (also when GitHub or the download fails). Each run writes `contract-latest-<date>-<version>.log` in ImageHearth's log folder (`~/.local/state/imagehearth/log` on Linux and `%LOCALAPPDATA%\imagehearth\Logs` on Windows), plus a `-comfyui.log` with ComfyUI's own output. The first lines say which version was tested.

It needs the checkout of the repository, uv and a local ComfyUI installed by `setup` (set `IMAGEHEARTH_COMFY_DIR` for another one). The first run installs the project's dependencies with `uv run`.

### Schedule it on Windows

Weekly, Mondays at 09:00, with the Task Scheduler (change the path of the checkout):

```powershell
schtasks /Create /TN "ImageHearth contract test" /SC WEEKLY /D MON /ST 09:00 /TR "powershell -NoProfile -ExecutionPolicy Bypass -File K:\path\to\ImageHearth\scripts\contract_latest.ps1"
```

Run it now to see it work, and look at the result:

```powershell
schtasks /Run /TN "ImageHearth contract test"
```

```powershell
schtasks /Query /TN "ImageHearth contract test" /V /FO LIST
```

"Last Result: 0" means it passed. Remove it with `schtasks /Delete /TN "ImageHearth contract test" /F`.

### Schedule it on Linux

With cron (`crontab -e`), weekly on Mondays at 09:00:

```
0 9 * * 1 /path/to/ImageHearth/scripts/contract_latest.sh
```

Or with a systemd user timer. `~/.config/systemd/user/imagehearth-contract.service`:

```ini
[Service]
Type=oneshot
ExecStart=/path/to/ImageHearth/scripts/contract_latest.sh
```

and `~/.config/systemd/user/imagehearth-contract.timer`:

```ini
[Timer]
OnCalendar=Mon 09:00
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
systemctl --user enable --now imagehearth-contract.timer
```

`journalctl --user -u imagehearth-contract.service` shows the last result.

### If it fails

1. Read the log. A line `MISSING <node>` or `UNKNOWN INPUT <node> <input>` names the workflow that would break. `FAIL: Can't read the latest ComfyUI release` or `Can't download` is the network; run it again later.
2. `ComfyUI exited at startup` usually means the new release needs Python packages your local environment doesn't have. See the `-comfyui.log`. It doesn't say the workflows are wrong.
3. Nothing breaks for users: they have the pinned version. Decide when to raise it. Fix the templates in `data/workflows/`, raise `[comfyui]` in `data/models.toml` (version, URL and SHA-256), run `scripts/contract.sh` and release it as a minor version ([versioning.md](versioning.md)).

## If it fails halfway

- **A version uploaded to PyPI can't be reused,** even after deleting it. Yank the bad one on PyPI, so it isn't installed by accident, and publish the next one (`1.0.1`), bumping the version everywhere.
- **The installer is broken but the package is fine:** fix `main`. Users get the script from there.
- **The upload failed partway:** run `uv publish --check-url https://pypi.org/simple/` to skip the files already there.
- **PyPI is fine but the registry fails:** nothing is lost. Fix the problem and run `mcp-publisher publish` again. If it needs a change in the README, that means a new PyPI version.
- **The repository was made public and something private appears:** make it private again, and treat anything exposed as compromised: revoke it. Rewriting history doesn't remove what's already been copied.
- **A token leaks:** revoke it at once on PyPI.
