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
        "--variant",
        choices=("fp8", "gguf", "sdxl"),
        help="Force a variant of quality or full instead of the one that fits the GPU memory.",
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
