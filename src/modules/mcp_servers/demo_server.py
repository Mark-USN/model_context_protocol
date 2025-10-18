# demo_server.py — FastMCP server that discovers tools/prompts/resources without a registry.

import argparse
import importlib
import json
import pkgutil
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Tuple

from fastmcp import FastMCP

# -----------------------------
# Server instance & conventions
# -----------------------------
mcp = FastMCP(
    name="DemoServer",
    include_tags={"public", "api"},
    exclude_tags={"internal", "deprecated"},
    on_duplicate_tools="error",
    on_duplicate_resources="warn",
    on_duplicate_prompts="replace",
    include_fastmcp_meta=False,
)

_THIS_DIR = Path(__file__).resolve().parent
_TOOLS_PKG = (__package__ + ".tools") if __package__ else "tools"
_PROMPTS_DIR = _THIS_DIR / "prompts"
_RESOURCES_DIR = _THIS_DIR / "resources"

# In-memory stores (replace registry)
PROMPTS: Dict[str, Dict[str, Any]] = {}
RESOURCES: Dict[str, Dict[str, Any]] = {}

# -----------------------------
# Utility: derive input schema
# -----------------------------
def derive_input_schema(func: Callable[..., Any]) -> Dict[str, Any]:
    """Very light JSON schema from a function signature (strings by default)."""
    import inspect
    params = inspect.signature(func).parameters
    properties, required = {}, []
    for p in params.values():
        if p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY):
            properties[p.name] = {"type": "string"}
            if p.default is p.empty:
                required.append(p.name)
    return {"type": "object", "properties": properties, "required": required}

# -----------------------------------------
# Discovery: iterate functions exported as TOOLS
# -----------------------------------------
def iter_tool_functions(package_name: str) -> Iterable[Tuple[Callable[..., Any], Dict[str, Any]]]:
    """
    Import every module in <package_name> and yield (func, meta) for each function
    explicitly listed in a module-level TOOLS = [func1, func2, ...].
    Optional TOOL_META = {func_name: {...}} provides per-tool metadata.
    """
    pkg = importlib.import_module(package_name)
    root = Path(pkg.__file__).parent

    for mod_info in pkgutil.iter_modules([str(root)]):
        mod = importlib.import_module(f"{package_name}.{mod_info.name}")
        funcs = getattr(mod, "TOOLS", None)
        if not funcs:
            continue
        meta_map: Dict[str, Dict[str, Any]] = getattr(mod, "TOOL_META", {})
        for f in funcs:
            meta = meta_map.get(f.__name__, {})
            yield f, meta

# -----------------------------------------
# Load prompts/resources directly to memory
# -----------------------------------------
def load_prompts_from_dir(dir_path: Path) -> None:
    if not dir_path.exists():
        return
    try:
        import frontmatter  # optional
    except ImportError:
        frontmatter = None

    for p in dir_path.rglob("*.md"):
        text = p.read_text(encoding="utf-8")
        if frontmatter:
            post = frontmatter.loads(text)
            name = (post.metadata or {}).pop("name", p.stem)
            PROMPTS[name] = {"name": name, "text": post.content.strip(), "meta": dict(post.metadata or {})}
        else:
            PROMPTS[p.stem] = {"name": p.stem, "text": text.strip(), "meta": {}}

def load_resources_from_dir(dir_path: Path) -> None:
    if not dir_path.exists():
        return
    for p in dir_path.rglob("*.resource.json"):
        meta = json.loads(p.read_text(encoding="utf-8"))
        name = meta["name"]
        RESOURCES[name] = {
            "name": name,
            "uri": meta["uri"],
            "mime": meta.get("mime", "application/octet-stream"),
            "meta": {k: v for k, v in meta.items() if k not in {"name", "uri", "mime"}},
        }

# -----------------------------------------
# Attach everything to FastMCP at startup
# -----------------------------------------
def attach_everything():
    # 1) Attach tools
    for func, meta in iter_tool_functions(_TOOLS_PKG):
        mcp.tool(
            name=meta.get("name", func.__name__),
            description=meta.get("description", (func.__doc__ or "").strip() or func.__name__),
            inputSchema=meta.get("inputSchema", derive_input_schema(func)),
            outputSchema=meta.get("outputSchema"),
            tags=meta.get("tags", []),
        )(func)

    # 2) Load prompts/resources & expose helper tools
    load_prompts_from_dir(_PROMPTS_DIR)
    load_resources_from_dir(_RESOURCES_DIR)

    @mcp.tool(name="list_prompts", description="List all discovered prompts.")
    def _list_prompts():
        return {"count": len(PROMPTS), "items": [{"name": p["name"], "meta": p["meta"]} for p in PROMPTS.values()]}

    @mcp.tool(
        name="get_prompt",
        description="Return prompt text and metadata by name.",
        inputSchema={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
    )
    def _get_prompt(name: str):
        p = PROMPTS.get(name)
        if not p:
            raise ValueError(f"Unknown prompt: {name}")
        return p

    @mcp.tool(name="list_resources", description="List all discovered resources.")
    def _list_resources():
        return {
            "count": len(RESOURCES),
            "items": [{"name": r["name"], "uri": r["uri"], "mime": r["mime"], "meta": r["meta"]} for r in RESOURCES.values()],
        }

    @mcp.tool(
        name="get_resource",
        description="Return resource descriptor by name.",
        inputSchema={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
    )
    def _get_resource(name: str):
        r = RESOURCES.get(name)
        if not r:
            raise ValueError(f"Unknown resource: {name}")
        return r

# -----------------------------
# CLI (kept as before)
# -----------------------------
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
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host name or IP address (default 127.0.0.1).")
    parser.add_argument("--port", type=port_type, default=8085, help="TCP port to bind/connect (default 8085).")
    args = parser.parse_args()

    attach_everything()
    mcp.run(transport="http", host=args.host, port=args.port)
    print(f"Server started on http://{args.host}:{args.port}")

if __name__ == "__main__":
    main()
