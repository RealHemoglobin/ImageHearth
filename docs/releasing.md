# Releasing

Run by the maintainer, by hand, from their own machine: there's no CI and nothing here is automated. Every step that publishes is hard or impossible to undo. Examples use `0.1.0b1`.

## Order matters

1. **Merge to `main` first.** The install scripts are served from `main`.
2. **Make the repository public before announcing the scripts.** Their URLs don't work while it's private.
3. **Publish to PyPI before the MCP Registry.** The registry reads the `mcp-name` marker from the README on PyPI.

## 1. Before you start

All of this must be true. Otherwise, stop.

- [ ] Every item under "Antes de publicar" in the phase's `validation.md` is checked: Windows checks and generation, clean Ubuntu and Windows 11 machines, and a real agent following `llms-install.md`.
- [ ] The support table in both READMEs says only what was tested. Once Windows 11 has passed, change its row to "Supported"; if it hasn't, don't publish. The Windows measurements are in the READMEs and `specs/tech-stack.md`, and the "still pending" note is gone.
- [ ] The same version in `pyproject.toml`, `install.sh`, `install.ps1`, `server.json`, `llms-install.md`, `docs/agents.md` and both READMEs. A test checks it.
- [ ] `CHANGELOG.md` is up to date.
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

Install it on Linux and Windows. Dependencies must keep coming from PyPI, and this also checks that a pinned beta installs without `--prerelease`:

```bash
uv tool install imagehearth-mcp==0.1.0b1 --index https://test.pypi.org/simple/ --index-strategy unsafe-best-match
```

```bash
imagehearth-mcp --version
```

```bash
imagehearth-mcp doctor
```

Check how the page looks on TestPyPI: README links, images and tables. Then remove the rehearsal with `uv tool uninstall imagehearth-mcp`. A version on TestPyPI can't be reused either: if you need another rehearsal with changes, use a temporary version such as `0.1.0b1.dev1`, and don't commit it.

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
git tag v0.1.0b1
git push origin v0.1.0b1
gh release create v0.1.0b1 dist/* --prerelease --title "ImageHearth 0.1.0b1" --notes-file <file with the changelog entry>
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

Also check `uv tool install imagehearth-mcp==0.1.0b1`, and record the results in the phase's `validation.md`. Then invite the testers with [`beta-testing.md`](beta-testing.md).

## If it fails halfway

- **A version uploaded to PyPI can't be reused,** even after deleting it. Yank the bad one on PyPI, so it isn't installed by accident, and publish the next one (`0.1.0b2`), bumping the version everywhere.
- **The installer is broken but the package is fine:** fix `main`. Users get the script from there.
- **The upload failed partway:** run `uv publish --check-url https://pypi.org/simple/` to skip the files already there.
- **PyPI is fine but the registry fails:** nothing is lost. Fix the problem and run `mcp-publisher publish` again. If it needs a change in the README, that means a new PyPI version.
- **The repository was made public and something private appears:** make it private again, and treat anything exposed as compromised: revoke it. Rewriting history doesn't remove what's already been copied.
- **A token leaks:** revoke it at once on PyPI.
