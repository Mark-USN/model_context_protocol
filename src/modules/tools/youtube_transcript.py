"""YouTube transcript tool for FastMCP.

This module fetches transcripts/subtitles for a YouTube video using
`youtube-transcript-api`, with a best-effort on-disk cache.

Key behaviors:
- Accepts either a full YouTube URL or a bare video id.
- Tries preferred languages first (descending priority).
- Falls back to translating the first available transcript when possible.
- Writes/reads a JSON cache under a configurable cache directory.

Environment variables:
- MCP_CACHE_DIR: override the base cache directory.

Notes for AI agents:
- The primary public entrypoints (MCP tools) are `youtube_json()` and
  `youtube_text()`.
- `fetch_transcript()` is the core I/O function; it returns raw transcript
  snippets as JSON-serializable dictionaries.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Sequence, TypedDict, TypeVar
from urllib.parse import parse_qs, urlparse

from youtube_transcript_api import (
    FetchedTranscript,
    NoTranscriptFound,
    NotTranslatable,
    TranscriptsDisabled,
    TranslationLanguageNotAvailable,
    YouTubeTranscriptApi,
)
from fastmcp import FastMCP  # pylint: disable=unused-import

logger = logging.getLogger(__name__)

T = TypeVar("T", bound="FastMCP")


class TranscriptSnippet(TypedDict):
    """Raw transcript snippet shape returned by `FetchedTranscript.to_raw_data()`."""

    text: str
    start: float
    duration: float


#: Default language priority (descending).
PREFERRED_LANGS: tuple[str, ...] = (
    "en",
    "en-US",
    "en-GB",
    "es",
    "es-419",
    "es-ES",
)

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def get_video_id(url_or_id: str) -> str:
    """Extract a YouTube video id from a URL *or* accept a bare id.

    Args:
        url_or_id: Full YouTube URL (watch/shorts/youtu.be) or the bare video id.

    Returns:
        The YouTube video id.

    Raises:
        ValueError: If the input is empty or does not contain a valid video id.
    """

    candidate = (url_or_id or "").strip()
    if not candidate:
        raise ValueError("Empty URL/video id")

    # Allow callers/agents to pass just a video id.
    if "://" not in candidate and _VIDEO_ID_RE.fullmatch(candidate):
        return candidate

    parsed = urlparse(candidate)

    # https://youtu.be/<id>
    if parsed.netloc.endswith("youtu.be"):
        vid = parsed.path.lstrip("/").split("/", 1)[0]
        if _VIDEO_ID_RE.fullmatch(vid or ""):
            return vid

    # https://www.youtube.com/watch?v=<id>
    qs = parse_qs(parsed.query)
    if "v" in qs and qs["v"]:
        vid = qs["v"][0]
        if _VIDEO_ID_RE.fullmatch(vid or ""):
            return vid

    # https://www.youtube.com/shorts/<id>
    if parsed.path.startswith("/shorts/"):
        vid = parsed.path.removeprefix("/shorts/")
        if "/" not in vid and _VIDEO_ID_RE.fullmatch(vid):
            return vid
    
    raise ValueError(f"Invalid YouTube URL/video id: {url_or_id!r}")


def _get_cache_dir() -> Path:
    """Base folder for project cache.

    Resolution order:
    1) MCP_CACHE_DIR environment variable
    2) <repo_root>/cache (best-effort heuristic: 3 parents up from this file)
    3) ./cache (fallback)
    """

    if override := os.environ.get("MCP_CACHE_DIR"):
        return Path(override).expanduser().resolve()

    here = Path(__file__).resolve()
    try:
        return here.parents[3] / "cache"
    except IndexError:
        return Path.cwd() / "cache"


def _get_transcripts_dir() -> Path:
    """Folder for transcript cache."""

    out_dir = _get_cache_dir() / "transcripts"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def _get_transcript_cache_path(video_id: str) -> Path:
    """Return the path to the cached transcript JSON for this video."""

    return _get_transcripts_dir() / f"{video_id}.json"


def _as_raw_snippets(transcript: FetchedTranscript | list[TranscriptSnippet]) -> list[TranscriptSnippet]:
    """Normalize transcript output to raw JSON-serializable snippet dicts."""

    if isinstance(transcript, list):
        return transcript
    return transcript.to_raw_data()  # already JSON-friendly


def transcript_to_list_and_cache(
    transcript: FetchedTranscript | list[TranscriptSnippet] | None,
    cache_path: Path,
) -> list[TranscriptSnippet] | None:
    """Convert a fetched transcript into raw snippet dictionaries and cache to disk.

    This is "best effort" caching: any write failure is logged and the transcript
    is still returned.

    Args:
        transcript: Transcript object from `youtube-transcript-api` (or raw list)
            or None.
        cache_path: Destination JSON path.

    Returns:
        The transcript as `list[TranscriptSnippet]`, or None.
    """

    if transcript is None:
        return None

    transcript_list = _as_raw_snippets(transcript)

    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(transcript_list, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("💾 Saved transcript cache to %s", cache_path)
    except OSError as exc:
        logger.warning("⚠️ Failed to write transcript cache %s: %s", cache_path, exc)

    return transcript_list


def fetch_transcript(
    url_or_id: str,
    prefer_langs: Sequence[str] | None = None,
) -> list[TranscriptSnippet] | None:
    """Fetch a transcript for a YouTube video and return raw snippet dicts.

    Args:
        url_or_id: YouTube URL or video id.
        prefer_langs: Preferred language codes (descending priority). If None,
            defaults to :data:`PREFERRED_LANGS`.

    Returns:
        A list of transcript snippets or None when no transcript exists.
    """

    langs = list(prefer_langs) if prefer_langs is not None else list(PREFERRED_LANGS)
    video_id = get_video_id(url_or_id)
    cache_path = _get_transcript_cache_path(video_id)

    # 1) Best-effort cache read.
    if cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(cached, list):
                cache_path.touch()
                logger.info("✅ Using cached transcript for %s", video_id)
                return cached  # type: ignore[return-value]
        except (OSError, json.JSONDecodeError) as exc:  # pragma: no cover
            logger.warning(
                "⚠️ Failed to load cached transcript %s: %s; recomputing.",
                cache_path,
                exc,
            )

    ytt_api = YouTubeTranscriptApi()

    # 2) Try preferred languages (descending priority) via `fetch()`.
    try:
        fetched = ytt_api.fetch(
            video_id,
            languages=langs or None,
            preserve_formatting=True,
        )
        return transcript_to_list_and_cache(fetched, cache_path)
    except TranscriptsDisabled:
        logger.info("✅ Transcripts disabled for %s", video_id)
        return None
    except NoTranscriptFound:
        # Preferred languages unavailable; we may still be able to fetch some other
        # language or translate.
        pass

    # 3) Fallback: list available transcripts; try translating the first available.
    try:
        transcript_list = ytt_api.list(video_id)
    except (TranscriptsDisabled, NoTranscriptFound) as exc:
        logger.info("✅ No transcripts for %s: %s", video_id, exc)
        return None

    # Log available language codes for debugging.
    try:
        available_langs = [getattr(tr, "language_code", "?") for tr in transcript_list]
        logger.debug("✅ Available languages for %s: %s", video_id, available_langs)
    except Exception:  # pragma: no cover
        pass

    first_tr = next(iter(transcript_list), None)
    if first_tr is None:
        return None

    try:
        if langs:
            logger.info("Translating first available transcript to %s", langs[0])
            fetched = first_tr.translate(langs[0]).fetch(preserve_formatting=True)
        else:
            fetched = first_tr.fetch(preserve_formatting=True)
    except (NotTranslatable, TranslationLanguageNotAvailable):
        logger.warning(
            "⚠️ Translation failed; returning subtitles in original language %s.",
            getattr(first_tr, "language_code", "?"),
        )
        fetched = first_tr.fetch(preserve_formatting=True)

    return transcript_to_list_and_cache(fetched, cache_path)

def json_to_paragraphs(
    transcript_list: list[dict],
    *,
    gap_s: float = 1.5,
) -> str:
    paragraphs: list[list[str]] = []
    current: list[str] = []
    last_end: float | None = None

    for snip in transcript_list:
        text = snip.get("text", "").strip()
        if not text:
            continue

        start = snip.get("start", 0.0)
        duration = snip.get("duration", 0.0)

        if last_end is not None and start - last_end > gap_s:
            paragraphs.append(current)
            current = []

        current.append(text)
        last_end = start + duration

    if current:
        paragraphs.append(current)

    return "\n\n".join(" ".join(p) for p in paragraphs)




def youtube_json(url_or_id: str, prefer_langs: Sequence[str] | None = None) -> str | None:
    """Return the transcript formatted as JSON, or None.

    Args:
        url_or_id: YouTube URL or video id.
        prefer_langs: Preferred language codes (descending priority).

    Returns:
        A JSON string (pretty-printed) or None.
    """

    transcript_list = fetch_transcript(url_or_id, prefer_langs)
    if transcript_list is None:
        return None
    return json.dumps(transcript_list, ensure_ascii=False, indent=2)


def youtube_text(url_or_id: str, prefer_langs: Sequence[str] | None = None) -> str | None:
    """Return the transcript as a single space-joined string, or None."""

    transcript_list = fetch_transcript(url_or_id, prefer_langs)
    if transcript_list is None:
        return None

    # Combine all text snippets into a single string.
    return " ".join(snippet.get("text", "") for snippet in transcript_list).strip()


def youtube_paragraph(url_or_id: str, prefer_langs: Sequence[str] | None = None) -> str | None:
    """Return the transcript as a single space-joined string, or None."""

    transcript_list = fetch_transcript(url_or_id, prefer_langs)
    if transcript_list is None:
        return None

    # Combine all text snippets into a single string.
    return json_to_paragraphs(transcript_list)

def register(mcp: T) -> None:
    """Register YouTube transcript tools with the MCP instance."""

    logger.debug("✅ Registering YouTube transcript tools")
    mcp.tool(tags=["public", "api"])(youtube_json)
    mcp.tool(tags=["public", "api"])(youtube_text)
    mcp.tool(tags=["public", "api"])(youtube_paragraph)

def main() -> None:
    """CLI entry point to test transcript retrieval."""

    from datetime import timedelta

    yt_url = "https://www.youtube.com/watch?v=ulebPxBw8Uw"

    while not yt_url:
        yt_url = input("Enter YouTube URL: ").strip()
        if not yt_url:
            logger.warning("⚠️ Please paste a valid YouTube URL.")

    start = time.perf_counter()
    trans = youtube_json(yt_url)
    elapsed = time.perf_counter() - start
    print("\n\n--- JSON TRANSCRIPT ---\n")
    print(json.dumps(trans, indent=2, ensure_ascii=False))
    print(f"\n✅ Transcribed in {timedelta(seconds=elapsed)}.\n")

    start = time.perf_counter()
    trans = youtube_text(yt_url)
    elapsed = time.perf_counter() - start
    print("\n\n--- TEXT TRANSCRIPT ---\n")
    print(trans)
    print(f"\n✅ Transcribed in {timedelta(seconds=elapsed)}.\n")

    start = time.perf_counter()
    trans = youtube_paragraph(yt_url)
    elapsed = time.perf_counter() - start
    print("\n\n--- PARAGRAPH TRANSCRIPT ---\n")
    print(trans)
    print(f"\n✅ Transcribed in {timedelta(seconds=elapsed)}.\n")


if __name__ == "__main__":
    main()
