# mcp_runtime/registry.py
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
import inspect

@dataclass
class ToolSpec:
    name: str
    func: Callable[..., Any]
    description: Optional[str] = None
    input_schema: Optional[Dict[str, Any]] = None
    output_schema: Optional[Dict[str, Any]] = None
    tags: List[str] = field(default_factory=list)

@dataclass
class PromptSpec:
    name: str
    text: str
    meta: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ResourceSpec:
    name: str
    uri: str
    mime: str = "text/plain"
    meta: Dict[str, Any] = field(default_factory=dict)

class MCPRegistry:
    def __init__(self) -> None:
        self.tools: Dict[str, ToolSpec] = {}
        self.prompts: Dict[str, PromptSpec] = {}
        self.resources: Dict[str, ResourceSpec] = {}

    def register_tool(self, spec: ToolSpec) -> None:
        if spec.name in self.tools:
            raise ValueError(f"Duplicate tool name: {spec.name}")
        self.tools[spec.name] = spec

    def register_prompt(self, spec: PromptSpec) -> None:
        if spec.name in self.prompts:
            raise ValueError(f"Duplicate prompt name: {spec.name}")
        self.prompts[spec.name] = spec

    def register_resource(self, spec: ResourceSpec) -> None:
        if spec.name in self.resources:
            raise ValueError(f"Duplicate resource name: {spec.name}")
        self.resources[spec.name] = spec

REGISTRY = MCPRegistry()

# ---------- Decorators ----------

def _derive_input_schema(func: Callable[..., Any]) -> Dict[str, Any]:
    params = inspect.signature(func).parameters
    properties, required = {}, []
    for p in params.values():
        if p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY):
            # super light default; swap in pydantic later if you want strict types
            properties[p.name] = {"type": "string"}
            if p.default is p.empty:
                required.append(p.name)
    return {"type": "object", "properties": properties, "required": required}

def tool(name: Optional[str] = None, description: Optional[str] = None,
         input_schema: Optional[Dict[str, Any]] = None,
         output_schema: Optional[Dict[str, Any]] = None,
         tags: Optional[List[str]] = None):
    """Decorator to auto-register a function as a ToolSpec."""
    def wrap(func: Callable[..., Any]):
        tool_name = name or func.__name__
        REGISTRY.register_tool(ToolSpec(
            name=tool_name,
            func=func,
            description=description or (func.__doc__ or "").strip() or tool_name,
            input_schema=input_schema or _derive_input_schema(func),
            output_schema=output_schema,
            tags=tags or []
        ))
        return func
    return wrap

def prompt(name: str, text: str, **meta):
    """Decorator to register a fixed prompt (no-op on call)."""
    def wrap(dummy):
        REGISTRY.register_prompt(PromptSpec(name=name, text=text, meta=meta))
        return dummy
    return wrap

def resource(name: str, uri: str, mime: str = "text/plain", **meta):
    """Decorator to register a resource descriptor."""
    def wrap(dummy):
        REGISTRY.register_resource(ResourceSpec(name=name, uri=uri, mime=mime, meta=meta))
        return dummy
    return wrap



