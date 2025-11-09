# math_tools.py

import logging
from typing import TypeVar
from pathlib import Path
from fastmcp import FastMCP

T = TypeVar("T", bound=FastMCP)

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
