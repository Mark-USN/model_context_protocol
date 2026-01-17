"""
YouTube search + metadata tools (playlist-aware).

Tools:
  - youtube_search: search for videos and/or playlists; returns full metadata for videos
  - youtube_video_info: metadata for one or many video IDs/URLs
  - youtube_playlist_videos: expand a playlist ID/URL into per-video metadata (same schema as search videos)

Notes:
  - search.list is lightweight and does NOT include duration/stats; we batch videos.list for all videoIds.
  - videos.list accepts up to 50 IDs per call; playlistItems.list is paged (50 per page).
"""

from __future__ import annotations

import logging
import re
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Tuple, TypeVar, Annotated
from urllib.parse import parse_qs, urlparse

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from pydantic import Field
from fastmcp import FastMCP

from ..utils.api_keys import api_vault

T = TypeVar("T", bound=FastMCP)
logger = logging.getLogger(__name__)


# -----------------------------
# Enums / schema helpers
# -----------------------------

class YtOrder(str, Enum):
    date = "date"
    rating = "rating"
    relevance = "relevance"
    title = "title"
    videocount = "videocount"


ORDER_HELP = {
    YtOrder.date: "Reverse chronological by publish date.",
    YtOrder.rating: "Highest to lowest rating.",
    YtOrder.relevance: "Most relevant to the query (default).",
    YtOrder.title: "Alphabetical by title.",
    YtOrder.videocount: "Channels by uploaded video count; live by concurrent viewers.",
}


class SearchKind(str, Enum):
    video = "video"
    playlist = "playlist"
    both = "video,playlist"


# -----------------------------
# ID extraction + duration parsing
# -----------------------------

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

# Playlist IDs are not fixed length; common prefixes:
#  PL... (most user playlists), UU... (uploads), LL... (likes), RD... (mix), OL... etc.
_PLAYLIST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,200}$")

_ISO8601_DUR_RE = re.compile(
    r"^P"
    r"(?:(?P<days>\d+)D)?"
    r"(?:T"
    r"(?:(?P<hours>\d+)H)?"
    r"(?:(?P<minutes>\d+)M)?"
    r"(?:(?P<seconds>\d+)S)?"
    r")?$"
)


def parse_iso8601_duration_to_seconds(dur: str) -> int:
    """
    YouTube returns ISO-8601 durations like:
      PT15M33S, PT1H2M, PT49S, P1DT2H
    """
    m = _ISO8601_DUR_RE.match(dur or "")
    if not m:
        return 0
    days = int(m.group("days") or 0)
    hours = int(m.group("hours") or 0)
    minutes = int(m.group("minutes") or 0)
    seconds = int(m.group("seconds") or 0)
    return (((days * 24 + hours) * 60 + minutes) * 60) + seconds


def extract_video_id(url_or_id: str) -> Optional[str]:
    """Extract a YouTube videoId from a URL or raw ID; returns None if not found."""
    s = (url_or_id or "").strip()
    if _VIDEO_ID_RE.match(s):
        return s

    p = urlparse(s)
    host = (p.netloc or "").lower()
    path = p.path.strip("/")

    # youtube.com/watch?v=VIDEO
    if "youtube.com" in host:
        qs = parse_qs(p.query)
        v = (qs.get("v") or [None])[0]
        if v and _VIDEO_ID_RE.match(v):
            return v

        # /shorts/<id>, /embed/<id>, /v/<id>
        parts = path.split("/")
        if len(parts) >= 2 and parts[0] in {"shorts", "embed", "v"}:
            cand = parts[1]
            if _VIDEO_ID_RE.match(cand):
                return cand

    # youtu.be/<id>
    if "youtu.be" in host:
        cand = path.split("/")[0]
        if _VIDEO_ID_RE.match(cand):
            return cand

    return None


def extract_playlist_id(url_or_id: str) -> Optional[str]:
    """Extract a YouTube playlistId from a URL or raw playlist ID; returns None if not found."""
    s = (url_or_id or "").strip()

    # If they pass a raw playlist ID
    if _PLAYLIST_ID_RE.match(s) and not _VIDEO_ID_RE.match(s):
        # Heuristic: accept raw IDs; caller can validate by API response.
        return s

    p = urlparse(s)
    qs = parse_qs(p.query)
    pl = (qs.get("list") or [None])[0]
    if pl and _PLAYLIST_ID_RE.match(pl):
        return pl

    # playlist URL may be /playlist?list=...
    # For completeness: /watch?v=...&list=...
    return None


