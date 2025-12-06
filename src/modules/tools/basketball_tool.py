# tools/basketball_tool.py
"""
Basketball statistics tool.
Simulates retrieving player and team statistics.
"""

import logging
from pathlib import Path
from typing import Any, Dict, TypeVar
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
