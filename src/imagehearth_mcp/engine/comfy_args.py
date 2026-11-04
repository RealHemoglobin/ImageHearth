"""Memory arguments for ComfyUI, chosen from the hardware.

ComfyUI already loads a model in parts when it doesn't fit (its NORMAL_VRAM
mode). These arguments only move the thresholds where it gives up VRAM for
speed. The values are the starting point, not a measurement: `comfy_args` in
config.toml is added at the end, so it always wins.
"""

from imagehearth_mcp.engine import config
from imagehearth_mcp.engine.log import get_logger

log = get_logger("comfy_args")

# VRAM in MiB.
NOVRAM_BELOW = 4096
LOWVRAM_BELOW = 8192
RESERVE_BELOW = 20000


def hardware():
    """(system, vram_mib, ram_mib) of the main GPU; vram is 0 if unknown."""
    from imagehearth_mcp.provisioner import detect

    detection = detect.detect()
    gpu = detection.primary_gpu
    return detection.system, gpu.vram_mib if gpu else 0, detection.ram_mib


def choose(system, vram_mib, ram_mib):
    """Arguments picked for this hardware, without the user's own."""
    if not vram_mib:
        return []

    if vram_mib < NOVRAM_BELOW:
        return ["--novram"]

    if vram_mib < LOWVRAM_BELOW:
        return ["--lowvram"]

    if vram_mib < RESERVE_BELOW:
        # The desktop needs some VRAM too; Windows keeps more for itself.
        return ["--reserve-vram", "1.0" if system == "windows" else "0.5"]

    return []


def effective(detected=None):
    """Chosen arguments followed by the user's `comfy_args`."""
    try:
        chosen = choose(*(detected or hardware()))
    except Exception as error:  # noqa: BLE001 - detection must never keep ComfyUI from starting.
        log.warning("Could not detect the hardware for ComfyUI's arguments: %s", error)
        chosen = []

    return [*_without_overridden(chosen), *config.COMFY_ARGS]


VRAM_MODES = {"--novram", "--lowvram", "--normalvram", "--highvram", "--gpu-only"}


def _without_overridden(chosen):
    """Drops chosen arguments that the user sets themselves (ComfyUI rejects conflicting modes)."""
    user = set(config.COMFY_ARGS)
    result = []
    index = 0

    while index < len(chosen):
        argument = chosen[index]
        takes_value = argument == "--reserve-vram"
        width = 2 if takes_value else 1

        overridden = (
            argument in user
            or (argument in VRAM_MODES and user & VRAM_MODES)
            or (takes_value and any(u.startswith("--reserve-vram=") for u in user))
        )

        if not overridden:
            result.extend(chosen[index : index + width])

        index += width

    return result
