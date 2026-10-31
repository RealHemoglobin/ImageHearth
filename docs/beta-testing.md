# Help test the ImageHearth beta

ImageHearth has been measured on one machine: an RTX 4090 with 24 GB on Linux. It needs to meet other hardware before version 0.1.0.

## Who we're looking for

Anyone with **Linux or Windows 11 and an NVIDIA GPU, series 20 or newer**, and an MCP agent such as Claude Code, Codex, opencode or Hermes. Different hardware helps most: cards with 8, 12 or 16 GB, laptops, older drivers, other distributions, or an existing ComfyUI.

You need 14 GB of free disk for the smallest profile. FLUX models are non-commercial, and setup shows each license before downloading.

Other GPUs and macOS are welcome too, but they're experimental. A report that it failed is still useful.

## What to try

Please try it **without help first**: where you get stuck is what we most want to know.

1. Install with the one-line command in the [README](../README.md). Time it, if you can.
2. Restart your agent and ask for an image with the fast quality.
3. If you installed `quality` or `full`, ask for a high-quality image. With `full`, ask it to edit that image.
4. Run `imagehearth-mcp doctor`.

If you'd like to go further: interrupt a download and run setup again, use an existing ComfyUI, keep a local language model loaded, or run `imagehearth-mcp uninstall` and check what it leaves.

## How to report

Whether it worked or not, [open an issue](https://github.com/RealHemoglobin/ImageHearth/issues/new/choose). If something failed, use the installation template. If it worked, please send this:

```markdown
**System and GPU:** (for example, Ubuntu 24.04, RTX 3060 12 GB)
**Agent and model:** (for example, opencode with qwen3.5:9b)
**Profile:** fast / quality / full
**Installed without help:** yes / no. If no, where did you get stuck?
**Generated an image:** yes / no
**Time per image:** first and next ones, if you noted them
**Anything confusing:**

<details><summary>doctor --json</summary>

(paste the output of `imagehearth-mcp doctor --json`)

</details>
```

`doctor --json` includes local paths, which may show your user name: replace it if you prefer. It doesn't include prompts or images, and ImageHearth sends nothing anywhere.
