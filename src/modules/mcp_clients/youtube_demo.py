"""
YouTube demo workflow for UniversalClient.

Runs youtube_search, classifies results, optionally samples playlists,
and exercises transcript tools in a round-robin pattern so that each
tool is exercised without calling the same URL four times.
"""

from __future__ import annotations

import json
import logging
# import re
import time
from datetime import timedelta
from typing import Any
# from modules.utils.paths import resolve_cache_paths
from modules.utils.youtube_ids import extract_video_id, extract_playlist_id
# from urllib.parse import parse_qs, urlparse
from modules.utils.log_utils import get_logger, log_tree
from .ai_prompt import (
    NormalizedQuery, 
    mcp_messages_to_openai,
    prompt_result_messages_to_llm,
    normalize_youtube_query, 
    post_filter, 
    LlmMessage
)


logger = get_logger(__name__)

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
        log_tree(
                logger,
                logging.INFO,
                f"{tool}({url}):",
                result,
                collapse_keys={"env"},  # env can be huge/noisy
                redact_keys={"token", "api_key"},
            )

        vid = extract_video_id(url) or f"video_{idx}"
        out = client.cache_output_dir() / f"{vid}.{ext}"
        payload = getattr(result, "data", result)

        if ext in {"json"}:
            out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        else:
            out.write_text(str(payload), encoding="utf-8")

        logger.info("Saved %s (%s)", out, timedelta(seconds=elapsed))

# -------------------------------------------------
# Search exerciser
# -------------------------------------------------
async def exercise_youtube_search(client: Any) -> list[dict[str, Any]]:
    if not client.yt_search:
        client.yt_search = "English language python tutorials about list comprehension do not include short videos."
    
    logger.info("Executing youtube_query_normalizer prompt")
    prompt_result = await client.get_prompt(
        "youtube_query_normalizer",
        {"search_string": client.yt_search},
    )

    openai_messages = prompt_result_messages_to_llm(prompt_result.messages)

    log_tree(
            logger,
            logging.INFO,
            "OpenAI Messages:",
            openai_messages,
            collapse_keys={"env"},  # env can be huge/noisy
            redact_keys={"token", "api_key"},
        )

    ai_query = normalize_youtube_query(openai_messages)
    query = ai_query.query
    log_tree(
            logger,
            logging.INFO,
            "ai_query:",
            ai_query,
            collapse_keys={"env"},  # env can be huge/noisy
            redact_keys={"token", "api_key"},
        )
    logger.info("Normalized YouTube query: %s", query)

    yt_search_args: dict[str, Any] = {
            "query": ai_query.query,
            "order": "relevance",
            "max_results": client.MAX_SEARCH_RESULTS,
        }

    logger.info("Running youtube_search:")
    log_tree(
            logger,
            logging.INFO,
            "youtube_search:",
            yt_search_args,
            collapse_keys={"env"},  # env can be huge/noisy
            redact_keys={"token", "api_key"},
        )

    res = await client.call_tool("youtube_search", yt_search_args)
    call_title = 'youtube_search('
    f'query: {yt_search_args["query"]}, '
    f'order: {yt_search_args["order"]}, '
    f'max_results: {yt_search_args["max_results"]})'

    log_tree(
        logger,
        logging.INFO,
        call_title,
        res,
        collapse_keys={"env"},  # env can be huge/noisy
        redact_keys={"token", "api_key"},
    )

    payload = getattr(res, "data", {}) or {}
    return payload.get("items") or []



# -------------------------------------------------
# Main demo
# -------------------------------------------------
async def run_youtube_demo(client: Any) -> None:

    video_urls: list[str] = []
    playlist_urls: list[str] = []

    items = await exercise_youtube_search(client)

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
        log_tree(
            logger,
            logging.INFO,
            f"youtube_playlist_video_list(playlist:{playlist_urls[0]}, "
            "max_videos: 5)",
            pl_vid_result,
            collapse_keys={"env"},  # env can be huge/noisy
            redact_keys={"token", "api_key"},
        )
        # pl_vid_list = getattr(pl_vid_result, "data", {}) or {}


    await exercise_transcripts_round_robin(client, video_urls)
