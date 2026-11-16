import argparse
import sys
from importlib.metadata import version


def _add_consent(parser):
    parser.add_argument(
        "--accept-licenses",
        action="store_true",
        help="Accept the model licenses without asking. Required to download "
        "in non-interactive mode.",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Never ask: fail instead when a decision is missing.",
    )


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="imagehearth-mcp",
        description="MCP server for local image generation and editing. "
        "Without arguments it serves MCP over stdio.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {version('imagehearth-mcp')}",
    )
    commands = parser.add_subparsers(dest="command", metavar="command")

    setup = commands.add_parser(
        "setup", help="Install ComfyUI and the models, or attach to an existing ComfyUI."
    )
    setup.add_argument(
        "--profile",
        choices=("fast", "quality", "full", "mac-fast", "mac-quality", "mac-full"),
        help="What to install. The mac-* profiles are only for macOS.",
    )
    setup.add_argument(
        "--fast-models",
        metavar="NAMES",
        help="Models for fast generation (quick drafts): a comma-separated list of "
        "name[:precision], e.g. klein-4b,z-image-turbo:int8. The first is the default. "
        "Choose from: sdxl-turbo, z-image-turbo, klein-4b. Without a precision, the one "
        "recommended for the GPU. On an existing installation the list fixes the set: the "
        "missing models are downloaded first and the others deleted afterwards. Without "
        "it the fast models are left as they are.",
    )
    setup.add_argument(
        "--quality-models",
        metavar="NAMES",
        help="Models for high-quality generation (quality and full profiles), same format. "
        "Choose from: sdxl, flux-dev, flux-schnell, chroma-hd, qwen-image, hidream-full. "
        "flux-dev has a non-commercial license; hidream-full shows the Llama 3.1 license. "
        "Choosing others replaces the installed ones: downloaded first, deleted afterwards.",
    )
    setup.add_argument(
        "--edit-models",
        metavar="NAMES",
        help="Models for image editing (full profile), same format. Choose from: kontext, "
        "klein-4b, qwen-image-edit.",
    )
    setup.add_argument(
        "--quality-model",
        metavar="NAME",
        help="Same as --quality-models with one model (kept from earlier versions).",
    )
    setup.add_argument(
        "--loras",
        metavar="NAMES",
        help="Style LoRAs for SDXL 1.0: a comma-separated list of names, all or none. On "
        "an existing installation it fixes the set: the ones missing are downloaded and "
        "the others deleted. Without it the LoRAs are left as they are. Needs sdxl "
        "among the quality models.",
    )
    setup.add_argument(
        "--variant",
        choices=("fp8", "gguf"),
        help="Precision for the models that don't name one with name:precision, where they "
        "have it, instead of the one recommended for the GPU memory.",
    )
    setup.add_argument(
        "--yes",
        action="store_true",
        help="Confirm replacing or removing installed models without asking.",
    )
    setup.add_argument(
        "--experimental",
        action="store_true",
        help="Required on macOS, which is prepared but untested.",
    )
    _add_consent(setup)
    mode = setup.add_mutually_exclusive_group()
    mode.add_argument(
        "--managed", action="store_true", help="Install a ComfyUI of its own."
    )
    mode.add_argument(
        "--attach", metavar="PATH", help="Use the existing ComfyUI in PATH."
    )
    setup.add_argument(
        "--install-node",
        action="store_true",
        help="Allow installing the status node in an attached ComfyUI.",
    )
    setup.add_argument(
        "--install-dir",
        metavar="PATH",
        help="Install ComfyUI in PATH/comfyui, and the models in PATH/comfyui/models "
        "unless --models-dir says otherwise. Not compatible with --attach.",
    )
    setup.add_argument(
        "--models-dir",
        metavar="PATH",
        help="Keep the models here and share them through extra_model_paths.yaml.",
    )
    setup.add_argument("--port", type=int, help="Port ComfyUI listens on.")
    setup.add_argument(
        "--batch-limit",
        type=int,
        metavar="N",
        help="Most images one create_image call may ask for (default 20).",
    )
    setup.add_argument(
        "--skip-smoke-test",
        action="store_true",
        help="Don't generate the final test image.",
    )

    doctor = commands.add_parser("doctor", help="Check every layer of the installation.")
    doctor.add_argument("--json", action="store_true", help="Print the result as JSON.")
    doctor.add_argument(
        "--verify-hashes",
        action="store_true",
        help="Compare the SHA-256 of each model instead of only its size (slow).",
    )

    update = commands.add_parser(
        "update", help="Apply the pinned ComfyUI version and the current model manifest."
    )
    _add_consent(update)
    update.add_argument(
        "--move-to",
        metavar="PATH",
        help="Move the ComfyUI that ImageHearth installed, and the models it downloaded, "
        "to PATH/comfyui. Repeat the command to finish an interrupted move; use the "
        "current folder to cancel it.",
    )
    update.add_argument(
        "--yes",
        action="store_true",
        help="With --move-to, move without asking.",
    )

    uninstall = commands.add_parser(
        "uninstall", help="Remove only what setup installed."
    )
    uninstall.add_argument(
        "--yes", action="store_true", help="Don't ask for confirmation."
    )
    uninstall.add_argument(
        "--remove-models",
        action="store_true",
        help="Also remove the models setup downloaded, without asking.",
    )
    uninstall.add_argument(
        "--keep-models",
        action="store_true",
        help="Keep the models setup downloaded, without asking.",
    )
    connect = commands.add_parser(
        "connect", help="Add ImageHearth to an agent or editor, with a backup first."
    )
    connect.add_argument("agent", nargs="?", help="Which one. See --list.")
    action = connect.add_mutually_exclusive_group()
    action.add_argument(
        "--print",
        action="store_true",
        dest="print_only",
        help="Only print the configuration snippet; nothing is changed.",
    )
    action.add_argument(
        "--detect",
        action="store_true",
        help="Find the installed clients and offer to connect them.",
    )
    action.add_argument(
        "--list", action="store_true", dest="list_clients", help="List known clients."
    )
    action.add_argument(
        "--remove", action="store_true", help="Remove ImageHearth from that client."
    )
    connect.add_argument("--yes", action="store_true", help="Don't ask for confirmation.")
    connect.add_argument(
        "--no-skill", action="store_true", help="Don't install the optional skill."
    )
    return parser


def _run_command(args):
    # Cada comando se importa al usarse: el servidor MCP no carga el provisioner.
    from imagehearth_mcp.engine.errors import ConfigError
    from imagehearth_mcp.provisioner import ProvisionError

    try:
        if args.command == "doctor":
            from imagehearth_mcp.provisioner.doctor import run
        elif args.command == "setup":
            from imagehearth_mcp.provisioner.setup import run
        elif args.command == "connect":
            from imagehearth_mcp.provisioner.connect import run
        elif args.command == "update":
            from imagehearth_mcp.provisioner.maintenance import update as run
        else:
            from imagehearth_mcp.provisioner.maintenance import uninstall as run

        return run(args)
    except (ProvisionError, ConfigError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(
            "\nInterrupted. Run the same command again to continue.", file=sys.stderr
        )
        return 130


def main(argv=None):
    args = _build_parser().parse_args(argv)

    if args.command:
        sys.exit(_run_command(args))

    from imagehearth_mcp.engine.errors import ConfigError

    # Se importa aquí para que --version no cargue el servidor.
    try:
        from imagehearth_mcp.server import mcp
    except ConfigError as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)

    mcp.run(transport="stdio")
