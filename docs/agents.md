# Connecting agents and editors

ImageHearth is a standard MCP server over stdio, so any client that supports MCP can use it. The [installer](../README.md#installation) offers to connect the clients it finds. To install by hand, run `uv tool install imagehearth-mcp==0.1.0b1`. After that, `connect` adds it for you:

```bash
imagehearth-mcp connect --list          # known clients and their support level
imagehearth-mcp connect --detect        # find installed clients and offer to connect them
imagehearth-mcp connect <client>        # connect one
imagehearth-mcp connect --print <client>  # print the snippet, change nothing
imagehearth-mcp connect --remove <client>
```

`connect` backs up the file first (`<file>.imagehearth-<date>.bak`), keeps your other entries, can be repeated without duplicating anything, and copies no environment variables or secrets. It uses the absolute path of the executable. It refuses to touch a file it can't parse. `imagehearth-mcp uninstall` removes what `connect` recorded, unless you changed the entry yourself. Where the client supports skills, the optional skill is installed too (`--no-skill` to skip it); the server's own instructions are enough without it.

## Support levels

- **Tested:** connected with `connect` from an empty configuration, then generated with `fast`, generated with `quality` and edited with Kontext, on Linux on 2026-10-31.
- **Untested:** checked against its documentation only. It is not announced as supported.

## Any other client

Run `imagehearth-mcp connect --print claude-desktop`, which prints the most common format, and put that entry wherever your client keeps its MCP servers. Use the absolute path of `imagehearth-mcp` (`which imagehearth-mcp`, or `where` on Windows). If tools are cut off after a while, raise the client's tool timeout: generation can take minutes.

## Long generations

Measured with a 330-second tool call:

| Client | Without progress | With progress, as ImageHearth sends it |
|---|---|---|
| Claude Code | Completes | Completes |
| pi | Stops at 60 s | Completes |
| opencode | Stops | Completes |
| Codex | Stops at 300 s | Stops at 300 s; completes with the `tool_timeout_sec` that `connect` sets |
| Hermes | Stops at 300 s | Completes with the `timeout` that `connect` sets |

## Small local models

Measured on 2026-10-31 with `qwen3.5:9b` in Ollama and no skill. The smallest model tried, 9B, chose the right tool, passed valid parameters, reported the path, and generated and edited while loaded, with its memory back afterwards, in opencode, Hermes, pi and Codex. Nothing smaller has been tried.

## Clients

### Claude Code (`claude-code`)

Support: **Tested**. Method: `claude mcp add --scope user`. Generation, `quality` and Kontext tested with `claude -p`.

<!-- snippet:claude-code -->
```json
{
  "mcpServers": {
    "imagehearth": {
      "command": "/absolute/path/to/imagehearth-mcp"
    }
  }
}
```

### Claude Desktop (`claude-desktop`)

Support: **Untested**. Method: edits `claude_desktop_config.json` (Linux `~/.config/Claude/`, macOS `~/Library/Application Support/Claude/`, Windows `%APPDATA%\Claude\`).

<!-- snippet:claude-desktop -->
```json
{
  "mcpServers": {
    "imagehearth": {
      "command": "/absolute/path/to/imagehearth-mcp"
    }
  }
}
```

### Codex (`codex`)

Support: **Tested**. Method: edits `~/.codex/config.toml`, keeping comments, because `codex mcp add` can't set the timeout. Codex otherwise stops any tool call at 300 s. Tested with a local model through `codex exec --oss`.

<!-- snippet:codex -->
```toml
[mcp_servers.imagehearth]
command = "/absolute/path/to/imagehearth-mcp"
tool_timeout_sec = 1800
```

### Gemini CLI (`gemini`)

Support: **Untested**. Method: `gemini mcp add --scope user`, or `~/.gemini/settings.json`.

<!-- snippet:gemini -->
```json
{
  "mcpServers": {
    "imagehearth": {
      "command": "/absolute/path/to/imagehearth-mcp"
    }
  }
}
```

### opencode (`opencode`)

Support: **Tested**. Method: edits `~/.config/opencode/opencode.json`, because `opencode mcp add` asks questions. A config that only exists as `opencode.jsonc` isn't edited: paste the snippet there.

<!-- snippet:opencode -->
```json
{
  "mcp": {
    "imagehearth": {
      "type": "local",
      "command": [
        "/absolute/path/to/imagehearth-mcp"
      ],
      "enabled": true
    }
  }
}
```

### Hermes (`hermes`)

Support: **Tested**. Method: edits `~/.hermes/config.yaml`, keeping comments, because `hermes mcp add` asks questions. Hermes otherwise stops a tool call at 300 s.

<!-- snippet:hermes -->
```yaml
mcp_servers:
  imagehearth:
    command: /absolute/path/to/imagehearth-mcp
    timeout: 1800
```

### pi (`pi`)

Support: **Tested**. Method: `pi mcp add --exposure direct`. With pi's default exposure, a 9B model did not find the tool.

<!-- snippet:pi -->
```json
{
  "mcpServers": {
    "imagehearth": {
      "command": "/absolute/path/to/imagehearth-mcp",
      "exposure": "direct"
    }
  }
}
```

### VS Code (`vscode`)

Support: **Untested**. Method: edits the user `mcp.json` (Linux `~/.config/Code/User/`, macOS `~/Library/Application Support/Code/User/`, Windows `%APPDATA%\Code\User\`). `connect` itself was run here, but no image was generated from VS Code, so it stays untested.

<!-- snippet:vscode -->
```json
{
  "servers": {
    "imagehearth": {
      "type": "stdio",
      "command": "/absolute/path/to/imagehearth-mcp"
    }
  }
}
```

### Cursor (`cursor`)

Support: **Untested**. Method: edits `~/.cursor/mcp.json`.

<!-- snippet:cursor -->
```json
{
  "mcpServers": {
    "imagehearth": {
      "type": "stdio",
      "command": "/absolute/path/to/imagehearth-mcp"
    }
  }
}
```

### IntelliJ and other JetBrains IDEs (`jetbrains`)

Support: **Untested**. Method: none, `connect` only prints the snippet. Open Settings | Tools | AI Assistant | Model Context Protocol (MCP), choose Add and paste it.

<!-- snippet:jetbrains -->
```json
{
  "mcpServers": {
    "imagehearth": {
      "command": "/absolute/path/to/imagehearth-mcp"
    }
  }
}
```
