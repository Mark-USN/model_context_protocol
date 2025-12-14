""" 20251101 MMH demo_server.py — FastMCP server that discovers 
        tools/prompts/resources.
    Based on https://gofastmcp.com/servers/server
    Added code to automatically register tools and prompts from their packages.
        from the 'tools' package,
"""
# TODO: 20251101 MMH Add resource_loader.py and resource_template_loader.py

import argparse
import logging
from pathlib import Path
from fastmcp import FastMCP
from ..utils.prompt_md_loader import register_prompts_from_markdown
from ..utils.prompt_loader import register_prompts
from ..utils.tool_loader import register_tools
from ..utils.long_tool_loader import register_long_tools


# -----------------------------
# Logging setup
# -----------------------------
logging.basicConfig(
    # level=logging.DEBUG if settings.debug else logging.INFO,
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)-8s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(Path(__file__).stem)

# -----------------------------
# Paths to tool, prompt, resource packages
# -----------------------------
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
    """ 20251101 MMH attach_everything registers all tools and prompts to the FastMCP server.
        Warning: The server will pull in all the code from a tool or prompt package.
        Any error in a file will cause the tools or prompts in that package to be ignored.
        Make sure you trust the code in those packages!
    """
    register_tools(mcp, package=_TOOLS_DIR)
    logger.info("✅	 Tools registered.")

    register_long_tools(mcp, package=_TOOLS_DIR)
    logger.info("✅	 Tools registered.")

    register_prompts_from_markdown(mcp, prompts_dir=_PROMPTS_DIR)
    logger.info("✅	 Markdown files parsed and prompts registered.")

    register_prompts(mcp, package=_PROMPTS_DIR)
    logger.info("✅	 Prompt functions registered.")

def launch_server(host:str="127.0.0.1", port:int=8085):
    """ 20251101 MMH launch_server
        The entry point to start the FastMCP server. 
        Launch the FastMCP server with all tools and prompts attached. 
    """
    attach_everything()
    mcp.run(transport="http", host=host, port=port)
    logger.info("✅	 Server started on http://{host}:{port}")


# -----------------------------
# CLI (kept as before)
# -----------------------------
def port_type(value: str) -> int:
    """ 20251101 MMH port_type
        Custom argparse type that validates a TCP port number.
    """
    try:
        port = int(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"Port must be an integer (got {value!r})") from e
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError(f"Port number must be between 1 and 65535 (got {port})")
    return port

def main():
    """ 20251101 MMH main
        Main entry point when launched "stand alone" 
        Parse arguments and start the server. 
    """
    parser = argparse.ArgumentParser(description="Create and run an MCP server.")
    parser.add_argument("--host", type=str, default="127.0.0.1",
                        help="Host name or IP address (default 127.0.0.1).")
    parser.add_argument("--port", type=port_type, default=8085,
                        help="TCP port to bind/connect (default 8085).")
    args = parser.parse_args()

    launch_server(args.host, args.port)

if __name__ == "__main__":
    main()