def normalize_video_inputs(inputs: Iterable[str]) -> Tuple[List[str], List[Dict[str, Any]]]:
    """
    Returns:
      (video_ids, errors)
    errors is a list of {input, error}
    """
    video_ids: List[str] = []
    errors: List[Dict[str, Any]] = []

    for raw in inputs:
        vid = extract_video_id(raw)
        if not vid:
            errors.append({"input": raw, "error": "Could not extract video_id"})
        else:
            video_ids.append(vid)

    # De-dupe while preserving order
    seen = set()
    deduped: List[str] = []
    for vid in video_ids:
        if vid not in seen:
            seen.add(vid)
            deduped.append(vid)

    return deduped, errors


# -----------------------------
# YouTube API client helpers
# -----------------------------

def _get_youtube_client():
    vault = api_vault()
    google_key = vault.get_value(key="GOOGLE_KEY")
    if not google_key:
        raise RuntimeError("Missing GOOGLE_KEY from api_vault()")
    return build("youtube", "v3", developerKey=google_key)


def _as_int(v: Any) -> int:
    try:
        return int(v)
    except Exception:
        return 0


def _chunked(seq: List[str], size: int) -> Iterable[List[str]]:
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def _videos_list(youtube, video_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Fetch snippet + contentDetails + statistics for many video IDs.
    Returns dict keyed by video_id -> full API item
    """
    out: Dict[str, Dict[str, Any]] = {}
    if not video_ids:
        return out

    # videos.list supports up to 50 IDs per request
    for chunk in _chunked(video_ids, 50):
        req = youtube.videos().list(  # pylint: disable=no-member
            part="snippet,contentDetails,statistics",
            id=",".join(chunk),
            maxResults=len(chunk),
        )
        resp = req.execute()
        for item in resp.get("items", []) or []:
            out[item.get("id", "")] = item
    return out


def _shape_video_item(video_id: str, video_item: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Produce MCP-friendly JSON for a video result.
    If video_item is None (private/deleted/unavailable), still return a stub.
    """
    if not video_item:
        return {
            "kind": "video",
            "video_id": video_id,
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "title": "",
            "description": "",
            "publishedAt": "",
            "duration": {"iso8601": "PT0S", "seconds": 0},
            "statistics": {"views": 0, "likes": 0, "comments": 0},
            "available": False,
        }

    snippet = video_item.get("snippet") or {}
    content = video_item.get("contentDetails") or {}
    stats = video_item.get("statistics") or {}

    dur_iso = content.get("duration") or "PT0S"
    dur_s = parse_iso8601_duration_to_seconds(dur_iso)

    return {
        "kind": "video",
        "video_id": video_id,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "title": snippet.get("title", ""),
        "description": snippet.get("description", ""),
        "publishedAt": snippet.get("publishedAt", ""),
        "duration": {"iso8601": dur_iso, "seconds": dur_s},
        "statistics": {
            "views": _as_int(stats.get("viewCount")),
            "likes": _as_int(stats.get("likeCount")),
            "comments": _as_int(stats.get("commentCount")),
        },
        "available": True,
    }


def _shape_playlist_search_item(search_item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Playlists don't have duration/views/likes/comments in a meaningful single value.
    For search results, we return what search.list gives us + a playlist URL + playlist_id.
    (If you want playlist itemCount/title/etc beyond snippet, add playlists.list later.)
    """
    snippet = search_item.get("snippet") or {}
    pid = (search_item.get("id") or {}).get("playlistId", "")

    return {
        "kind": "playlist",
        "playlist_id": pid,
        "url": f"https://www.youtube.com/playlist?list={pid}" if pid else "",
        "title": snippet.get("title", ""),
        "description": snippet.get("description", ""),
        "publishedAt": snippet.get("publishedAt", ""),
        "channelTitle": snippet.get("channelTitle", ""),
        "thumbnails": snippet.get("thumbnails", {}),
    }


# -----------------------------
# MCP Tools
# -----------------------------

def youtube_search(
    query: Annotated[str, Field(description="Search terms.")],
    order: Annotated[
        YtOrder,
        Field(
            default=YtOrder.relevance,
            description="Sort order. " + " ".join(f"{k.value}: {v}" for k, v in ORDER_HELP.items()),
        ),
    ] = YtOrder.relevance,
    max_results: Annotated[int, Field(description="Max search items (1-50).", ge=1, le=50)] = 10,
    kinds: Annotated[
        SearchKind,
        Field(
            default=SearchKind.both,
            description="Return videos only, playlists only, or both.",
        ),
    ] = SearchKind.both,
) -> Dict[str, Any]:
    """
    Search YouTube and return MCP-friendly JSON.

    Important behavior:
      - Preserves the ordering of search results.
      - For video results, enriches with duration + statistics (via videos.list).
      - For playlist results, returns playlist snippet fields + playlist_id + playlist URL,
        but does NOT expand (user can call youtube_playlist_videos to expand).
    """
    youtube = _get_youtube_client()

    # search.list returns "items" ordered per the request's sort criteria
    req = youtube.search().list(  # pylint: disable=no-member
        part="snippet,id",
        q=query,
        type=kinds.value,  # "video", "playlist", or "video,playlist"
        maxResults=max_results,
        order=order.value,
    )

    try:
        resp = req.execute()
    except HttpError as e:
        return {
            "query": query,
            "order": order.value,
            "maxResults": max_results,
            "kinds": kinds.value,
            "items": [],
            "errors": [{"error": "YouTube API error", "details": str(e)}],
        }

    search_items: List[Dict[str, Any]] = resp.get("items") or []

    # Gather all video IDs in search order for a single batch metadata call
    # Playlist results are handled separately.
    video_ids_in_order: List[str] = []
    for it in search_items:
        kind = (it.get("id") or {}).get("kind", "")
        if kind.endswith("#video"):
            vid = (it.get("id") or {}).get("videoId")
            if vid:
                video_ids_in_order.append(vid)

    video_map = _videos_list(youtube, video_ids_in_order)

    # Build ordered output items (same order as search.list)
    out_items: List[Dict[str, Any]] = []
    for it in search_items:
        id_obj = it.get("id") or {}
        kind = id_obj.get("kind", "")

        if kind.endswith("#video"):
            vid = id_obj.get("videoId", "")
            out_items.append(_shape_video_item(vid, video_map.get(vid)))
        elif kind.endswith("#playlist"):
            out_items.append(_shape_playlist_search_item(it))
        else:
            # Unexpected kind; keep a minimally useful record
            out_items.append({"kind": "unknown", "raw": it})

    return {
        "query": query,
        "order": order.value,
        "maxResults": max_results,
        "kinds": kinds.value,
        "items": out_items,
        "errors": [],
    }


def youtube_video_info(
    inputs: Annotated[
        List[str],
        Field(description="List of YouTube video URLs or video IDs."),
    ],
) -> Dict[str, Any]:
    """
    Return full metadata (snippet + duration + stats) for one or many videos.
    Preserves the order of the provided inputs (after removing invalid inputs).
    """
    youtube = _get_youtube_client()

    video_ids, errors = normalize_video_inputs(inputs)
    video_map = _videos_list(youtube, video_ids)

    # Preserve input order (deduped order)
    items = [_shape_video_item(vid, video_map.get(vid)) for vid in video_ids]

    return {
        "inputs_count": len(inputs),
        "video_ids_count": len(video_ids),
        "items": items,
        "errors": errors,
    }


def youtube_playlist_videos(
    playlist: Annotated[
        str,
        Field(description="YouTube playlist URL or playlist ID (list=...)."),
    ],
    max_videos: Annotated[
        int,
        Field(description="Max videos to return from the playlist.", ge=1, le=500),
    ] = 50,
) -> Dict[str, Any]:
    """
    Expand a playlist to per-video metadata objects (same schema as youtube_search video items).

    This is the *user-controlled* expansion tool, so callers can decide whether to use playlists.
    """
    youtube = _get_youtube_client()

    playlist_id = extract_playlist_id(playlist)
    if not playlist_id:
        return {
            "playlist": playlist,
            "playlist_id": "",
            "items": [],
            "errors": [{"input": playlist, "error": "Could not extract playlist_id"}],
        }

    # 1) Get video IDs from playlistItems.list (paged)
    video_ids: List[str] = []
    page_token: Optional[str] = None
    errors: List[Dict[str, Any]] = []

    try:
        while True:
            req = youtube.playlistItems().list(  # pylint: disable=no-member
                part="contentDetails",
                playlistId=playlist_id,
                maxResults=min(50, max_videos - len(video_ids)),
                pageToken=page_token,
            )
            resp = req.execute()
            for it in resp.get("items", []) or []:
                cd = it.get("contentDetails") or {}
                vid = cd.get("videoId")
                if vid:
                    video_ids.append(vid)
                    if len(video_ids) >= max_videos:
                        break

            if len(video_ids) >= max_videos:
                break

            page_token = resp.get("nextPageToken")
            if not page_token:
                break
    except HttpError as e:
        errors.append({"error": "YouTube API error", "details": str(e)})

    # 2) Batch fetch video metadata
    video_map = _videos_list(youtube, video_ids)

    # 3) Preserve playlist order
    items = [_shape_video_item(vid, video_map.get(vid)) for vid in video_ids]

    return {
        "playlist": playlist,
        "playlist_id": playlist_id,
        "requested_max_videos": max_videos,
        "returned_videos": len(items),
        "items": items,
        "errors": errors,
    }


def register(mcp: T):
    """Register youtube_search tools with MCPServer."""
    logger.info("Registering youtube_search tools")
    mcp.tool(tags=["public", "api"])(youtube_search)
    mcp.tool(tags=["public", "api"])(youtube_video_info)
    mcp.tool(tags=["public", "api"])(youtube_playlist_videos)
