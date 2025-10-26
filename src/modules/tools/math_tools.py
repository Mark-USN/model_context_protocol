# math_tools.py

import logging
from typing import TypeVar
from pathlib import Path
from fastmcp import FastMCP

T = TypeVar("T", bound=FastMCP)

logger = logging.getLogger(f"{Path(__file__).stem}")


def add(a: float, b: float) -> str:
    """Add two numbers (strings ok); returns string."""
    return str(float(a) + float(b))

def multiply(a: float, b: float) -> str:
    return str(float(a) * float(b))

def register(mcp: T):
    """Register math tools with MCPServer."""
    logger.info("Registering math tools")
    mcp.tool(tags=["public", "api"])(add)
    mcp.tool(tags=["public", "api"])(multiply)
