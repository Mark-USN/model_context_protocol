"""Definition of prompt functions for use with an MCP server (mcp_yt_server)."""

from __future__ import annotations

# import logging
from typing import TypeVar
from fastmcp import FastMCP
from fastmcp.prompts.prompt import Message, PromptResult # ,PromptMessage, TextContent
from pydantic import Field
from modules.utils.log_utils import get_logger # , log_tree


T = TypeVar("T", bound=FastMCP)

logger = get_logger(__name__)

def youtube_query_normalizer_prompt(
    search_string: str = Field(
        description=(
            "Raw user search string. May include quoted phrases, +required terms, -excluded terms, "
            "OR/| groups, and restrictions like title: and channel:."
        )
    ),
) -> PromptResult:
    """Return a prompt that instructs an AI to normalize a YouTube query into advanced search syntax."""
    return [
        Message(
            f"""You are a search-query normalizer for YouTube.

Input:
- search_string: {search_string}

Task:
Convert search_string into a Google/YouTube advanced search query string that preserves intent and constraints.

Rules:
1) Preserve exact phrases:
   - Keep quoted text exactly as a phrase, including quotes.
     Example: "quantum diffraction"

2) Handle includes/excludes:
   - +term means REQUIRED → include the term in the query (required).
   - -term means EXCLUDED → keep it as a negated term.
   - Do not invent new terms.

3) Boolean logic:
   - Preserve OR / | (case-insensitive) by grouping with parentheses.
     Example: (slit OR grating)

4) Restrictions:
   - Preserve title:xxx as a title restriction.
   - Preserve channel:Name as a channel restriction.
   - Do not add site: filters unless explicitly requested.

5) Normalization:
   - Normalize whitespace.
   - Keep operator precedence clear with parentheses where needed.

Output:
Return a JSON object with exactly these fields (and nothing else):

{{
  "query": "<normalized google/youtube search string>",
  "includes": ["..."],
  "excludes": ["..."],
  "phrases": ["..."],
  "channels": ["..."],
  "notes": "Short explanation of what was preserved/changed"
}}

Do NOT execute any search. Do NOT call any tools.
Only produce the JSON object.
"""
        )
    ]


def register(mcp: T) -> None:
    """Register prompts with the MCP server instance."""
    logger.info("✅ Registering prompts")

    # YouTube-specific prompt (query normalization)
    mcp.prompt(tags=["public", "api", "youtube"])(youtube_query_normalizer_prompt)
