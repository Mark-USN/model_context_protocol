# infra/long_tool_loader.py
"""
Dynamic discovery and registration of MCP tools.
This loader automatically scans a package for modules (.py files),
imports them safely, and registers them into an MCP server.
"""

import sys
import importlib
import importlib.util
import pkgutil
import hashlib
import logging
from types import ModuleType
from typing import List, TypeVar
from pathlib import Path
from fastmcp import FastMCP

T = TypeVar("T", bound=FastMCP)

# -----------------------------
# Logging setup
# -----------------------------
logger = logging.getLogger(__name__)

# _REL_PATH = Path(__file__).parents[1].resolve()
# modules/utils/tool_loader.py
_REL_PATH = Path(__file__).parents[2].resolve()
# parents[2] = .../ (the folder that has 'modules' in it)

def load_module_from_path(
    path: str | Path,
    *,
    sys_path_root: str | Path | None = None,
    module_name: str | None = None,
    add_sys_path: bool = True,
) -> tuple[ModuleType, str]:
    """
    Load a Python module/package from an arbitrary filesystem path.

    Args:
        path: Either a directory (package) or a .py file.
        sys_path_root: If provided, we compute a dotted module name relative to this root.
                       Also used for namespace packages (no __init__.py).
        module_name: Force the dotted module name to this value (optional).
        add_sys_path: If True and sys_path_root is set, prepend it to sys.path if missing.

    Returns:
        (module_object, dotted_module_name)

    Notes:
        - If `path` is a package dir with __init__.py, we can load it directly via file location.
        - If `path` is a .py, we load that file.
        - If `path` points inside a namespace package (no __init__.py), we must import by name,
          which requires `sys_path_root` on sys.path.
    """
    p = Path(path).resolve()
    if not p.exists():
        raise FileNotFoundError(p)

    def _name_from_root(pp: Path, root: Path) -> str:
        """ Derive a dotted module name for `pp` relative to `root`. """
        rel = pp.relative_to(root)
        parts = list(rel.parts)
        if pp.is_file() and pp.suffix == ".py":
            parts[-1] = pp.stem
        return ".".join(parts)

    # If a dotted name was not forced, try to derive one
    derived_name = None
    if module_name is None and sys_path_root:
        root = Path(sys_path_root).resolve()
        if add_sys_path and str(root) not in sys.path:
            sys.path.insert(0, str(root))
        try:
            # For a dir package, name = path relative to root
            # For a file, name = file (sans .py) relative to root
            derived_name = _name_from_root(p, root)
        except ValueError:
            # path is not under sys_path_root; we'll fall back to a unique name
            pass

    # If we still don't have a name, make a unique, stable one
    if module_name is None:
        module_name = derived_name
    if module_name is None:
        h = hashlib.sha1(str(p).encode("utf-8")).hexdigest()[:10]
        if p.is_dir():
            module_name = f"_dynpkg_{p.name}_{h}"
        else:
            module_name = f"_dynmod_{p.stem}_{h}"

    # CASE 1: Directory with __init__.py → load as package by file location
    if p.is_dir():
        init_path = p / "__init__.py"
        if init_path.exists():
            spec = importlib.util.spec_from_file_location(module_name, init_path)
            if spec is None or spec.loader is None:
                raise ImportError(f"Cannot create spec for package at {init_path}")
            mod = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = mod
            spec.loader.exec_module(mod)
            return mod, module_name

        raise ImportError(f"Unsupported path type: {p}")


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

        full_name = f"{package}.{modname}"
        try:
            module = importlib.import_module(full_name)
            modules.append(module)
            logger.info("✅ Loaded tool module: %s", full_name)
        except Exception as e:      # pylint: disable=broad-exception-caught
            logger.exception("❌ Error importing module %s: %s", full_name, e)
            continue

    return modules


def register_long_tools_in_module(mcp: T, module: ModuleType) -> None:
    """
    Register all long tools from a specific module.

    Args:
        mcp (Any): The MCP server instance.
        module (ModuleType): The module containing a register(mcp) method.
    """
    if not hasattr(module, "register_long"):
        logger.warning("⚠️ Module %s has no register_long(mcp) function", module.__name__)
        return

    module.register_long(mcp)
    logger.info("🔧 Registered long tools from %s", module.__name__)

    #=================================================
    #
    # Entry Point called by MCP server
    #
    #=================================================

def register_long_tools(mcp: T, package: Path | str = "../tools") -> None:
    """
    Register all discovered long tool modules with the MCP server.

    Args:
        mcp (Any): The MCP server instance.
        package (str): Package path to scan for tool modules.
    """
    if isinstance(package, Path):
        tools_pkg = package
    else:
        tools_pkg = Path(package)

    if not tools_pkg.exists() or not tools_pkg.is_dir():
        logger.exception("❌ Prompts directory %s does not exist or is not a directory.", tools_pkg)
        return

    # _, module_name = load_module_from_path(path=tools_pkg, sys_path_root=_REL_PATH,
    #                       module_name="tools", add_sys_path=True)
    _, module_name = load_module_from_path(
        path=tools_pkg,
        sys_path_root=_REL_PATH,  # project root
        add_sys_path=True,        # let the loader derive the dotted name
    )

    modules = discover_tools(module_name)
    if not modules:
        logger.warning("⚠️ No long tool modules found in package '%s'", package)

    for module in modules:
        register_long_tools_in_module(mcp, module)




