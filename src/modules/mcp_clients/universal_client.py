"""
Universal MCP client.

Connects to a FastMCP server, lists its tools/resources/templates/prompts,
and exercises known workflows using safe, deterministic arguments.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastmcp import Client
from modules.utils.log_utils import configure_logging, get_logger
from modules.utils.paths import resolve_cache_paths
from .youtube_demo import run_youtube_demo

logger = get_logger(__name__)

RUN_PROMPT_EXAMPLES = True
RUN_TOOL_EXAMPLES = True


@dataclass(slots=True, frozen=True)
class ServerConfig:
    host: str
    port: int

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/mcp"


class UniversalClient(Client):
    """Universal FastMCP client.

    Responsibilities:
    - connect to server
    - list tools/resources/templates/prompts
    - exercise known workflows when available
    """

    yt_search: str = ""
    MAX_SEARCH_RESULTS: int = 5

    tools_list: list[Any]
    tool_names: set[str]

    def __init__(self, host: str, port: int) -> None:
        self.config = ServerConfig(host, port)
        super().__init__(self.config.url)
        self.tools_list = []
        self.tool_names = set()

    # -------------------------------------------------
    # Paths
    # -------------------------------------------------
    def cache_output_dir(self) -> Path:
        return resolve_cache_paths(
            app_name="universal_client",
            start=Path(__file__),
        ).app_cache_dir

    # -------------------------------------------------
    # Server discovery
    # -------------------------------------------------
    async def refresh_tools(self) -> None:
        """Query the server for tools and cache their names."""
        self.tools_list = await self.list_tools()
        self.tool_names = {
            getattr(t, "name", "")
            for t in self.tools_list
            if getattr(t, "name", "")
        }

    # -------------------------------------------------
    # Main entry point
    # -------------------------------------------------
    async def run(self) -> None:
        async with self:
            await self.ping()

            await self.refresh_tools()
            self._show_tools(self.tools_list)

            resources = await self.list_resources()
            self._show_resources(resources)

            templates = await self.list_resource_templates()
            self._show_templates(templates)

            prompts = await self.list_prompts()
            self._show_prompts(prompts)

            if RUN_PROMPT_EXAMPLES:
                await self._run_example_prompts(prompts)

            if RUN_TOOL_EXAMPLES:
                await self._run_example_tools()

    # -------------------------------------------------
    # Exercisers
    # -------------------------------------------------
    async def _run_example_tools(self) -> None:
        """Exercise known workflows using server-discovered tools."""
        if "youtube_search" not in self.tool_names:
            logger.info("youtube_search not available; skipping tool exercises.")
            return

        transcript_tools = {
            "youtube_snippets",
            "youtube_json",
            "youtube_text",
            "youtube_paragraph",
        }
        if not (self.tool_names & transcript_tools):
            logger.info("No transcript tools available; skipping YouTube demo.")
            return

        await run_youtube_demo(self)

    async def _run_example_prompts(self, prompts: list[Any]) -> None:
        names = {getattr(p, "name", "") for p in prompts if getattr(p, "name", "")}
        if "youtube_query_normalizer" not in names:
            return

        search_string = "Find English language videos on python list comprehensions"
        logger.info("Executing youtube_query_normalizer prompt")
        result = await self.get_prompt(
            "youtube_query_normalizer",
            {"search_string": search_string},
        )

        # 20260125 MMH dump the result from youtube_query_normalizer
        logger.info("youtube_query_normalizer result = \n%s",json.dumps(result, indent=2, ensure_ascii=False))

        for msg in getattr(result, "messages", []) or []:
            logger.info("Prompt output: %s", getattr(msg, "content", msg))

    # -------------------------------------------------
    # Display helpers
    # -------------------------------------------------
    def _show_tools(self, tools: list[Any]) -> None:
        logger.info("\nAvailable Tools:\n")
        for t in tools:
            logger.info("Tool: %s", getattr(t, "name", None))

    def _show_resources(self, resources: list[Any]) -> None:
        logger.info("\nAvailable Resources:\n")
        for r in resources:
            logger.info("Resource: %s", getattr(r, "uri", None))

    def _show_templates(self, templates: list[Any]) -> None:
        logger.info("\nAvailable Resource Templates:\n")
        for t in templates:
            logger.info("Template: %s", getattr(t, "uriTemplate", None))

    def _show_prompts(self, prompts: list[Any]) -> None:
        logger.info("\nAvailable Prompts:\n")
        for p in prompts:
            logger.info("Prompt: %s", getattr(p, "name", None))


def main() -> None:
    from modules.utils.log_utils import configure_logging, get_logger

    configure_logging(log_level=logging.INFO)
    asyncio.run(UniversalClient("127.0.0.1", 8085).run())


if __name__ == "__main__":
    main()
