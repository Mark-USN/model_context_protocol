# prompt_md_loader.py
""" Dynamic discovery and registration of MCP prompts from markdown (.md) files,
    using YAML front matter for metadata (including parameters).
"""

from __future__ import annotations

import logging
import textwrap
from pathlib import Path
from typing import Any, TypeVar
import frontmatter  # pip/uv: python-frontmatter
from fastmcp import FastMCP

T = TypeVar("T", bound=FastMCP)

logger = logging.getLogger(Path(__file__).stem)


def _normalize_params(raw_params: Any) -> dict[str, dict[str, Any]]:
    """
    Normalize the 'params' block from YAML into a dict:
        { name: {description, required, default, type} }

    Accepts either:
      - a mapping: params: { text: { ... }, lang: { ... } }
      - or a list of dicts: params: [ {name: text, ...}, {name: lang, ...} ]
    """
    if not raw_params:
        return {}

    params: dict[str, dict[str, Any]] = {}

    # Case 1: mapping style
    if isinstance(raw_params, dict):
        for name, cfg in raw_params.items():
            if cfg is None:
                cfg = {}
            elif not isinstance(cfg, dict):
                # e.g. params: {text: "some description"}
                cfg = {"description": str(cfg)}

            name_str = str(name)
            params[name_str] = {
                "description": cfg.get("description"),
                "required": bool(cfg.get("required", True)),
                "default": cfg.get("default"),
                "type": cfg.get("type", "string"),
            }
        return params

    # Case 2: list-of-dicts style
    if isinstance(raw_params, list):
        for item in raw_params:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if not name:
                continue
            name_str = str(name)
            params[name_str] = {
                "description": item.get("description"),
                "required": bool(item.get("required", True)),
                "default": item.get("default"),
                "type": item.get("type", "string"),
            }
        return params

    logger.warning("Unsupported 'params' format in front matter: %r", raw_params)
    return {}


# def _make_prompt_fn(prompt_body: str, params_meta: dict[str, dict[str, Any]]):
#     """
#     Create a callable that renders the prompt with **kwargs substituted into
#     {placeholders} in the markdown body, applying defaults / required flags
#     from params_meta.
#     """
#     # Find all {placeholders} in the body
#     placeholders = sorted(set(re.findall(r"\{([^}]+)\}", prompt_body)))

#     placeholder_set = set(placeholders)
#     params_set = set(params_meta.keys())

#     # Log mismatches to help catch typos
#     unused_params = params_set - placeholder_set
#     missing_params = placeholder_set - params_set

#     if unused_params:
#         logger.info(
#             "Params defined in YAML but not used in template: %s",
#             ", ".join(sorted(unused_params)),
#         )
#     if missing_params:
#         logger.info(
#             "Template placeholders without YAML param definitions (using implicit "
#             "required=True, no default): %s",
#             ", ".join(sorted(missing_params)),
#         )

#     def _fn(**kwargs: Any) -> str:
#         values: dict[str, Any] = {}

#         # Build final values for all placeholders
#         for name in placeholders:
#             cfg = params_meta.get(name, {})
#             required = cfg.get("required", True)
#             has_default = "default" in cfg
#             default_val = cfg.get("default")

#             if name in kwargs:
#                 values[name] = kwargs[name]
#             elif has_default:
#                 values[name] = default_val
#             elif required:
#                 raise ValueError(f"Missing required parameter '{name}' for prompt")
#             # else: optional with no default and not provided → leave out,
#             # which will cause a KeyError in format() if the template uses it.

#         # Warn about extra kwargs that don't match placeholders
#         extra = set(kwargs) - placeholder_set
#         if extra:
#             logger.warning(
#                 "Extra parameters passed to prompt (ignored in template): %s",
#                 ", ".join(sorted(extra)),
#             )

#         try:
#             rendered = prompt_body.format(**values)
#         except KeyError as e:
#             raise ValueError(f"Missing value for template placeholder: {e}") from e

#         return rendered + "\n\n"

#     return _fn


def _make_dynamic_prompt_fn(name: str, prompt_body: str, params: dict[str, dict]):
    """
    Create a function with a real dynamic signature that FastMCP accepts.
        Args:
            name: The name of the function to create.
            prompt_body: The body of the prompt template with {placeholders}.
            params: A dict of parameter metadata, keyed by parameter name.
        Returns:
            A callable function that renders the prompt with parameters.
    """

    # Build the function signature text
    parts = []
    for p, cfg in params.items():
        if "default" in cfg:
            default = repr(cfg["default"])
            parts.append(f"{p}={default}")
        else:
            parts.append(p)
    arglist = ", ".join(parts) if parts else ""

    # Build the function body code
    code = f"""
def {name}({arglist}):
    values = locals()
    try:
        return f""" + '"""' + f"""{prompt_body}""" + '"""' + f"""
    except KeyError as e:
        raise ValueError(f"Missing value for template placeholder: {{e}}")
"""

    # Prepare namespace
    ns = {}

    # Execute the function definition
    exec(textwrap.dedent(code), ns)

    # Extract the function object
    return ns[name]


def register_prompts_from_markdown(mcp: T, prompts_dir: str | Path) -> None:
    """
    Scan for .md files in the prompts directory and register them with FastMCP.

    Each .md file may optionally start with YAML front matter, e.g.:

        ---
        name: summarize_text
        description: Summarize arbitrary input text in a concise way.
        tags:
          - public
          - summarize
        style: helpful
        params:
          text:
            description: The text to summarize
            required: true
          lang:
            description: Output language
            required: false
            default: en
        ---

        Please summarize the following text in 3–5 bullet points.
        Respond in {lang}.

        {text}

    Args:
        prompts_dir (str | Path): The directory to search for .md files.

    Side Effects:
        Adds prompts to the FastMCP server for any successfully converted .md files.
    """
    prompts_path = Path(prompts_dir)

    if not prompts_path.exists() or not prompts_path.is_dir():
        logger.error("❌ Prompts directory %s does not exist or is not a directory.", prompts_path)
        return
    # 20251112 MMH rglob to find in subdirs too.
    for md_path in prompts_path.rglob("*.md"):
        try:
            post = frontmatter.load(md_path)  # parses YAML front matter if present
        except Exception as e:      # pylint: disable=broad-exception-caught
            logger.exception("Failed to parse front matter in %s: %s", md_path, e)
            continue

        body: str = str(post.content).strip()
        meta: dict[str, Any] = dict(post.metadata or {})

        # Core fields
        name: str = meta.get("name") or md_path.stem
        style: str = meta.get("style", "plain")
        description: str = meta.get("description") or f"Render '{name}' prompt ({style})."

        # Tags: allow string or list, always ensure "public"
        raw_tags = meta.get("tags") or ["public"]
        if isinstance(raw_tags, str):
            tags = {raw_tags}
        else:
            tags = {str(t).strip() for t in raw_tags if str(t).strip()}
        if "public" not in tags:
            tags.add("public")

        # Params: normalize to a stable dict format
        raw_params = meta.get("params")
        params_meta = _normalize_params(raw_params)

        # Extra meta: everything not core
        extra_meta = {
            k: v
            for k, v in meta.items()
            if k not in {"name", "description", "tags", "style", "params"}
        }

        fn = _make_dynamic_prompt_fn(name, body, params_meta)

        # Register the prompt with FastMCP
        mcp.prompt(
            name=name,
            description=description,
            tags=tags,
            meta={
                "style": style,
                "source_file": md_path.name,
                "params": params_meta,  # expose param metadata to clients
                **extra_meta,
            },
        )(fn)

        logger.info("✅ Registered prompt '%s' from %s", name, md_path.name)
