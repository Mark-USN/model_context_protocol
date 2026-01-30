# resource_loader.py
"""
Dynamic discovery and registration of MCP resource.
This loader automatically scans a package for *_tool modules,
imports them safely, and registers them into an MCP server.
"""

import importlib
import pkgutil
import json
# import logging
from types import ModuleType
from typing import Any, List, TypeVar
from pathlib import Path
import frontmatter
from fastmcp import FastMCP
from modules.utils.log_utils import get_logger # , log_tree

T = TypeVar("T", bound=FastMCP)

# -----------------------------
# Logging setup
# -----------------------------
logger = get_logger(__name__)

full_path = Path(__file__)

default_resource_path = full_path.parent.parent / "resources"

resources_dict : dict[str, dict[str, Any]] ={}

def discover_resources(resources_dir: Path) -> None: # = default_resource_path) -> None:
    """
    Load all .json files found in the resources directory into the global resources_dic.

    Args:
        resources_dir (Path): Python path to resource files.

    Returns:
        None
    Side Effects:
        Populates the global resources_dic with discovered resources.
    """

    if not resources_dir.exists():
        logger.error("❌ Resources directory %s does not exist.",resources_dir)
        return
    files = resources_dir.rglob("*.json")

    if len (list(files)) == 0:
        logger.warning("⚠️ No resource files found in directory '%s'", resources_dir)
        return

    for r in files:
        text = r.read_text(encoding="utf-8")
        post = frontmatter.load(text)
        name = (post.metadata or {}).pop("name", r.stem)
        resources_dict[name] = {"name": name, "text": post.content.strip(),
                                "meta": dict(post.metadata or {})}

def discover_resource(package: Path = default_resource_path) -> List[ModuleType]:
    """
    Discover all *_tool modules inside the given package.

    Args:
        package (str): Python package path containing the tool modules.

    Returns:
        List[ModuleType]: A list of successfully imported modules.
    """
    try:
        pkg = importlib.import_module(package)
    except ImportError as e:
        logger.error("❌ Could not import resource package '%s': %s", package, e)
        return []

    modules: List[ModuleType] = []

    for _, modname, ispkg in pkgutil.iter_modules(pkg.__path__):
        # TODO: MCP does not handle submodules. Need to add code to recurse
        # into subpackages and 'flatten' them into the main package namespace.
        if ispkg :
            continue
        # if ispkg or not modname.endswith("_tool"):
        #     continue

        full_name = f"{package}.{modname}"
        try:
            module = importlib.import_module(full_name)
            modules.append(module)
            logger.info("✅ Loaded tool module: %s", full_name)
        except Exception as e:      # pylint: disable=broad-exception-caught
            logger.exception("❌ Error importing module %s: %s", full_name, e)
            continue

    return modules


def register_resource(mcp: T, package: str = "mcp_servers.resource") -> None:
    """
    Register all discovered tool modules with the MCP server.

    Args:
        mcp (Any): The MCP server instance.
        package (str): Package path to scan for tool modules.
    """
    modules = discover_resource(package)
    if not modules:
        logger.warning("⚠️ No tool modules found in package '%s'", package)

    for module in modules:
        register_resource_in_module(mcp, module)


def register_resource_in_module(mcp: Any, module: ModuleType) -> None:
    """
    Register all resource from a specific module.

    Args:
        mcp (Any): The MCP server instance.
        module (ModuleType): The module containing a register(mcp) method.
    """
    if not hasattr(module, "register"):
        logger.warning("⚠️ Module %s has no register(mcp) function", module.__name__)
        return

    module.register(mcp)
    logger.info("🔧 Registered resource from %s", module.__name__)


def load_resources_from_dir(dir_path: Path) -> None:
    """
        Load resource metadata from JSON files in the specified directory.
        Args:
            dir_path (Path): Path to the directory containing resource JSON files.
    """
    if not dir_path.exists():
        return
    for p in dir_path.rglob("*.json"):
        props: dict[str, Any] = {}
        meta = json.loads(p.read_text(encoding="utf-8"))
        name = meta["name"]
        props = {
            "name": name,
            "uri": meta["uri"],
            "mime": meta.get("mime", "application/octet-stream"),
            "meta": {k: v for k, v in meta.items() if k not in {"name", "uri", "mime"}},
        }
        resources_dict[name] = props
