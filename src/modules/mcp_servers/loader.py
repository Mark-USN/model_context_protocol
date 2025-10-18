# mcp_runtime/loader.py
import importlib
import pkgutil
from pathlib import Path
from typing import Optional
from .registry import REGISTRY, PromptSpec, ResourceSpec

def import_package_modules(package_name: str) -> None:
    pkg = importlib.import_module(package_name)
    pkg_path = Path(pkg.__file__).parent
    for mod in pkgutil.iter_modules([str(pkg_path)]):
        importlib.import_module(f"{package_name}.{mod.name}")

def load_prompts_from_dir(dir_path: Optional[Path]) -> None:
    if not dir_path or not dir_path.exists():
        return
    # Supports simple Markdown; YAML front-matter if python-frontmatter is installed
    try:
        import frontmatter  # pip install python-frontmatter
    except ImportError:
        frontmatter = None

    for p in dir_path.rglob("*.md"):
        text = p.read_text(encoding="utf-8")
        meta, body = {}, text
        if frontmatter:
            post = frontmatter.loads(text)
            meta = dict(post.metadata or {})
            body = post.content
        name = meta.pop("name", p.stem)
        REGISTRY.register_prompt(PromptSpec(name=name, text=body.strip(), meta=meta))

def load_resources_from_dir(dir_path: Optional[Path]) -> None:
    if not dir_path or not dir_path.exists():
        return
    import json
    for p in dir_path.rglob("*.resource.json"):
        meta = json.loads(p.read_text(encoding="utf-8"))
        REGISTRY.register_resource(ResourceSpec(
            name=meta["name"],
            uri=meta["uri"],
            mime=meta.get("mime", "application/octet-stream"),
            meta={k: v for k, v in meta.items() if k not in {"name","uri","mime"}}
        ))

