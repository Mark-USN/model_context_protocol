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

def youtube_query_normalizer(
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
Also extract structured components from the SAME input (do not invent any terms).

Rules:
1) Preserve exact phrases:
   - Keep quoted text exactly as a phrase in the query, including quotes.
     Example: "quantum diffraction"
   - Populate "phrases" with each quoted phrase WITHOUT the surrounding quotes.
     Example: "quantum diffraction" -> phrases includes ["quantum diffraction"]

2) Handle includes/excludes:
   - +term means REQUIRED:
       * Ensure the term appears in the query as a normal (non-prefixed) term.
       * Add the raw term (without '+') to "includes".
   - -term means EXCLUDED:
       * Ensure the term appears in the query as a negated term (e.g., -term).
       * Add the raw term (without '-') to "excludes".
   - Do not invent new terms.

3) Boolean logic:
   - Preserve OR / | (case-insensitive) by grouping with parentheses where needed.
     Example: (slit OR grating)

4) Restrictions:
   - Preserve title:xxx as a title restriction in the query.
   - Preserve channel:Name as a channel restriction in the query.
   - Populate "channels" with each channel name WITHOUT the "channel:" prefix.
   - Do not add site: filters unless explicitly requested.

5) Normalization:
   - Normalize whitespace (single spaces).
   - Keep operator precedence clear with parentheses where needed.
   - Deduplicate items within includes/excludes/phrases/channels.
   - Keep ordering stable: preserve first-appearance order from the input.

Output:
Return a JSON object with exactly these fields (and nothing else):

{{
  "query": "<normalized google/youtube search string>",
  "includes": ["..."],
  "excludes": ["..."],
  "phrases": ["..."],
  "channels": ["..."],
  "notes": "One sentence max: what was preserved/normalized."
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
    mcp.prompt(tags=["public", "api", "youtube"])(youtube_query_normalizer)
