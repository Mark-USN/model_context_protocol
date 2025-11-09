# prompt_md_loader.py
from __future__ import annotations
"""
Dynamic discovery and registration of MCP prompts from markdown (.md) files.
"""


"""
This section automatically scans a file for *.md files,
imports them safely, and registers them into an MCP server.
"""
from operator import contains
import re
import logging
from pathlib import Path
from typing import Iterable, TypeVar, Dict
from fastmcp import FastMCP  # or import your `mcp` instance

T = TypeVar("T", bound=FastMCP)

# -----------------------------
# Logging setup
# -----------------------------
logging.basicConfig(
    # level=logging.DEBUG if settings.debug else logging.INFO,
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)-8s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(Path(__file__).stem)

# Patterns for front matter delimiters (Theamatic Breaks in MarkDown)
dash_pattern = re.compile(r"^\s{0, 3}---\s*$", re.MULTILINE)
underscore_pattern = re.compile(r"^\s{0, 3}___\s*$", re.MULTILINE)
star_pattern = re.compile(r"^\s{0, 3}---\s*$", re.MULTILINE)

def _split_front_matter(md_txt: str):
    """
    _split_front_matter splits markdown text into front matter and body.
    Args:
        md_txt (str): The markdown text.
    Returns:
        fm (str): The front matter text.

    Side Effects:
        Populates the global prompts_dic with discovered prompts.

    """
    first_line = md_txt.split('\n', 1)[0]
    if re.match(dash_pattern, first_line):
        _, fm_txt, body_txt = md_txt.split("---", 2)
        return fm_txt.strip(), body_txt.strip()
    elif re.match(underscore_pattern, first_line):
        _, fm_txt, body_txt = md_txt.split("___", 2)
        return fm_txt.strip(), body_txt.strip()
    elif re.match(star_pattern, first_line):
        _, fm_txt, body_txt = md_txt.split("***", 2)
        return fm_txt.strip(), body_txt.strip()
    else:
        pass

    return "", md_txt.strip()

def _parse_front_matter(fm_txt: str):
    """
    _parse_front_matter converts the front matter to a dictionary of fields to be supplied 
    to the @mcp.prompt decorator.

    Args:
        fm_txt (str): The front matter text split off from the main body of the md file.
    Returns:
        A dictionary of mcp.prompt parameters and their values.

    Side Effects:
        None

    """

    # TODO: Add code to grab variables and their types from the front matter.

    name = None
    tags = set()
    style = None
    description = None

    # Minimal parser; replace with yaml.safe_load if you prefer
    for line in fm_text.splitlines():
        key, _, val = line.partition(":")
        key = key.strip().lower()
        val = val.strip()
        if key == "name":
            name = val
        elif key == "style":
            style = val
        elif key == "tags":
            if "[" in val and "]" in val:
                inside = val.split("[", 1)[1].split("]", 1)[0]
                tags = {t.strip() for t in inside.split(",") if t.strip()}
        elif key == "description":
            description = val

    return {
        "name": name,
        "tags": tags,
        "style": style,
        "description": description,
    }

def register_prompts_from_markdown(mcp: T, prompts_dir: str | Path) -> None:
    """
    register_prompts_from_markdown. Scan for .md files in the prompts directory 
    and register them with FastMCP.

    Args:
        prompts_dir (str | Path): The directory to search for .md files.
    Returns:
        None

    Side Effects:
        Adds Prompts to the FastMCP server for any successfully converted .md files.

    """
    if isinstance(prompts_dir, Path):
        prompts_path = prompts_dir
    else:
        prompts_path = Path(prompts_dir)

    if not prompts_path.exists() or not prompts_path.is_dir():
        logger.exception(f"❌ Prompts directory {prompts_path} does not exist or is not a directory.")
        return

    # Get a list of all .md files in the directory and process them one by one.
    for md_path in prompts_path.glob("*.md"):
        raw = md_path.read_text(encoding="utf-8")
        fm_text, body = _split_front_matter(raw)
        if fm_text != "":
            meta = _parse_front_matter(fm_text)
            name = meta["name"] or md_path.stem
            tags = meta["tags"] or set("public")
            style = meta["style"] or "plain"
            description = meta["description"] or f"Render '{name}' prompt ({style})."
        else:
            name = md_path.stem
            tags = set("public")
            style = "plain"
            description = f"Render '{name}' prompt ({style})."


        # Build a small wrapper function and register it
        # Note: the below function is not visible outside this function
        def make_func(prompt_body: str):
            # Look for parameters in the prompt body and use them as function args
            params = re.findall(r"\{([^}]+)\}", prompt_body)
            param_line=""
            if len(params) > 0:
                for p in params:
                    param_line += f"{p}: str = Field(description='Parameter {p} for the prompt.') ,"
                param_line = param_line[:-1]  # Remove trailing comma

            def _fn(param_line) -> str:
                return f"{prompt_body}\n\n"
            return _fn

        # Create the actual prompt function
        fn = make_func(body)  # registration happens via decorator

        # demo_server looks for the "public" tag to expose tools
        if "public" not in tags:
            tags.add("public")

        # Register the prompt with FastMCP
        mcp.prompt(
            name=name,
            description=description,
            tags=tags,
            meta={"style": style, "source_file": md_path.name},
        )(fn)

