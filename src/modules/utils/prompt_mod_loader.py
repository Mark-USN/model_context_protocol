# prompt_mod_loader.py
"""
Dynamic discovery and registration of MCP prompt modules.
This loader automatically scans a package for modules, in the
given directory, imports them safely, and registers them into an MCP server.
"""

import importlib
import pkgutil
import logging
from types import ModuleType
from pathlib import Path
from typing import Any, List, Optional, TypeVar, Dict
from fastmcp import FastMCP

T = TypeVar("T", bound=FastMCP) 

logger = logging.getLogger(f"{Path(__file__).stem}")


def discover_prompts(package: str = ".prompts") -> List[ModuleType]:
    """
    Discover all modules inside the given package.

    Args:
        package (str): Python package path containing the prompt modules.

    Returns:
        List[ModuleType]: A list of successfully imported modules.
    """
    try:
        pkg = importlib.import_module(package)
    except ImportError as e:
        logger.error("❌ Could not import prompts package '%s': %s", package, e)
        return []

    modules: List[ModuleType] = []

    for _, modname, ispkg in pkgutil.iter_modules(pkg.__path__):
        # TODO: MCP does not handle submodules. Need to add code to recurse
        # into subpackages and 'flatten' them into the main package namespace. 
        if ispkg :
            continue

        full_name = f"{package}.{modname}"
        try:
            module = importlib.import_module(full_name)
            modules.append(module)
            logger.info("✅ Loaded prompt module: %s", full_name)
        except Exception as e:
            logger.exception("❌ Error importing module %s: %s", full_name, e)

    return modules


def register_prompts(mcp: T, package: str = "mcp_servers.prompts") -> None:
    """
    Register all discovered prompt modules with the MCP server.

    Args:
        mcp (Any): The MCP server instance.
        package (str): Package path to scan for prompt modules.
    """
    modules = discover_prompts(package)
    if not modules:
        logger.warning("⚠️ No prompt modules found in package '%s'", package)

    for module in modules:
        register_prompts_in_module(mcp, module)


def register_prompts_in_module(mcp: T, module: ModuleType) -> None:
    """
    Register all prompts from a specific module.

    Args:
        mcp (Any): The MCP server instance.
        module (ModuleType): The module containing a register(mcp) method.
    """
    if not hasattr(module, "register"):
        logger.warning("⚠️ Module %s has no register(mcp) function", module.__name__)
        return

    try:
        module.register(mcp)
        logger.info("🔧 Registered prompts from %s", module.__name__)
    except Exception as e:
        logger.exception("❌ Failed to register prompts from %s: %s", module.__name__, e)
