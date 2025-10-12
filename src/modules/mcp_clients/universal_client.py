# universal_client.py
# 20251003 MMH Connect to an mcp server and output its available tools, resources,
# templats, and prompts
# Based on https://gofastmcp.com/clients/client

import asyncio
from fastmcp import Client

class universal_client(Client):

    def __init__(self,host:str,port:int):
        self.url = f"http://{host}:{port}/mcp"
        super().__init__(self.url)

    async def run(self):
        async with self:
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
            
            # Execute operations
            result = await self.call_tool("add", {"a": 5, "b": 3})
            print(f"Result of add tool: {result}")


if __name__ == "__main__":
    asyncio.run(universal_client("127.0.0.1", 8085).run())
    