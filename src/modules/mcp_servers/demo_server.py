""" 20251101 MMH demo_server.py — FastMCP server that discovers 
        tools/prompts/resources.
    Based on https://gofastmcp.com/servers/server
    Added code to automatically register tools and prompts from their packages.
        from the 'tools' package,
"""
# TODO: 20251101 MMH Add resource_loader.py and resource_template_loader.py

import argparse
# import logging
import time
from pathlib import Path
from fastmcp import FastMCP
from modules.utils.log_utils import LogConfig, configure_logging, get_logger # , log_tree
from modules.utils.prompt_md_loader import register_prompts_from_markdown
from modules.utils.prompt_loader import register_prompts
from modules.utils.tool_loader import register_tools
from modules.utils.paths import resolve_cache_paths, get_module_path
# from modules.utils.long_tool_loader import register_long_tools


# -----------------------------
# Logging setup
# -----------------------------
logger = get_logger(__name__)

# -----------------------------
# Paths to tool, prompt, resource packages
# -----------------------------
def _get_tools_dir()->Path:
    return get_module_path(start = Path(__file__)) / "Tools"

def _get_prompts_dir()->Path:
    return get_module_path(start = Path(__file__)) / "Prompts"

def _get_resources_dir()->Path:
    return get_module_path(start = Path(__file__)) / "Resources"

def _get_cache_dir()->Path:
    cache_path = get_module_path(start = Path(__file__)) / "Cache"
    cache_path.mkdir(parents=True, exist_ok=True)
    return cache_path



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
def purge_cache(days: int = 7) -> None:
    """ Purge transcript cache files older than `days` days.
        Args:
            days (int): Number of days to keep cache files. Default is 7 days.
    """
    # All audio files should be deleted after they are transcribed. So ony 
    # files that are currently being transcribed or possibly failed transcriptions
    # should be here.

    cutoff = time.time() - (days * 86400)

    audio_dir = resolve_cache_paths(
                app_name = "audio",
                start = Path(__file__)
            ).base_cache_dir
    if audio_dir.exists():
        for f in audio_dir.iterdir():
            if f.is_file() and f.stat().mt_atime < cutoff:
                f.unlink(missing_ok=True)

    transcript_dir = resolve_cache_paths(
                app_name = "transcripts",
                start = Path(__file__)
            ).base_cache_dir
    if transcript_dir.exists():
        for f in transcript_dir.iterdir():
            if f.is_file() and f.stat().mt_atime < cutoff:
                f.unlink(missing_ok=True)


# -----------------------------------------
# Attach everything to FastMCP at startup
# -----------------------------------------
def attach_everything():
    """ 20251101 MMH attach_everything registers all tools and prompts to the FastMCP server.
        Warning: The server will pull in all the code from a tool or prompt package.
        Any error in a file will cause the tools or prompts in that package to be ignored.
        Make sure you trust the code in those packages!
    """
    register_tools(mcp, package=_get_tools_dir())
    logger.info("✅	 Tools registered.")

    # register_long_tools(mcp, package=_TOOLS_DIR)
    # logger.info("✅	 Long tools registered.")

    register_prompts_from_markdown(mcp, prompts_dir=_get_prompts_dir())
    logger.info("✅	 Markdown files parsed and prompts registered.")

    register_prompts(mcp, prompts_dir=_get_prompts_dir())
    logger.info("✅	 Prompt functions registered.")

def launch_server(host:str="127.0.0.1", port:int=8085):
    """ 20251101 MMH launch_server
        The entry point to start the FastMCP server. 
        Launch the FastMCP server with all tools and prompts attached. 
    """
    logger.info("✅ demo_server started.")
    attach_everything()
    mcp.run(transport="http", host=host, port=port)
    logger.info("✅	 Demo Server started on http://{host}:{port}")


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
    # -----------------------------
    # Logging setup
    # -----------------------------
    configure_logging(LogConfig(level="INFO"))
    


    main()
