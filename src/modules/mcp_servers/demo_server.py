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
from ..utils.prompt_mod_loader import register_prompts
from ..utils.tool_loader import register_tools

from fastmcp import FastMCP

logging.basicConfig(
    # level=logging.DEBUG if settings.debug else logging.INFO,
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)-8s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(Path(__file__).stem)


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


_THIS_DIR = Path(__file__).resolve().parent
_TOOLS_PKG = (__package__ + ".tools") if __package__ else "tools"
_PROMPTS_DIR = _THIS_DIR / "prompts"
_RESOURCES_DIR = _THIS_DIR / "resources"


# -----------------------------------------
# Attach everything to FastMCP at startup
# -----------------------------------------
def attach_everything():
    # 1) Attach tools
    register_tools(mcp, package=_TOOLS_PKG)

    # 2) Load prompts/resources & expose helper tools
    register_prompts_from_markdown(mcp, prompts_dir=_PROMPTS_DIR)
    register_prompts(mcp, package=_PROMPTS_DIR)


    # load_resources_from_dir(_RESOURCES_DIR)


    # @mcp.tool(name="list_prompts", description="List all discovered prompts.")
    # def _list_prompts():
    #     return {"count": len(PROMPTS), "items": [{"name": p["name"], "meta": p["meta"]} for p in PROMPTS.values()]}

    # @mcp.tool(
    #     name="get_prompt",
    #     description="Return prompt text and metadata by name.",
    #     # inputSchema={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
    # )
    # def _get_prompt(name: str):
    #     p = PROMPTS.get(name)
    #     if not p:
    #         raise ValueError(f"Unknown prompt: {name}")
    #     return p

    # @mcp.tool(name="list_resources", description="List all discovered resources.")
    # def _list_resources():
    #     return {
    #         "count": len(RESOURCES),
    #         "items": [{"name": r["name"], "uri": r["uri"], "mime": r["mime"], "meta": r["meta"]} for r in RESOURCES.values()],
    #     }

    # @mcp.tool(
    #     name="get_resource",
    #     description="Return resource descriptor by name.",
    #     # inputSchema={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
    # )
    # def _get_resource(name: str):
    #     r = RESOURCES.get(name)
    #     if not r:
    #         raise ValueError(f"Unknown resource: {name}")
    #     return r


def launch_server(host:str="127.0.0.1", port:int=8085):
    attach_everything()
    mcp.run(transport="http", host=host, port=port)
    print(f"Server started on http://{host}:{port}")


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

    # # 20251018 MMH Add environment variable to wait for debugger attach, then run the code below.

    launch_server(args.host, args.port)

if __name__ == "__main__":
    main()
