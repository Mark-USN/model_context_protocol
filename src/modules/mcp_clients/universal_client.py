""" 20251003 MMH universal_client.py
    Connect to an mcp server and output its available tools, resources,
    templates, and prompts
    Based on https://gofastmcp.com/clients/client
"""
# import json
# from ..utils.logging_config import setup_logging
import asyncio
from pathlib import Path
import logging
from typing import Any, List, Dict, Optional # , TypeVar
from .youtube_demo import run_youtube_demo

from fastmcp import Client

# -----------------------------
# Logging setup
# -----------------------------
# setup_logging()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------
# Control which examples to run
# ---------------------------------------------------------------------
RUN_PROMPT_EXAMPLES = True
RUN_TOOL_EXAMPLES = True


class UniversalClient(Client):
    """ 20251003 MMH universal_client class
        A universal MCP client that connects to a FastMCP server,
        lists available tools, resources, templates, and prompts,
        and demonstrates calling some example tools.
    """
    # Variable to hold YouTube URL
    yt_search: str = ""
    session_info: Optional[Dict[str, Any]] = None
    MAX_SEARCH_RESULTS: int = 5
    _next_allowed_ts: float = 0.0  # simple global limiter
    tools_list: List[str]= []
    tool_names: set = set()


    def __init__(self, host: str, port: int):
        """ 20251003 MMH universal_client __init__
            Initialize the universal_client with server host and port.
        """
        self.url = f"http://{host}:{port}/mcp"
        super().__init__(self.url)

# ---------------------------------------------------------------------
# Helper Methods
# ---------------------------------------------------------------------
    def get_tool_names(self) -> set:
        """ Return a set of available tool names on the server. """
        return self.tool_names


    def base_output_dir(self) -> Path:
        """Base folder for project cache (inside mymcpserver/cache)."""
        out_dir = Path(__file__).resolve().parents[3] / "cache" / "universal_client"
        out_dir.mkdir(parents=True, exist_ok=True)
        return out_dir

# ---------------------------------------------------------------------
# Start Client/Server Interaction
# ---------------------------------------------------------------------


    async def run(self) -> None:
        """ 20251003 MMH universal_client.run()
            Connect to the MCP server, list available tools, resources,
            templates, and prompts, and demonstrate calling some example tools.
        """
        async with self:
            # Basic server interaction
            await self.ping()

            # List available tools, resources, templates, and prompts
            self.tools_list = await self.list_tools()
            self.tool_names = {tool.name for tool in self.tools_list}
            self._show_tools(self.tools_list)

            resources = await self.list_resources()
            self._show_resources(resources)

            templates = await self.list_resource_templates()
            self._show_templates(templates)

            prompts = await self.list_prompts()
            self._show_prompts(prompts)

            if RUN_PROMPT_EXAMPLES:
                # Execute example prompts
                await self._run_example_prompts(prompts)

            if RUN_TOOL_EXAMPLES:
                # Execute example tools
                await self._run_example_tools(self.tools_list)

# ---------------------------------------------------------------------
#
#           Show registered Tools', Resources', Templates', and Prompts
#
# ---------------------------------------------------------------------

    def _show_tools(self, tools) -> None:
        """Print available tools."""
        logger.info(
            "\nNo Tools available.\n"
            if not tools
            else "\nAvailable Tools:\n",
        )
        for tool in tools:
            logger.info(f"Tool: {tool.name}")
            logger.info(f"Description: {tool.description}")
            if tool.inputSchema:
                logger.info(f"Parameters: {tool.inputSchema}")
            # Access tags and other metadata
            # if hasattr(tool, 'meta') and tool.meta:
            #     fastmcp_meta = tool.meta.get('_fastmcp', {})
            #     logger.info(f"Tags: {fastmcp_meta.get('tags', [])}")

    def _show_resources(self, resources) -> None:
        """Print available resources."""
        logger.info(
            "\nNo Resources available.\n"
            if not resources
            else "\nAvailable Resources:\n",
        )
        for resource in resources:
            logger.info(f"Resource URI: {resource.uri}")
            logger.info(f"Name: {resource.name}")
            logger.info(f"Description: {resource.description}")
            logger.info(f"MIME Type: {resource.mimeType}")
            # Access tags and other metadata
            # if hasattr(resource, '_meta') and resource._meta:
            #     fastmcp_meta = resource._meta.get('_fastmcp', {})
            #     logger.info(f"Tags: {fastmcp_meta.get('tags', [])}")

    def _show_templates(self, templates) -> None:
        """Print available resource templates."""
        logger.info(
            "\nNo Resource Templates available.\n"
            if not templates
            else "\nAvailable Resource Templates:\n",
        )
        for template in templates:
            logger.info(f"Template URI: {template.uriTemplate}")
            logger.info(f"Name: {template.name}")
            logger.info(f"Description: {template.description}")
            # Access tags and other metadata
            # if hasattr(template, '_meta') and template._meta:
            #     fastmcp_meta = template._meta.get('_fastmcp', {})
            #     logger.info(f"Tags: {fastmcp_meta.get('tags', [])}")

    def _show_prompts(self, prompts) -> None:
        """Print available prompts."""
        logger.info(
            "\nNo Prompts available.\n"
            if not prompts
            else "\nAvailable Prompts:\n",
        )
        for prompt in prompts:
            logger.info(f"Prompt: {prompt.name}")
            logger.info(f"Description: {prompt.description}")
            if prompt.arguments:
                arg_names = [arg.name for arg in prompt.arguments]
                logger.info(f"Arguments: {arg_names}")
            # Access tags and other metadata
            # if hasattr(prompt, '_meta') and prompt._meta:
            #     fastmcp_meta = prompt._meta.get('_fastmcp', {})
            #     logger.info(f"Tags: {fastmcp_meta.get('tags', [])}")

# ---------------------------------------------------------------------
#
#           Run Example Tools
#
# ---------------------------------------------------------------------
    async def _run_example_tools(self, tools) -> None:
        """Run example tool invocations where available."""

        # if "add" in tool_names:
        #     await self._run_add_demo()
        # else:
        #     logger.info("\n'add' tool not available on this server.")

        if "youtube_text" in self.tool_names:
            await run_youtube_demo(self)

# ---------------------------------------------------------------------
#
#           Run Example Prompts
#
# ---------------------------------------------------------------------

    async def _run_example_prompts(self, prompts) -> None:
        """Run example tool invocations where available."""
        prompt_names = {prompt.name for prompt in prompts}

        if "youtube_query_normalizer" in prompt_names:
            await self._run_youtube_query_normalizer_prompt()
        else:
            logger.info("\n'summarize_text' prompt not available on this server.")


    async def _run_youtube_query_normalizer_prompt(self) -> None:
        """Demonstrate calling the 'youtube_query_normalizer' prompt."""
        logger.info("\n\nExecuting 'youtube_query_normalizer' prompt with parameters "
              "search_string=Find English language videos on the topic of python list comprehensions")
        result = await self.get_prompt("youtube_query_normalizer",
                            {"search_string": "Find English language videos on the topic of python list comprehensions"})
        logger.info(f"Result of youtube_query_normalizer Prompt: {result}")
        # Access the personalized messages
        logger.info("\nPersonalized Messages:")
        for message in result.messages:
            logger.info(f"Generated message: {message.content}")

if __name__ == "__main__":
    # -----------------------------
    # Logging setup
    # -----------------------------
    from ..utils.logging_config import setup_logging
    setup_logging()

    asyncio.run(UniversalClient("127.0.0.1", 8085).run())
