""" 20251003 MMH universal_client.py
    Connect to an mcp server and output its available tools, resources,
    templates, and prompts
    Based on https://gofastmcp.com/clients/client
"""
import asyncio
from pathlib import Path
import re
import time
import json
import random
import logging
# from ..utils.logging_config import setup_logging
from typing import Any, List, Dict, Optional, TypeVar
from datetime import timedelta

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

class UniversalClient(Client):
    """ 20251003 MMH universal_client class
        A universal MCP client that connects to a FastMCP server,
        lists available tools, resources, templates, and prompts,
        and demonstrates calling some example tools.
    """
    # Variable to hold YouTube URL
    yt_urls: str | Optional[List::str] = None
    yt_search: str = ""
    token: Optional[Dict] = None
    MAX_SEARCH_RESULTS: int = 5
    _next_allowed_ts: float = 0.0  # simple global limiter


    def __init__(self, host: str, port: int):
        """ 20251003 MMH universal_client __init__
            Initialize the universal_client with server host and port.
        """
        self.url = f"http://{host}:{port}/mcp"
        super().__init__(self.url)

# ---------------------------------------------------------------------
# Helper Methods
# ---------------------------------------------------------------------
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

    async def call_long_tool_and_get_result(self, tool_name: str, args: dict, *, poll_s: float = 2.0):
        """Call a long-running tool and poll for its result.
        Args:
            tool_name: The name of the tool to call.
            args: The arguments to pass to the tool
            poll_s: Polling interval in seconds.
        Returns:
            The result of the long-running tool.
        """
        # Launch job (long_job_server behavior)
        launch = await self.call_tool(tool_name, args)
        launch_data = launch.data

        if "job_id" not in launch_data:
            # If you accidentally hit demo_server, this might already be the real result.
            return launch_data

        job_id = launch_data["job_id"]

        while True:
            status = await self.call_tool("get_job_status", {"job_id": job_id, "token": args["token"]})
            s = status.data
            state = s.get("state")

            if state in ("done", "failed", "timed_out", "canceled"):
                break

            await asyncio.sleep(poll_s)

        result = await self.call_tool("get_job_result", {"job_id": job_id, "token": args["token"]})
        return result.data

    async def _throttle(self, *, min_interval_s: float, jitter_s: float) -> None:
        """Ensure at least min_interval_s between tool calls (plus jitter) to help
            keep YouTube from blocking our requests.
            Args:
                min_interval_s: Minimum interval between calls in seconds.
                jitter_s: Maximum jitter to add to wait time in seconds.   
            Returns:
                None
        """
        now = time.monotonic()
        wait = max(0.0, self._next_allowed_ts - now)
        # add jitter every time (helps avoid "machine-like" spacing)
        wait += random.uniform(0.0, jitter_s)
        if wait > 0:
            await asyncio.sleep(wait)
        self._next_allowed_ts = time.monotonic() + min_interval_s

    async def call_tools_polite(
        self,
        tool_name: str,
        args: dict,
        *,
        min_interval_s: float = 2.5,
        jitter_s: float = 1.5,
        max_retries: int = 4,
        base_backoff_s: float = 15.0,
    ):
        """ Call a tool with throttling + exponential backoff on transient blocks.
            Trying to be polite to avoid being blocked by rate limits at YouTube.
            Args:
                tool_name: The name of the tool to call.
                args: The arguments to pass to the tool
                min_interval_s: Minimum interval between calls in seconds.
                jitter_s: Maximum jitter to add to wait time in seconds.
                max_retries: Maximum number of retries on transient errors.
                base_backoff_s: Base backoff time in seconds for retries.
            Returns:
                The result of the tool call.
        """
        attempt = 0
             
        while True:
            await self._throttle(min_interval_s=min_interval_s, jitter_s=jitter_s)
            try:
                if args.get("token") is None:
                    return await self.call_tool(tool_name, args)
                else:
                    return await self.call_long_tool_and_get_result(tool_name, args)
            except Exception as e:
                msg = str(e).lower()
                # Heuristic: adjust based on your actual exception strings
                transient = any(k in msg for k in ["429", "too many requests", "blocked", "requestblocked", "rate"])
                if (not transient) or (attempt >= max_retries):
                    raise
                sleep_s = base_backoff_s * (2 ** attempt) + random.uniform(0, 5)
                logger.warning("Transient error calling %s (attempt %s/%s): %s; sleeping %.1fs",
                               tool_name, attempt + 1, max_retries + 1, e, sleep_s)
                await asyncio.sleep(sleep_s)
                attempt += 1

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
        # Show fastmcp and torch versions, CUDA availability, etc.
        import fastmcp, torch
        import time
        from datetime import timedelta
        print("\n\n⚠The below information is only relevant if the client is run on the same machine as the server.")
        print("\nfastmcp:", fastmcp.__version__)
        print("torch:", torch.__version__)
        print("CUDA available:", torch.cuda.is_available())
        print("Device count:", torch.cuda.device_count())
        print("\n")
        
        # Ask user for Search Term once
        # self.yt_search = "Python programming using async tutorials"
        self.yt_search = "chromaticity and color preception"

        while not self.yt_search:
            self.yt_search = input("\033[1mEnter Search for YouTube: \033[0m").strip()
            if not self.yt_search:
                logger.warning(
                    "⚠️ Please enter a valid search term.",
                )
        
        # youtube_search
        print(
            "\n\nExecuting 'get_most_relevant_video_url' tool "
            f"with parameters {self.yt_search}, {self.MAX_SEARCH_RESULTS}.",
        )
        yt_url_result = None
        yt_url_result = await self.call_tool(
            "get_most_relevant_video_url",
            {"query": self.yt_search,
             "maxResults": self.MAX_SEARCH_RESULTS},
        )
        # When working with LLMs result.content might be preferred.
        self.yt_urls = yt_url_result.data
        if isinstance(self.yt_urls, str):
            print(f"\nMost relevant YouTube URL: {self.yt_urls}")
        elif isinstance(self.yt_urls, List):
            print(f"\nMost relevant YouTube URLs:\n")
            for url in self.yt_urls:
                print(f"- {url}")

        await self.get_all_transcripts()
        await self.get_all_audio_transcripts()

    # ---------------------------------------------------------------------
    #           YouTube Transcript Methods (Subtitles/Captions)
    # ---------------------------------------------------------------------

    async def get_a_transcript(self, url: str) -> None:
        """ Get transcripts for a given YouTube URL using various tools.
                Args:
                    yt_url: The YouTube video URL.
        """
        # youtube_json
        print(
            "\n\nExecuting 'youtube_json' tool "
            f"with parameters {url}",
        )
        start = time.perf_counter()
        json_result = await self.call_tools_polite(
            tool_name = "youtube_json",
            args = {"url": url},
        )
        elapsed = int(time.perf_counter() - start)
        video_id = self.get_video_id(url)
        json_path = self.base_output_dir() / f"{video_id}.json"
        with open(json_path, "w", encoding="utf-8") as json_file:
            json_file.write(str(json_result.data))
        print(f"\nResult of youtube_json tool in {json_path}\n")
        print(f"The transcription of {video_id}.json "
                f"took {str(timedelta(seconds=elapsed))}")

        # youtube_text
        print(
            "\n\nExecuting 'youtube_text' tool "
            f"with parameters {url}",
        )
        start = time.perf_counter()
        text_result = await self.call_tools_polite(
            tool_name = "youtube_text",
            args = {'url': url}
        )
        elapsed = int(time.perf_counter() - start)
        txt_path = self.base_output_dir() / f"{video_id}.txt"
        with open(txt_path, "w", encoding="utf-8") as txt_file:
            txt_file.write(str(text_result.data))
        print(f"\nResult of youtube_text tool in {txt_path}")
        print(f"The transcription of {video_id}.txt "
                f"took {str(timedelta(seconds=elapsed))}")

    async def get_all_transcripts(self) -> None:
        """ Get transcripts for a given YouTube URL.
                Args:
                    yt_url: The YouTube video URL.
        """
        # youtube_json
        if isinstance(self.yt_urls, List): 
            for url in self.yt_urls:
                await self.get_a_transcript(url)
        else:
            await self.get_a_transcript(self.yt_urls)

    # ---------------------------------------------------------------------
    #           YouTube Audio Transcript Methods
    # ---------------------------------------------------------------------

    async def get_token(self) -> None:
        """ Get token for YouTube URL using token tool.
        """
        print(
            "\n\nExecuting 'get_session_token' tool ",
        )
        try:
            token_result = await self.call_tool(
                "get_session_token",
                {},
            )
            self.token = token_result.data
            print(f"\nResult of get_session_token tool: {self.token}\n")
        except Exception as e:
            print(f"Error obtaining session token: {e}")
            self.token = None


    async def get_an_audio_transcript(self, url:str)->None:
        print(
            "\n\nExecuting 'youtube_audio_json' tool "
            f"to transcribe {url}",
        )
        start = time.perf_counter()
        if self.token is None:
            json_result = await self.call_tools_polite(
                "youtube_audio_json",
                {"url": url})
        else:
            json_result = await self.call_tools_polite(
                "youtube_audio_json",
                {"url": url, "token": self.token})
        elapsed = int(time.perf_counter() - start)
        # Write JSON output to file.
        video_id = self.get_video_id(url)
        json_path = self.base_output_dir() / f"{video_id}_audio.json"
        with open(json_path, "w", encoding="utf-8") as json_file:
            json_file.write(str(json_result.data))
        print(f"\nResult of youtube_json tool in {json_path}\n")
        print(f"The transcription of {video_id}_audio.json "
                f"took {str(timedelta(seconds=elapsed))}")

        # youtube_audio_text
        print(
            "\n\nExecuting 'youtube_audio_text' tool "
            f"to transcribe {url}",
        )
        start = time.perf_counter()
        if self.token is None:
            text_result = await self.call_tools_polite(
                "youtube_audio_text",
                {"url": url})
        else:
            text_result = await self.call_tools_polite(
                "youtube_audio_text",
                {"url": url, "token": self.token})          
        elapsed = int(time.perf_counter() - start)
        # Write TXT output to file.
        txt_path = self.base_output_dir() / f"{video_id}_audio.txt"
        with open(txt_path, "w", encoding="utf-8") as txt_file:
            txt_file.write(str(text_result.data))
        print(f"\nResult of youtube_text tool in {txt_path}")
        print(f"The transcription of {video_id}_audio.txt "
                f"took {str(timedelta(seconds=elapsed))}")

    async def get_all_audio_transcripts(self) -> None:
        """ Get transcripts for a given YouTube URL using various tools.
                Args:
                    yt_url: The YouTube video URL.
        """
        #           Run Audio Tools
        await self.get_token()

        # youtube_audio_json
        if isinstance(self.yt_urls, List): 
            for url in self.yt_urls:
                await self.get_an_audio_transcript(url)
        else:
            await self.get_an_audio_transcript(self.yt_urls)

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
