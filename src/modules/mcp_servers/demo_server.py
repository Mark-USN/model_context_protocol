# 20251003 MMH Basic mcp server example created as a class.
# Based on https://gofastmcp.com/servers/server
# MCP Decorators https://gofastmcp.com/patterns/decorating-methods#decorating-methods


import argparse
from fastmcp import FastMCP     # , mcp_configurator as mcp

mcp = FastMCP(
    name="DemoServer",
    include_tags={"public", "api"},              # Only expose these tagged components
    exclude_tags={"internal", "deprecated"},     # Hide these tagged components
    on_duplicate_tools="error",                  # Handle duplicate registrations
    on_duplicate_resources="warn",
    on_duplicate_prompts="replace",
    include_fastmcp_meta=False,                  # Disable FastMCP metadata for cleaner integration
)

# 2. Add a tool
@mcp.tool(tags=["public", "api"])
def add(a: int, b: int) -> int:
    """Adds two integer numbers together."""
    return a + b

# 3. Add a static resource
@mcp.resource(uri="resource://config", tags=["api"])
def get_config() -> dict:
    """Provides the application's configuration."""
    return {"version": "1.0", "author": "MyTeam"}

# 4. Add a resource template for dynamic content
@mcp.resource(uri="greetings://{name}", tags=["public"])
def personalized_greeting(name: str) -> str:
    """Generates a personalized greeting for the given name."""
    return f"Hello, {name}! Welcome to the MCP server."


def port_type(value: str) -> int:
    """Custom argparse type that validates a TCP port number."""
    try:
        port = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"Port must be an integer (got {value!r})")
    
    if not (1 <= port <= 65535):
        raise argparse.ArgumentTypeError(f"Port number must be between 1 and 65535 (got {port})")
    
    return port




def main():
    parser = argparse.ArgumentParser(
        description="Create and run an MCP server."
    )
    parser.add_argument("--host", type=str, default="127.0.0.1",
                        help="Host name or IP address (default 127.0.0.1).")
    parser.add_argument("--port", type=port_type, default=8085,
                        help="TCP port to bind/connect (default 8085).")
    
    args = parser.parse_args()

    mcp.run(transport="http", host=args.host, port=args.port)
    print(f"Server started on http://{args.host}:{args.port}")


if __name__ == "__main__":
    main()
    
