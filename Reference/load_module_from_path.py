from __future__ import annotations
from pathlib import Path
import importlib
import importlib.util
import sys
import types
import hashlib

def load_module_from_path(
    path: str | Path,
    *,
    sys_path_root: str | Path | None = None,
    module_name: str | None = None,
    add_sys_path: bool = True,
) -> tuple[types.ModuleType, str]:
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
        init_py = p / "__init__.py"
        if init_py.exists():
            spec = importlib.util.spec_from_file_location(module_name, init_py)
            if spec is None or spec.loader is None:
                raise ImportError(f"Cannot create spec for package at {init_py}")
            mod = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = mod
            spec.loader.exec_module(mod)
            return mod, module_name
        else:
            # Namespace package (no __init__.py) → must import by name with root on sys.path
            if not sys_path_root:
                raise ImportError(
                    f"{p} looks like a namespace package (no __init__.py). "
                    "Provide sys_path_root so it can be imported by dotted name."
                )
            # Ensure the parent of the namespace is importable
            mod = importlib.import_module(module_name)
            return mod, module_name

    # CASE 2: Single .py file → load by file location
    if p.is_file() and p.suffix == ".py":
        spec = importlib.util.spec_from_file_location(module_name, p)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot create spec for module at {p}")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = mod
        spec.loader.exec_module(mod)
        return mod, module_name

    raise ImportError(f"Unsupported path type: {p}")

