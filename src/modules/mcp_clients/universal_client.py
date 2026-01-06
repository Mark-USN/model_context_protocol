""" 20251003 MMH universal_client.py
    Connect to an mcp server and output its available tools, resources,
    templates, and prompts
    Based on https://gofastmcp.com/clients/client
"""
# import json
# from ..utils.logging_config import setup_logging
import asyncio
from pathlib import Path
import re
import time
import random
import logging
from typing import Any, List, Dict, Optional, TypeVar
from datetime import timedelta
from .youtube_demo import run_youtube_demo
from ..utils.job_client_mixin import JobClientMixin
from ..utils.tokens import retrieve_sid

from fastmcp import Client

# -----------------------------
# Logging setup
# -----------------------------
# setup_logging()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------
# Control which examples to run
# ---------------------------------------------------------------------
RUN_TOOL_EXAMPLES = True
RUN_PROMPT_EXAMPLES = False

class UniversalClient(JobClientMixin, Client):
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

    def get_video_id(self, url: str) -> str:
        """Extract the YouTube video ID from a URL.
            Args: url: The YouTube video URL.
        """
        url = url.strip()
        if not url:
            raise ValueError("Empty URL")

        # YouTube uses a short-link service for videos that looks like:
        # https://youtu.be/VIDEO_ID or https://youtu.be/dQw4w9WgXcQ
        m = re.search(r"youtu\.be/([A-Za-z0-9_\-]{6,})", url)
        if m:
            return m.group(1)

        m = re.search(r"[?&]v=([A-Za-z0-9_\-]{6,})", url)
        if m:
            return m.group(1)
        raise ValueError("Invalid YouTube URL")

    def base_output_dir(self) -> Path:
        """Base folder for project cache (inside mymcpserver/cache)."""
        out_dir = Path(__file__).resolve().parents[3] / "cache" / "universal_client"
        out_dir.mkdir(parents=True, exist_ok=True)
        return out_dir

    # ---------------------------------------------------------------------
    # Helper Methods for Long-Running Tools
    # ---------------------------------------------------------------------

    def token(self) -> Optional[str]:
        """Return the current session token."""
        return self.session_info.get("token") if self.session_info else None

    def session_id(self) -> Optional[str]:
        """ Return the current session ID.
            This is always derived from the token to avoid mix-ups or attempts to
            use falsified session_ids.
        """
        # return self.session_info.get("session_id") if self.session_info else None
        return retrieve_sid(self.token()) if self.session_info else None


    def expires(self) -> Optional[int]:
        return self.session_info.get("exp") if self.session_info else None

    async def get_token(self, ttl: Optional[int]=None) -> None:
        """ Get a session information which include the token session id, and 
            experation time. Needed for calling certain tools like those related to
            long-running jobs.
        """
        if ttl is not None:
            logger.info(f"\nRequesting session token with TTL={ttl} seconds.")   
            args ={"ttl_s": ttl}
        else:
            logger.info("\nRequesting session token with default TTL.")   
            args ={}
        logger.info("\n\nExecuting 'get_session_token' tool ")
        try:
            token_result = await self.call_tool("get_session_token", args)
            self.session_info = token_result.data
            # If the tool returns a dict, pull the real token string out of it.
            if self.session_info is not None:
                logger.info(f"\nResult of get_session_token tool: {self.session_info}\n"
                      f"session_info[token] = {self.session_info.get('token')}\n")
            else:
                logger.info("Error: get_session_token returned no data.")
        except Exception as e:
            logger.info(f"Error obtaining session token: {e}")
            self.session_info = None

    # Long-running tool helpers are provided by JobClientMixin.

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

            # resources = await self.list_resources()
            # self._show_resources(resources)

            # templates = await self.list_resource_templates()
            # self._show_templates(templates)

            prompts = None
            # prompts = await self.list_prompts()
            # self._show_prompts(prompts)

            if RUN_TOOL_EXAMPLES:
                # Execute example tools
                await self._run_example_tools(self.tools_list)

            if RUN_PROMPT_EXAMPLES:
                # Execute example prompts
                await self._run_example_prompts(prompts)

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

    async def _run_add_demo(self) -> None:
        """Demonstrate calling the 'add' tool."""
        logger.info("\n\nExecuting 'add' tool with parameters a=5, b=3")
        result = await self.call_tool("add", {"a": 5, "b": 3})
        logger.info(f"Result of add tool: {result}")

# ---------------------------------------------------------------------
#
#           Run Example Prompts
#
# ---------------------------------------------------------------------

    async def _run_example_prompts(self, prompts) -> None:
        """Run example tool invocations where available."""
        prompt_names = {prompt.name for prompt in prompts}

        if "summarize_text" in prompt_names:
            await self._run_summarize_text_demo()
        else:
            logger.info("\n'summarize_text' prompt not available on this server.")

        if "ask_about_topic" in prompt_names:
            await self._run_ask_about_topic_demo()
        else:
            logger.info("\n'ask_about_topic' prompt not available on this server.")

        if "generate_code_request" in prompt_names:
            await self._run_generate_code_request_demo()
        else:
            logger.info("\n'generate_code_request' prompt not available on this server.")

        if "roleplay_scenario" in prompt_names:
            await self._run_roleplay_scenario_demo()
        else:
            logger.info("\n'roleplay_scenario' prompt not available on this server.")

    async def _run_summarize_text_demo(self) -> None:
        """Demonstrate calling the 'summarize_text' prompt."""
        logger.info("\n\nExecuting 'summarize_text' prompt with parameters "
              "topic=Dogbert Characteristics, lang=en")
        result = await self.get_prompt("summarize_text",
                            {"text": "Dogbert Characteristics", "lang":"en"})
        logger.info(f"Result of summarize_text Prompt: {result}")
        # Access the personalized messages
        logger.info("\nPersonalized Messages:")
        for message in result.messages:
            logger.info(f"Generated message: {message.content}")


    async def _run_ask_about_topic_demo(self) -> None:
        """Demonstrate calling the 'ask_about_topic' prompt."""
        logger.info("\n\nExecuting 'ask_about_topic' prompt with parameters "
              "topic=Dogbert Characteristics")
        result = await self.get_prompt("ask_about_topic",
                            {"topic": "Dogbert Characteristics"})
        logger.info(f"Result of ask_about_topic Prompt: {result}")
        # Access the personalized messages
        logger.info("\nPersonalized Messages:")
        for message in result.messages:
            logger.info(f"Generated message: {message.content}")

    async def _run_generate_code_request_demo(self) -> None:
        """Demonstrate calling the 'generate_code_request' prompt."""
        logger.info("\n\nExecuting 'generate_code_request' prompt with parameters "
              "language=assembly, task_description= build windows operating system")
        result = await self.get_prompt("generate_code_request",
                            {"language": "assembly",
                             "task_description":"build windows operating system"})
        logger.info(f"Result of generate_code_request Prompt: {result}")
        # Access the personalized messages
        logger.info("\nPersonalized Messages:")
        for message in result.messages:
            logger.info(f"Generated message: {message.content}")


    async def _run_roleplay_scenario_demo(self) -> None:
        """Demonstrate calling the 'roleplay_scenario' prompt."""
        logger.info("\n\nExecuting 'roleplay_scenario' prompt with parameters "
              "character=Roger Rabbit, situation= The real world")
        result = await self.get_prompt("roleplay_scenario",
                            {"character": "Roger Rabbit",
                             "situation":"The real world"})
        logger.info(f"Result of roleplay_scenario Prompt: {result}")
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
