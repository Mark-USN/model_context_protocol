"""
YouTube demo and transcript helpers for UniversalClient.

Extracted from UniversalClient to keep the client class focused on MCP mechanics.
"""

import time
import logging
import re
from typing import Any, Optional , TypedDict, Literal
from urllib.parse import parse_qs, urlparse

from datetime import timedelta

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------
# Helper Methods
# ---------------------------------------------------------------------
# ---------------------------------------------------------------------------
# ID extraction 
# ---------------------------------------------------------------------------

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_PLAYLIST_ID_RE = re.compile(
        r"^(PL|UU|LL|FL|OL|RD|WL)[A-Za-z0-9_-]{10,200}$"
    )

def get_video_id(url_or_id: str) -> str | None:
    s = (url_or_id or "").strip()
    if _VIDEO_ID_RE.match(s):
        return s

    p = urlparse(s)
    host = (p.netloc or "").lower()
    path = p.path.strip("/")

    if "youtube.com" in host:
        qs = parse_qs(p.query)
        v = (qs.get("v") or [None])[0]
        if v and _VIDEO_ID_RE.match(v):
            return v

        parts = path.split("/")
        if len(parts) >= 2 and parts[0] in {"shorts", "embed", "v"}:
            cand = parts[1]
            if _VIDEO_ID_RE.match(cand):
                return cand

    if "youtu.be" in host:
        cand = path.split("/")[0]
        if _VIDEO_ID_RE.match(cand):
            return cand

    return None

    
def get_playlist_id(url_or_id: str) -> str | None:
    s = (url_or_id or "").strip()

    if _PLAYLIST_ID_RE.match(s) and not _VIDEO_ID_RE.match(s):
        return s

    p = urlparse(s)
    qs = parse_qs(p.query)
    pl = (qs.get("list") or [None])[0]
    if pl and _PLAYLIST_ID_RE.match(pl):
        return pl

    return None


class YouTubeId(TypedDict):
    kind: Literal["playlist", "video"]
    id: str


def classify_youtube_id(url_id: str) -> YouTubeId | None:
    """Return a normalized YouTube ID and its kind, or None if invalid."""

    if pid := get_playlist_id(url_id):
        return {"kind": "playlist", "id": pid}

    if vid := get_video_id(url_id):
        return {"kind": "video", "id": vid}

    return None


# ---------------------------------------------------------------------
# YouTube Demo Entry Point (was UniversalClient._run_youtube_demo)
# ---------------------------------------------------------------------

async def run_youtube_demo(client) -> None:
    """Demonstrate YouTube-related tools."""
    # Runtime diagnostics (only relevant when client/server co-located)
    import fastmcp
    import torch

    print(
        "\n\n⚠ The below information is only relevant if the client is run on the same machine as the server."
    )
    print("\nfastmcp:", fastmcp.__version__)
    print("torch:", torch.__version__)
    print("CUDA available:", torch.cuda.is_available())
    print("Device count:", torch.cuda.device_count())
    print("\n")

    # Default search term (can be overridden on the client before calling)
    if not client.yt_search:
        # client.yt_search = "chromaticity and color preception"
        client.yt_search = "Python tutorials about list comprehension -shorts"

    while not client.yt_search:
        client.yt_search = input("\033[1mEnter Search for YouTube: \033[0m").strip()
        if not client.yt_search:
            logger.warning("⚠️ Please enter a valid search term.")

    # youtube_search
    print(
        "\n\nExecuting 'youtube_search' tool "
        f"with parameters {client.yt_search}, {client.MAX_SEARCH_RESULTS}.",
    )


    yt_url_result = await client.call_tool(
        "youtube_search",
        {
            "query": client.yt_search,
            "order": "relevance",
            "max_results": client.MAX_SEARCH_RESULTS,
        },
    )

    payload: dict[str, Any] = getattr(yt_url_result, "data", None) or {}
    items: list[dict[str, Any]] = payload.get("items") or []
    videos: list[dict[str, Any]] = []
    playlists: list[dict[str, Any]] = []

    for itm in items:
        typedId = classify_youtube_id(itm.get("url") or "")
        if typedId and typedId["kind"] == "video":
            url = itm.get("url")
            if url:
                videos.append(url)
            duration = itm.get("duration") or {}
            stats = itm.get("statistics") or {}
            logger.info(
                "Video Info: for VideoId = %s\n"
                "kinds=%s video_id=%s url=%s title=%s published=%s duration_iso=%s duration_seconds=%s "
                "views=%s likes=%s comments=%s available=%s description=%s",
                typedId["id"],
                itm.get("kinds"),
                itm.get("video_id"),
                url,
                itm.get("title"),
                itm.get("publishedAt"),
                duration.get("iso8601"),
                duration.get("seconds"),
                stats.get("views"),
                stats.get("likes"),
                stats.get("comments"),
                itm.get("available"),
                itm.get("description"),
            )
        elif typedId and typedId["kind"] == "playlist":
            url = itm.get("url")
            if url:
                playlists.append(url)
            logger.info(
                "Playlist Info: for PlaylistId = %s\n"
                "kinds=%s playlist_id=%s url=%s title=%s description=%s published=%s "
                "channelTitle=%s privacyStatus=%s itemCount=%s available=%s",                                                                                                                                                                                                                                 
                typedId["id"],
                itm.get("kinds"),
                typedId["id"],
                url,
                itm.get("title"),
                itm.get("description"),
                itm.get("publishedAt"),
                itm.get("channelTitle"),
                itm.get("privacyStatus"),
                itm.get("itemCount"),
                itm.get("available"),
            )

    # If we have playlists, just process the first one for demo purposes
    if playlists:
        logger.info("Retreive the first five videos in the first playlist only.")
        logger.info("Video Info: for PlaylistId = %s\n", playlists[0])
        result = await client.call_tool(
                "youtube_playlist_video_list",
                {
                    "playlist": playlists[0],
                    "max_videos": 5,
                },
            )
        # Items should all be videos, but let's be sure.
        for itm in payload.get("items"):
            typedId = classify_youtube_id(itm.get("url") or "")
            if typedId and typedId["kind"] == "video":
                url = itm.get("url")
                duration = itm.get("duration") or {}
                stats = itm.get("statistics") or {}
                logger.info(
                    "Video Info: for VideoId = %s\n"
                    "kinds=%s video_id=%s url=%s title=%s published=%s duration_iso=%s duration_seconds=%s "
                    "views=%s likes=%s comments=%s available=%s description=%s",
                    typedId["id"],
                    itm.get("kinds"),
                    itm.get("video_id"),
                    url,
                    itm.get("title"),
                    itm.get("publishedAt"),
                    duration.get("iso8601"),
                    duration.get("seconds"),
                    stats.get("views"),
                    stats.get("likes"),
                    stats.get("comments"),
                    itm.get("available"),
                    itm.get("description"),
                )


    await get_all_transcripts(client, videos)



