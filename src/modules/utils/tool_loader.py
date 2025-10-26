# infra/tool_loader.py
"""
Dynamic discovery and registration of MCP tools.
This loader automatically scans a package for *_tool modules,
imports them safely, and registers them into an MCP server.
"""

import importlib
import pkgutil
import logging
from types import ModuleType
from typing import Any, List, Optional
from pathlib import Path

full_path = Path(__file__)
logger = logging.getLogger(f"{full_path.stem}")


def discover_tools(package: str = ".tools") -> List[ModuleType]:
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
        logger.error("❌ Could not import tools package '%s': %s", package, e)
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
        except Exception as e:
            logger.exception("❌ Error importing module %s: %s", full_name, e)

    return modules


def register_tools(mcp: Any, package: str = "mcp_servers.tools") -> None:
    """
    Register all discovered tool modules with the MCP server.

    Args:
        mcp (Any): The MCP server instance.
        package (str): Package path to scan for tool modules.
    """
    modules = discover_tools(package)
    if not modules:
        logger.warning("⚠️ No tool modules found in package '%s'", package)

    for module in modules:
        register_tools_in_module(mcp, module)


def register_tools_in_module(mcp: Any, module: ModuleType) -> None:
    """
    Register all tools from a specific module.

    Args:
        mcp (Any): The MCP server instance.
        module (ModuleType): The module containing a register(mcp) method.
    """
    if not hasattr(module, "register"):
        logger.warning("⚠️ Module %s has no register(mcp) function", module.__name__)
        return

    try:
        module.register(mcp)
        logger.info("🔧 Registered tools from %s", module.__name__)
    except Exception as e:
        logger.exception("❌ Failed to register tools from %s: %s", module.__name__, e)
