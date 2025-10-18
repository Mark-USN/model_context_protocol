# 20251012 MMH: FastMCP v2 server with auto-registration of tools/prompts/resources.

import argparse
from pathlib import Path

from fastmcp import FastMCP

# Local registry/loader (you already have these files next to this module)
from .registry import REGISTRY
from .loader import (
    import_package_modules,
    load_prompts_from_dir,
    load_resources_from_dir,
)

# -------------------------------------------------------------------
# FastMCP server instance (keeps your existing options/tags/policies)
# -------------------------------------------------------------------
mcp = FastMCP(
    name="DemoServer",
    include_tags={"public", "api"},              # Only expose these tagged components
    exclude_tags={"internal", "deprecated"},     # Hide these tagged components
    on_duplicate_tools="error",                  # Handle duplicate registrations
    on_duplicate_resources="warn",
    on_duplicate_prompts="replace",
    include_fastmcp_meta=False,                  # Disable FastMCP metadata for cleaner integration
)

# Where to look for auto-discovered assets (relative to this file)
_THIS_DIR = Path(__file__).resolve().parent
_PROMPTS_DIR = _THIS_DIR / "prompts"
_RESOURCES_DIR = _THIS_DIR / "resources"
_TOOLS_PKG = __package__ + ".tools"  # "mcp_servers.tools"

# -------------------------------------------------------------------
# One-time attach: import tool modules, load prompts/resources, register
# -------------------------------------------------------------------
def attach_everything():
    # 1) Import all modules in mcp_servers.tools (decorators auto-register)
    import_package_modules(_TOOLS_PKG)

    # 2) Load file-based prompts and resources (optional, if dirs exist)
    load_prompts_from_dir(_PROMPTS_DIR)
    load_resources_from_dir(_RESOURCES_DIR)

    # 3) Attach tools discovered in the REGISTRY
    for spec in REGISTRY.tools.values():
        # Register each tool with FastMCP v2. The decorator returned by
        # mcp.tool(...) is immediately applied to the function.
        mcp.tool(
            name=spec.name,
            description=spec.description or spec.name,
            inputSchema=spec.input_schema,
            outputSchema=spec.output_schema,
            tags=spec.tags,
        )(spec.func)

    # 4) Helper tools to expose prompts/resources to clients
    @mcp.tool(name="list_prompts", description="List all registered prompts.")
    def _list_prompts():
        return {
            "count": len(REGISTRY.prompts),
            "items": [{"name": p.name, "meta": p.meta} for p in REGISTRY.prompts.values()],
        }

    @mcp.tool(
        name="get_prompt",
        description="Return prompt text and metadata by name.",
        inputSchema={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
    )
    def _get_prompt(name: str):
        p = REGISTRY.prompts.get(name)
        if not p:
            raise ValueError(f"Unknown prompt: {name}")
        return {"name": p.name, "text": p.text, "meta": p.meta}

    @mcp.tool(name="list_resources", description="List all registered resources.")
    def _list_resources():
        return {
            "count": len(REGISTRY.resources),
            "items": [
                {"name": r.name, "uri": r.uri, "mime": r.mime, "meta": r.meta}
                for r in REGISTRY.resources.values()
            ],
        }

    @mcp.tool(
        name="get_resource",
        description="Return resource descriptor by name.",
        inputSchema={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
    )
    def _get_resource(name: str):
        r = REGISTRY.resources.get(name)
        if not r:
            raise ValueError(f"Unknown resource: {name}")
        return {"name": r.name, "uri": r.uri, "mime": r.mime, "meta": r.meta}


# -------------------------------------------------------------------
# CLI (same interface you had; just calls attach_everything() first)
# -------------------------------------------------------------------
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
    parser = argparse.ArgumentParser(description="Create and run an MCP server.")
    parser.add_argument("--host", type=str, default="127.0.0.1",
                        help="Host name or IP address (default 127.0.0.1).")
    parser.add_argument("--port", type=port_type, default=8085,
                        help="TCP port to bind/connect (default 8085).")
    args = parser.parse_args()

    # Build registry & attach before running
    attach_everything()

    # Run FastMCP v2 over HTTP (keeps your transport/args)
    mcp.run(transport="http", host=args.host, port=args.port)
    print(f"Server started on http://{args.host}:{args.port}")


if __name__ == "__main__":
    main()