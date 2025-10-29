# demo_server.py — FastMCP server that discovers tools/prompts/resources without a registry.

import os
import sys
import argparse
import logging
import importlib
import json
import pkgutil
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Tuple

# from regex import T
from ..utils.prompt_md_loader import register_prompts_from_markdown
from ..utils.prompt_loader import register_prompts
from ..utils.tool_loader import register_tools
from ..utils.get_icons import get_icon

from fastmcp import FastMCP

logging.basicConfig(
    # level=logging.DEBUG if settings.debug else logging.INFO,
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)-8s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(Path(__file__).stem)

_MODULES_DIR = Path(__file__).parents[1].resolve()
_TOOLS_DIR = _MODULES_DIR / "tools"
_PROMPTS_DIR = _MODULES_DIR / "prompts"
_RESOURCES_DIR = _MODULES_DIR / "resources"


# -----------------------------
# Server instance & conventions
# -----------------------------
mcp = FastMCP(
    name="DemoServer",
    include_tags={"public", "api"},
    exclude_tags={"internal", "deprecated"},
    on_duplicate_tools="error",
    on_duplicate_resources="warn",
    on_duplicate_prompts="replace",
    # strict_input_validation=False,
    include_fastmcp_meta=False,
)




# -----------------------------------------
# Attach everything to FastMCP at startup
# -----------------------------------------
def attach_everything():
    register_tools(mcp, package=_TOOLS_DIR)
    logger.info(f"{get_icon('check')} Tools registered.")

    register_prompts_from_markdown(mcp, prompts_dir=_PROMPTS_DIR)
    logger.info(f"{get_icon('check')} Markdown files parsed and prompts registered.")

    register_prompts(mcp, package=_PROMPTS_DIR)
    logger.info(f"{get_icon('check')} Prompt functions registered.")




def launch_server(host:str="127.0.0.1", port:int=8085):
    attach_everything()
    mcp.run(transport="http", host=host, port=port)
    logger.info(f"{get_icon('check')} Server started on http://{host}:{port}")


# -----------------------------
# CLI (kept as before)
# -----------------------------
def port_type(value: str) -> int:
    """Custom argparse type that validates a TCP port number."""
    try:
        port = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"Port must be an integer (got {value!r})")
    if not (1 <= port <= 65535):
        raise argparse.ArgumentTypeError(f"Port number must be between 1 and 65535 (got {port})")
    return port

def main():
    parser = argparse.ArgumentParser(description="Create and run an MCP server.")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host name or IP address (default 127.0.0.1).")
    parser.add_argument("--port", type=port_type, default=8085, help="TCP port to bind/connect (default 8085).")
    args = parser.parse_args()

    launch_server(args.host, args.port)

if __name__ == "__main__":
    main()
