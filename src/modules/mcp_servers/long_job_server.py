""" MCP module: HMAC-authenticated long-running jobs with session isolation."""
# import os
# import sys
# import hmac
# import json
# import uuid
# import base64
#import asyncio
# import inspect
# from contextlib import contextmanager
# from functools import wraps
# import importlib
# import pkgutil
# from dataclasses import dataclass, field
# from enum import Enum
# from modules.utils.tokens import requires_token
import time
import argparse
import logging
from pathlib import Path
from typing import Any, Callable, Dict, Optional, TypeVar, cast
from fastmcp import FastMCP
from modules.utils.logging_config import setup_logging
from modules.utils.jobs import long_tools_require_token
from modules.utils.prompt_md_loader import register_prompts_from_markdown
from modules.utils.prompt_loader import register_prompts
from modules.utils.tool_loader import register_tools
from modules.utils.long_tool_loader import register_long_tools
from modules.utils.paths import get_module_path, resolve_cache_paths


# mcp = FastMCP(name="MCP-HMAC-LongJobs")

# -----------------------------
# Logging setup
# -----------------------------
logger = logging.getLogger(__name__)

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
# From demo_server.py: Paths to tool, prompt, resource packages
# -----------------------------

mcp = FastMCP(
    name="LongJobServer",
    include_tags={"public", "api"},
    exclude_tags={"internal", "deprecated"},
    on_duplicate_tools="error",
    on_duplicate_resources="warn",
    on_duplicate_prompts="replace",
    # strict_input_validation=False,
    include_fastmcp_meta=False,
)


def purge_server_cache(days: int = 7) -> None:
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
            )
    if audio_dir.exists():
        for f in audio_dir.iterdir():
            if f.is_file() and f.stat().mt_atime < cutoff:
                f.unlink(missing_ok=True)

    transcript_dir = resolve_cache_paths(
                app_name = "transcripts",
                start = Path(__file__)
            )
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
    # Regular tools behave exactly like demo_server
    register_tools(mcp, package=_get_tools_dir())
    logger.info("✅\t Tools registered.")

    # Long tools: only those registered via register_long_tools are wrapped as background jobs
    with long_tools_require_token(mcp):
        register_long_tools(mcp, package=_get_tools_dir())
    logger.info("✅\t Long tools registered (launch as jobs; token required).")

    register_prompts_from_markdown(mcp, prompts_dir=_get_prompts_dir())
    logger.info("✅\t Prompts from markdown registered.")

    register_prompts(mcp, prompts_dir=_get_prompts_dir())
    logger.info("✅\t Prompts registered.")


def launch_server(host:str="127.0.0.1", port:int=8085):
    """ 20251101 MMH launch_server
        The entry point to start the FastMCP server. 
        Launch the FastMCP server with all tools and prompts attached. 
    """

    logger.info("✅ long_job_server started.")
    attach_everything()
    mcp.run(transport="http", host=host, port=port)
    logger.info("✅	 Long Job Server started on http://{host}:{port}")


def main():
    parser = argparse.ArgumentParser(description="MCP long-job server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8085)
    args = parser.parse_args()

    host = args.host
    port = args.port

    logger.info("✅ long_job_server started.")
    attach_everything()
    mcp.run(transport="http", host=host, port=port)
    logger.info("✅\t Server started on http://{host}:{port}")


if __name__ == "__main__":
    # -----------------------------
    # Logging setup
    # -----------------------------
    setup_logging()

    main()
