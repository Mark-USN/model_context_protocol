""" 20251003 MMH universal_client.py
    Connect to an mcp server and output its available tools, resources,
    templates, and prompts
    Based on https://gofastmcp.com/clients/client
"""
import asyncio
from pathlib import Path
import re
# import json
import logging
# from collections.abc import Mapping
from fastmcp import Client
# from fastmcp.client.client import CallToolResult

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

# ---------------------------------------------------------------------
# Control which examples to run
RUN_TOOL_EXAMPLES = True
RUN_PROMPT_EXAMPLES = False
# ---------------------------------------------------------------------

class UniversalClient(Client):
    """ 20251003 MMH universal_client class
        A universal MCP client that connects to a FastMCP server,
        lists available tools, resources, templates, and prompts,
        and demonstrates calling some example tools.
    """
    # Variable to hold YouTube URL
    yt_url: str = ""
    yt_search: str = ""

    def __init__(self, host: str, port: int):
        """ 20251003 MMH universal_client __init__
            Initialize the universal_client with server host and port.
        """
        self.url = f"http://{host}:{port}/mcp"
        super().__init__(self.url)

    # ----------------- Helpers -----------------
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


    async def run(self) -> None:
        """ 20251003 MMH universal_client.run()
            Connect to the MCP server, list available tools, resources,
            templates, and prompts, and demonstrate calling some example tools.
        """
        async with self:
            # Basic server interaction
            await self.ping()

            # List available tools, resources, templates, and prompts
            tools = await self.list_tools()
            self._show_tools(tools)

            resources = await self.list_resources()
            self._show_resources(resources)

            templates = await self.list_resource_templates()
            self._show_templates(templates)

            prompts = await self.list_prompts()
            self._show_prompts(prompts)

            if RUN_TOOL_EXAMPLES:
                # Execute example tools
                await self._run_example_tools(tools)

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
        print(
            "\nNo Tools available.\n"
            if not tools
            else "\nAvailable Tools:\n",
        )
        for tool in tools:
            print(f"Tool: {tool.name}")
            print(f"Description: {tool.description}")
            if tool.inputSchema:
                print(f"Parameters: {tool.inputSchema}")
            # Access tags and other metadata
            # if hasattr(tool, 'meta') and tool.meta:
            #     fastmcp_meta = tool.meta.get('_fastmcp', {})
            #     print(f"Tags: {fastmcp_meta.get('tags', [])}")
            print("")

    def _show_resources(self, resources) -> None:
        """Print available resources."""
        print(
            "\nNo Resources available.\n"
            if not resources
            else "\nAvailable Resources:\n",
        )
        for resource in resources:
            print(f"Resource URI: {resource.uri}")
            print(f"Name: {resource.name}")
            print(f"Description: {resource.description}")
            print(f"MIME Type: {resource.mimeType}")
            # Access tags and other metadata
            # if hasattr(resource, '_meta') and resource._meta:
            #     fastmcp_meta = resource._meta.get('_fastmcp', {})
            #     print(f"Tags: {fastmcp_meta.get('tags', [])}")
            print("")

    def _show_templates(self, templates) -> None:
        """Print available resource templates."""
        print(
            "\nNo Resource Templates available.\n"
            if not templates
            else "\nAvailable Resource Templates:\n",
        )
        for template in templates:
            print(f"Template URI: {template.uriTemplate}")
            print(f"Name: {template.name}")
            print(f"Description: {template.description}")
            # Access tags and other metadata
            # if hasattr(template, '_meta') and template._meta:
            #     fastmcp_meta = template._meta.get('_fastmcp', {})
            #     print(f"Tags: {fastmcp_meta.get('tags', [])}")
            print("")

    def _show_prompts(self, prompts) -> None:
        """Print available prompts."""
        print(
            "\nNo Prompts available.\n"
            if not prompts
            else "\nAvailable Prompts:\n",
        )
        for prompt in prompts:
            print(f"Prompt: {prompt.name}")
            print(f"Description: {prompt.description}")
            if prompt.arguments:
                arg_names = [arg.name for arg in prompt.arguments]
                print(f"Arguments: {arg_names}")
            # Access tags and other metadata
            # if hasattr(prompt, '_meta') and prompt._meta:
            #     fastmcp_meta = prompt._meta.get('_fastmcp', {})
            #     print(f"Tags: {fastmcp_meta.get('tags', [])}")
            print("")

