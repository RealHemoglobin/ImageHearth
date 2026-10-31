# Security policy

ImageHearth is in public beta, and only the latest published version receives fixes.

## Reporting a vulnerability

**Please don't open a public issue.** Report it privately through [GitHub's private vulnerability reporting](https://github.com/RealHemoglobin/ImageHearth/security/advisories/new).

Include what's affected, how to reproduce it and the version (`imagehearth-mcp --version`). This is a project maintained in spare time: expect a first answer within a week, on a best-effort basis. Fixes are credited in the changelog unless you prefer otherwise.

## What's most relevant

- The install scripts and what they download.
- Model and ComfyUI downloads, and their SHA-256 verification.
- Edits to agents' configuration files made by `connect`.
- Local paths read by `create_image`, and anything that lets a prompt or a tool call reach files or processes it shouldn't.
- The handling of processes: stopping or restarting something ImageHearth didn't start.

Bugs in ComfyUI, in the models or in an agent belong in their own projects.
