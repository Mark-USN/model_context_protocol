"""
YouTube demo workflow for UniversalClient.

Runs youtube_search, classifies results, optionally samples playlists,
and exercises transcript tools in a round-robin pattern so that each
tool is exercised without calling the same URL four times.
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import timedelta
from typing import Any
# from modules.utils.paths import resolve_cache_paths
from modules.utils.youtube_ids import extract_video_id, extract_playlist_id
from urllib.parse import parse_qs, urlparse
from modules.utils.log_utils import get_logger


logger = get_logger(__name__)

# _VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
# _PLAYLIST_ID_RE = re.compile(r"^(PL|UU|LL|FL|OL|RD|WL)[A-Za-z0-9_-]{10,200}$")


# # -------------------------------------------------
# # ID helpers
# # -------------------------------------------------
# def get_video_id(value: str) -> str | None:
#     s = value.strip()
#     if _VIDEO_ID_RE.fullmatch(s):
#         return s

#     p = urlparse(s)
#     if "youtube.com" in p.netloc:
#         qs = parse_qs(p.query)
#         v = (qs.get("v") or [None])[0]
#         if isinstance(v, str) and _VIDEO_ID_RE.fullmatch(v):
#             return v

#         parts = p.path.strip("/").split("/")
#         if len(parts) >= 2 and parts[0] in {"shorts", "embed", "v"}:
#             if _VIDEO_ID_RE.fullmatch(parts[1]):
#                 return parts[1]

#     if "youtu.be" in p.netloc:
#         cand = p.path.strip("/").split("/", 1)[0]
#         if _VIDEO_ID_RE.fullmatch(cand):
#             return cand

#     return None


# def get_playlist_id(value: str) -> str | None:
#     s = value.strip()
#     if _PLAYLIST_ID_RE.fullmatch(s):
#         return s

#     p = urlparse(s)
#     qs = parse_qs(p.query)
#     pl = (qs.get("list") or [None])[0]
#     if isinstance(pl, str) and _PLAYLIST_ID_RE.fullmatch(pl):
#         return pl

#     return None


# -------------------------------------------------
# Tool discovery
# -------------------------------------------------
async def fetch_tool_names(client: Any) -> set[str]:
    tools = await client.list_tools()
    return {getattr(t, "name", "") for t in tools if getattr(t, "name", "")}


# -------------------------------------------------
# Transcript exerciser
# -------------------------------------------------
async def exercise_transcripts_round_robin(
    client: Any,
    video_urls: list[str],
) -> None:
    tool_names = await fetch_tool_names(client)

    tools_in_order = [
        ("youtube_snippets", "snip"),
        ("youtube_json", "json"),
        ("youtube_text", "txt"),
        ("youtube_paragraph", "para"),
    ]
    available = [t for t in tools_in_order if t[0] in tool_names]
    if not available:
        logger.info("No transcript tools available.")
        return

    for idx, url in enumerate(video_urls):
        tool, ext = available[idx % len(available)]
        start = time.perf_counter()
        result = await client.call_tool(tool, {"url_or_id": url})
        elapsed = time.perf_counter() - start

        vid = extract_video_id(url) or f"video_{idx}"
        out = client.cache_output_dir() / f"{vid}.{ext}"
        payload = getattr(result, "data", result)

        if ext in {"json", "snip"}:
            out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        else:
            out.write_text(str(payload), encoding="utf-8")

        logger.info("Saved %s (%s)", out, timedelta(seconds=elapsed))


# -------------------------------------------------
# Main demo
# -------------------------------------------------
async def run_youtube_demo(client: Any) -> None:
    if not client.yt_search:
        client.yt_search = "Python tutorials about list comprehension -shorts"

    logger.info("Running youtube_search: %s", client.yt_search)
    res = await client.call_tool(
        "youtube_search",
        {
            "query": client.yt_search,
            "order": "relevance",
            "max_results": client.MAX_SEARCH_RESULTS,
        },
    )

    payload = getattr(res, "data", {}) or {}
    items = payload.get("items") or []

    video_urls: list[str] = []
    playlist_urls: list[str] = []

    for itm in items:
        url = itm.get("url") or ""
        if extract_video_id(url):
            video_urls.append(url)
        elif extract_playlist_id(url):
            playlist_urls.append(url)

    if playlist_urls:
        logger.info("Sampling playlist: %s", playlist_urls[0])
        pl_vid_result = await client.call_tool(
            "youtube_playlist_video_list",
            {"playlist": playlist_urls[0], "max_videos": 5},
        )
        pl_vid_list = getattr(pl_vid_result, "data", {}) or {}

    await exercise_transcripts_round_robin(client, video_urls)