# ---------------------------------------------------------------------
#
#           Run Example Tools
#
# ---------------------------------------------------------------------
    async def _run_example_tools(self, tools) -> None:
        """Run example tool invocations where available."""
        tool_names = {tool.name for tool in tools}

        if "add" in tool_names:
            await self._run_add_demo()
        else:
            print("\n'add' tool not available on this server.")

        if "youtube_text" in tool_names:
            await self._run_youtube_demo()

    async def _run_add_demo(self) -> None:
        """Demonstrate calling the 'add' tool."""
        print("\n\nExecuting 'add' tool with parameters a=5, b=3")
        result = await self.call_tool("add", {"a": 5, "b": 3})
        print(f"Result of add tool: {result}")

    async def _run_youtube_demo(self) -> None:
        """Demonstrate YouTube-related tools."""
        import fastmcp, torch
        import time
        from datetime import timedelta
        print("\nfastmcp:", fastmcp.__version__)
        print("torch:", torch.__version__)
        print("CUDA available:", torch.cuda.is_available())
        print("Device count:", torch.cuda.device_count())
        print("\n")
        
        # Ask user for Search Term once
        # self.yt_search = "Python programming tutorials"

        while not self.yt_search:
            self.yt_search = input("\033[1mEnter Search for YouTube: \033[0m").strip()
            if not self.yt_search:
                logger.warning(
                    "⚠️ Please enter a valid search term.",
                )

        base_out_dir = (
            Path(__file__)
            .parents[3]
            .resolve()
            / "outputs"
        )
        base_out_dir.mkdir(parents=True, exist_ok=True)
        
        # youtube_search
        print(
            "\n\nExecuting 'get_most_relevant_video_url' tool "
            f"with parameters {self.yt_search}",
        )
        yt_url_result = await self.call_tool(
            "get_most_relevant_video_url",
            {"query": self.yt_search},
        )

        # print(f"yt_url_result.data: \n{yt_url_result.data}\n")

        # When working with LLMs result.content might be preferred.
        self.yt_url = yt_url_result.data
        print(f"\nMost relevant YouTube URL: {self.yt_url}")

        # youtube_json
        print(
            "\n\nExecuting 'youtube_json' tool "
            f"with parameters {self.yt_url}",
        )
        start = time.perf_counter()
        json_result = await self.call_tool(
            "youtube_json",
            {"url": self.yt_url},
        )
        elapsed = int(time.perf_counter() - start)
        video_id = self.get_video_id(self.yt_url)
        json_path = base_out_dir / f"{video_id}.json"
        with open(json_path, "w", encoding="utf-8") as json_file:
            json_file.write(str(json_result.data))
        print(f"\nResult of youtube_json tool in {json_path}\n")
        print(f"The transcription of {video_id}.json "
              f"took {str(timedelta(seconds=elapsed))}")

        # youtube_text
        print(
            "\n\nExecuting 'youtube_text' tool "
            f"with parameters {self.yt_url}",
        )
        start = time.perf_counter()
        text_result = await self.call_tool(
            "youtube_text",
            {"url": self.yt_url},
        )
        elapsed = int(time.perf_counter() - start)
        txt_path = base_out_dir / f"{video_id}.txt"
        with open(txt_path, "w", encoding="utf-8") as txt_file:
            txt_file.write(str(text_result.data))
        print(f"\nResult of youtube_text tool in {txt_path}")
        print(f"The transcription of {video_id}.txt "
              f"took {str(timedelta(seconds=elapsed))}")
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
            print("\n'summarize_text' prompt not available on this server.")

        if "ask_about_topic" in prompt_names:
            await self._run_ask_about_topic_demo()
        else:
            print("\n'ask_about_topic' prompt not available on this server.")

        if "generate_code_request" in prompt_names:
            await self._run_generate_code_request_demo()
        else:
            print("\n'generate_code_request' prompt not available on this server.")

        if "roleplay_scenario" in prompt_names:
            await self._run_roleplay_scenario_demo()
        else:
            print("\n'roleplay_scenario' prompt not available on this server.")

    async def _run_summarize_text_demo(self) -> None:
        """Demonstrate calling the 'summarize_text' prompt."""
        print("\n\nExecuting 'summarize_text' prompt with parameters "
              "topic=Dogbert Characteristics, lang=en")
        result = await self.get_prompt("summarize_text",
                            {"text": "Dogbert Characteristics", "lang":"en"})
        print(f"Result of summarize_text Prompt: {result}")
        # Access the personalized messages
        print("\nPersonalized Messages:")
        for message in result.messages:
            print(f"Generated message: {message.content}")


    async def _run_ask_about_topic_demo(self) -> None:
        """Demonstrate calling the 'ask_about_topic' prompt."""
        print("\n\nExecuting 'ask_about_topic' prompt with parameters "
              "topic=Dogbert Characteristics")
        result = await self.get_prompt("ask_about_topic",
                            {"topic": "Dogbert Characteristics"})
        print(f"Result of ask_about_topic Prompt: {result}")
        # Access the personalized messages
        print("\nPersonalized Messages:")
        for message in result.messages:
            print(f"Generated message: {message.content}")

    async def _run_generate_code_request_demo(self) -> None:
        """Demonstrate calling the 'generate_code_request' prompt."""
        print("\n\nExecuting 'generate_code_request' prompt with parameters "
              "language=assembly, task_description= build windows operating system")
        result = await self.get_prompt("generate_code_request",
                            {"language": "assembly",
                             "task_description":"build windows operating system"})
        print(f"Result of generate_code_request Prompt: {result}")
        # Access the personalized messages
        print("\nPersonalized Messages:")
        for message in result.messages:
            print(f"Generated message: {message.content}")


    async def _run_roleplay_scenario_demo(self) -> None:
        """Demonstrate calling the 'roleplay_scenario' prompt."""
        print("\n\nExecuting 'roleplay_scenario' prompt with parameters "
              "character=Roger Rabbit, situation= The real world")
        result = await self.get_prompt("roleplay_scenario",
                            {"character": "Roger Rabbit",
                             "situation":"The real world"})
        print(f"Result of roleplay_scenario Prompt: {result}")
        # Access the personalized messages
        print("\nPersonalized Messages:")
        for message in result.messages:
            print(f"Generated message: {message.content}")


if __name__ == "__main__":
    asyncio.run(UniversalClient("127.0.0.1", 8085).run())
