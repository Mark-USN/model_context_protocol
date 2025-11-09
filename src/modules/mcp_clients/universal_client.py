""" 20251003 MMH universal_client.py
    Connect to an mcp server and output its available tools, resources,
    templates, and prompts
    Based on https://gofastmcp.com/clients/client
"""
import asyncio
from pathlib import Path
import json
import logging
from collections.abc import Mapping, Sequence
from fastmcp import Client
from fastmcp.client.client import CallToolResult

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


class universal_client(Client):
    """ 20251003 MMH universal_client class
        A universal MCP client that connects to a FastMCP server,
        lists available tools, resources, templates, and prompts,
        and demonstrates calling some example tools.
    """
    # Variable to hold YouTube URL
    YT_URL: str = ""

    def __init__(self,host:str,port:int):
        """ 20251003 MMH universal_client __init__
            Initialize the universal_client with server host and port.
        """
        self.url = f"http://{host}:{port}/mcp"
        super().__init__(self.url)


    # def _try_parse_snippets_json(self, s: str):
    #     """If s looks like JSON with 'snippets' -> [{'text': ...}], return list of texts; else None."""
    #     try:
    #         data = json.loads(s)
    #         if isinstance(data, dict) and isinstance(data.get("snippets"), list):
    #             out = []
    #             for seg in data["snippets"]:
    #                 if isinstance(seg, dict) and "text" in seg:
    #                     out.append(str(seg["text"]))
    #             return out
    #     except Exception:
    #         pass
    #     return None

    # def extract_text_values_any(self, result: CallToolResult, level: int = 0) -> str:
    #     """
    #     Recursively extract text from:
    #       - FastMCP TextContent(type='text', text=...)
    #       - Objects with .snippets (each having .text)
    #       - Segment-like resultects with .text (and maybe .start/.duration)
    #       - Plain dict/list structures
    #     Returns one formatted string with '\t' indentation.
    #     """
    #     cont = result.content if hasattr(result, "content") else result

    #     lines = []

    #     # --- Case A: FastMCP Content block like TextContent ---
    #     # e.g., TextContent(type='text', text='...')  (attrs, not necessarily dict)
    #     if hasattr(cont, "type") and getattr(cont, "type") == "text" and hasattr(cont, "text"):
    #         txt = getattr(cont, "text")
    #         # If the text is JSON with "snippets", expand them
    #         if isinstance(txt, str):
    #             parsed = self._try_parse_snippets_json(txt)
    #             if parsed:
    #                 for t in parsed:
    #                     lines.append("\t" * level + t)
    #             else:
    #                 lines.append("\t" * level + txt)
    #         else:
    #             lines.append("\t" * level + str(txt))
    #         return "\n".join(lines)

    #     # --- Case B: Root(..., snippets=[...]) or similar container with .snippets ---
    #     if hasattr(cont, "snippets") and isinstance(getattr(cont, "snippets"), Sequence):
    #         for seg in getattr(cont, "snippets"):
    #             # recurse into each segment
    #             lines.append(self.extract_text_values_any(seg, level + 1))
    #         return "\n".join(filter(None, lines))

    #     # --- Case C: Segment-like contect with a .text attribute ---
    #     if hasattr(cont, "text"):
    #         lines.append("\t" * level + str(getattr(cont, "text")))
    #         return "\n".join(lines)

    #     # --- Case D: Mapping (dict-like) fallback ---
    #     if isinstance(cont, Mapping):
    #         # If it *directly* has a 'text' key
    #         if "text" in cont:
    #             lines.append("\t" * level + str(cont["text"]))
    #         # Recurse into all values
    #         for v in cont.values():
    #             sub = self.extract_text_values_any(v, level + 1)
    #             if sub:
    #                 lines.append(sub)
    #         return "\n".join(filter(None, lines))

    #     # --- Case E: Sequence (list/tuple) fallback ---
    #     if isinstance(cont, Sequence) and not isinstance(cont, (str, bytes, bytearray)):
    #         for it in cont:
    #             sub = self.extract_text_values_any(it, level + 1)
    #             if sub:
    #                 lines.append(sub)
    #         return "\n".join(filter(None, lines))

    #     # Anything else: no text to extract
    #     return ""



    async def run(self):
        async with self:
            """ 20251003 MMH universal_client.run()
                Connect to the MCP server, list available tools, resources,
                templates, and prompts, and demonstrate calling some example tools.
            """
            # Basic server interaction
            await self.ping()
            
            # List available operations
            tools = await self.list_tools()
            print("\nNo Tools available.\n" if not tools else "\nAvailable Tools:\n")
            for tool in tools:
                print(f"Tool: {tool.name}")
                print(f"Description: {tool.description}")
                if tool.inputSchema:
                    print(f"Parameters: {tool.inputSchema}")
                # Access tags and other metadata
                if hasattr(tool, 'meta') and tool.meta:
                    fastmcp_meta = tool.meta.get('_fastmcp', {})
                    print(f"Tags: {fastmcp_meta.get('tags', [])}")
                print("")
            resources = await self.list_resources()
            print("\nNo Resources available.\n" if not resources else "\nAvailable Resources:\n")
            for resource in resources:
                print(f"Resource URI: {resource.uri}")
                print(f"Name: {resource.name}")
                print(f"Description: {resource.description}")
                print(f"MIME Type: {resource.mimeType}")
                # Access tags and other metadata
                if hasattr(resource, '_meta') and resource._meta:
                    fastmcp_meta = resource._meta.get('_fastmcp', {})
                    print(f"Tags: {fastmcp_meta.get('tags', [])}")
                print("")


            templates = await self.list_resource_templates()
            print("\nNo Resource Templates available.\n" if not templates else "\nAvailable Resource Templates:\n")
            for template in templates:
                print(f"Template URI: {template.uriTemplate}")
                print(f"Name: {template.name}")
                print(f"Description: {template.description}")
                # Access tags and other metadata
                if hasattr(template, '_meta') and template._meta:
                    fastmcp_meta = template._meta.get('_fastmcp', {})
                    print(f"Tags: {fastmcp_meta.get('tags', [])}")
                print("")


            prompts = await self.list_prompts()
            print("\nNo Prompts available.\n" if not prompts else "\nAvailable Promps:\n")
            for prompt in prompts:
                print(f"Prompt: {prompt.name}")
                print(f"Description: {prompt.description}")
                if prompt.arguments:
                    print(f"Arguments: {[arg.name for arg in prompt.arguments]}")
                # Access tags and other metadata
                if hasattr(prompt, '_meta') and prompt._meta:
                    fastmcp_meta = prompt._meta.get('_fastmcp', {})
                    print(f"Tags: {fastmcp_meta.get('tags', [])}")
                print("")
            
            # Execute operations
            if "add" in [tool.name for tool in tools]:
                print("\n\nExecuting 'add' tool with parameters a=5, b=3")
                result = await self.call_tool("add", {"a": 5, "b": 3})
                print(f"Result of add tool: {result}")
            else:
                print("\n'add' tool not available on this server.")
            
            if "youtube_text" in [tool.name for tool in tools]:
                while not self.YT_URL:
                    url = input("Enter YouTube URL: ").strip()
                    if not self.YT_URL:
                        logger.warning("⚠️ Please paste a valid YouTube URL.")

                # print("\n\nExecuting 'youtube_transcript' tool with parameters https://www.youtube.com/watch?v=DAYJZLERqe8")
                # result = await self.call_tool("youtube_transcript", {"url":"https://www.youtube.com/watch?v=DAYJZLERqe8"})
                # raw_path = Path(__file__).parents[3].resolve() / "youtube_text_output.raw"
                # # Now we can write it out to a file.
                # with open(raw_path, 'w', encoding='utf-8') as raw_file:
                #     raw_file.write(str(result))
                #     # logger.info(f"💾 Saved transcript to {txt_path}")
                # print(f"Result of youtube_transcript tool in {raw_path}")
                # # print(f"Result of youtube_transcript tool:\n{result}")

                print("\n\nExecuting 'youtube_json' tool with parameters https://www.youtube.com/watch?v=DAYJZLERqe8")
                result = await self.call_tool("youtube_json", {"url":self.YT_URL})
                json_path = Path(__file__).parents[3].resolve() / "outputs" / "youtube_text_output.json"
                # Now we can write it out to a file.
                with open(json_path, 'w', encoding='utf-8') as json_file:
                    json_file.write(str(result))
                    # logger.info(f"💾 Saved transcript to {txt_path}")
                print(f"Result of youtube_json tool in {json_path}")
                # print(f"Result of youtube_json tool:\n{result}")

                print("\n\nExecuting 'youtube_text' tool with parameters https://www.youtube.com/watch?v=DAYJZLERqe8")
                result = await self.call_tool("youtube_text", {"url":self.YT_URL})
                txt_path = Path(__file__).parents[3].resolve() / "outputs" / "youtube_text_output.txt"
                # Now we can write it out to a file.
                with open(txt_path, 'w', encoding='utf-8') as txt_file:
                    txt_file.write(str(result))
                    # logger.info(f"💾 Saved transcript to {txt_path}")
                print(f"Result of youtube_text tool in {txt_path}")
                # print(f"Result of youtube_text tool:\n{result}")


if __name__ == "__main__":
    asyncio.run(universal_client("127.0.0.1", 8085).run())
    