# ---------------------------------------------------------------------
# YouTube Transcript Methods (Subtitles/Captions)
# ---------------------------------------------------------------------

async def get_a_snippets_transcript(client, url: str) -> None:
    """Get transcripts for a given YouTube URL using youtube_snippets."""
    print(
        "\n\nExecuting 'youtube_snippets' tool "
        f"with parameters {url}",
    )
    start = time.perf_counter()

    snippets_result = await client.call_tool("youtube_snippets", {"url_or_id": url})

    elapsed = int(time.perf_counter() - start)
    video_id = get_video_id(url)

    snippets_path = client.base_output_dir() / f"{video_id}.snip"
    with open(snippets_path, "w", encoding="utf-8") as snippets_file:
        snippets_file.write(str(snippets_result.data))

    print(f"\nResult of youtube_snippets tool in {snippets_path}\n")
    print(f"The transcription of {video_id}.snip took {timedelta(seconds=elapsed)}")

async def get_a_json_transcript(client, url: str) -> None:
    """Get transcripts for a given YouTube URL using youtube_json."""
    print(
        "\n\nExecuting 'youtube_json' tool "
        f"with parameters {url}",
    )
    start = time.perf_counter()

    json_result = await client.call_tool("youtube_json", {"url_or_id": url})

    elapsed = int(time.perf_counter() - start)
    video_id = get_video_id(url)

    json_path = client.base_output_dir() / f"{video_id}.json"
    with open(json_path, "w", encoding="utf-8") as json_file:
        json_file.write(str(json_result.data))

    print(f"\nResult of youtube_json tool in {json_path}\n")
    print(f"The transcription of {video_id}.json took {timedelta(seconds=elapsed)}")

async def get_a_text_transcript(client, url: str) -> None:
    """Get transcripts for a given YouTube URL using youtube_text."""
    print(
        "\n\nExecuting 'youtube_text' tool "
        f"with parameters {url}",
    )
    start = time.perf_counter()

    text_result = await client.call_tool("youtube_text", {"url_or_id": url})
    
    elapsed = int(time.perf_counter() - start)
    video_id = get_video_id(url)

    txt_path = client.base_output_dir() / f"{video_id}.txt"
    with open(txt_path, "w", encoding="utf-8") as txt_file:
        txt_file.write(str(text_result.data))

    print(f"\nResult of youtube_text tool in {txt_path}")
    print(f"The transcription of {video_id}.txt took {timedelta(seconds=elapsed)}")

async def get_a_paragraph_transcript(client, url: str) -> None:
    """Get transcripts for a given YouTube URL using youtube_paragraph."""
    print(
        "\n\nExecuting 'youtube_paragraph' tool "
        f"with parameters {url}",
    )
    start = time.perf_counter()

    para_result = await client.call_tool("youtube_paragraph", {"url_or_id": url})
    
    elapsed = int(time.perf_counter() - start)
    video_id = get_video_id(url)

    para_path = client.base_output_dir() / f"{video_id}.para"
    with open(para_path, "w", encoding="utf-8") as para_file:
        para_file.write(str(para_result.data))

    print(f"\nResult of youtube_text tool in {para_path}")
    print(f"The transcription of {video_id}.para took {timedelta(seconds=elapsed)}")


# ---------------------------------------------------------------------
# Main function to get transcripts cycling through all tool types for
# multiple URLs
# ---------------------------------------------------------------------
async def get_all_transcripts(client, urls: str | list) -> None:
    """Get transcripts for a URL or list of URLs (rotates tool types)."""
    # No audio tools available, just cycle through the non-audio ones.
    if isinstance(urls, list):
        for idx, url in enumerate(urls):
            match idx % 4:
                case 0:
                    await get_a_snippets_transcript(client, url)
                case 1:
                    await get_a_json_transcript(client, url)
                case 2:
                    await get_a_text_transcript(client, url)
                case 3:
                    await get_a_paragraph_transcript(client, url)
    else:
        await get_a_text_transcript(client, urls)

