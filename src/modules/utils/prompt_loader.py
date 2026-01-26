# prompt_loader.py
"""
Dynamic discovery and registration of MCP prompt modules.
This loader automatically scans a package for modules, in the
given directory, imports them safely, and registers them into an MCP server.
"""

import sys
import importlib
import importlib.util
import pkgutil
import logging
import hashlib
from types import ModuleType
from pathlib import Path
from typing import List, TypeVar
from fastmcp import FastMCP
from modules.utils.log_utils import get_logger


T = TypeVar("T", bound=FastMCP)

# -----------------------------
# Logging setup
# -----------------------------
logger = get_logger(__name__)


_REL_PATH = Path(__file__).parents[1].resolve()


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
        module = importlib.import_module(full_name)
        modules.append(module)
        logger.info("✅ Loaded prompt module: %s", full_name)

    return modules


def register_prompts(mcp: T, prompts_dir: Path | str = "..prompts") -> None:
    """
    Register all discovered prompt modules with the MCP server.

    Args:
        mcp (Any): The MCP server instance.
        package (str): Package path to scan for prompt modules.
    """

    if isinstance(prompts_dir, Path):
        prompts_pkg = prompts_dir
    else:
        prompts_pkg = Path(prompts_dir)

    if not prompts_pkg.exists() or not prompts_pkg.is_dir():
        logger.exception("❌ Prompts directory %s does not exist or is not "
                         "a directory.", prompts_pkg)
        return

    _, module_name = load_module_from_path(
            path=prompts_pkg,
            sys_path_root=_REL_PATH,
            module_name="prompts",
            add_sys_path=True
            )

    modules = discover_prompts(module_name)
    if not modules:
        logger.warning("⚠️ No prompt modules found in package '%s'", prompts_dir)

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

    module.register(mcp)
    logger.info("🔧 Registered prompts from %s", module.__name__)
