# tools/basketball_tool.py
"""
Basketball statistics tool.
Simulates retrieving player and team statistics.
"""

# from pathlib import Path
import logging
from typing import Any, Dict, TypeVar
from fastmcp import FastMCP
from modules.utils.log_utils import get_logger


T = TypeVar("T", bound=FastMCP)

# -----------------------------
# Logging setup
# -----------------------------
logger = get_logger(__name__)

# -----------------------
# Core Functions
# -----------------------
def get_team_stats(team_name: str) -> Dict[str, Any]:
    """Return mock basketball team statistics."""
    if not isinstance(team_name, str) or not team_name.strip():
        logger.error("❌ Invalid team name provided.")
        return {"status": "error", "error": "Invalid team name."}

    # Mock data
    logger.debug("✅ Retrieving stats for team: %s.", team_name)
    return {
        "status": "ok",
        "function": "get_team_stats",
        "team": team_name.title(),
        "wins": 28,
        "losses": 14,
        "top_players": ["Jordan", "Pippen", "Rodman"],
    }


# -----------------------
# MCP Registration
# -----------------------
def register(mcp: T):
    """Register basketball tools with MCPServer."""
    logger.info("✅ Registering basketball tools")
    mcp.tool(tags=["public", "api"])(get_team_stats)


# -----------------------
# CLI Testing
# -----------------------
if __name__ == "__main__":
    print("🏀 Testing Basketball Tool")
    team = input("Enter team name: ")
    print(get_team_stats(team))
