import argparse
from importlib.metadata import version


def main(argv=None):
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
    parser.parse_args(argv)

    # Se importa aquí para que --version no cargue el servidor.
    from imagehearth_mcp.server import mcp

    mcp.run(transport="stdio")
