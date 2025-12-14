""" YouTube to Text Tool for FastMCP. Get or generate
    transcripts from YouTube videos.
"""
from __future__ import annotations
import re
import json
import logging
import time
import datetime
from pathlib import Path
from typing import List, Dict, Optional, TypeVar
from youtube_transcript_api import (
    YouTubeTranscriptApi,
    FetchedTranscript,
    TranscriptsDisabled,
    NoTranscriptFound,
    NotTranslatable,
    TranslationLanguageNotAvailable,
)
from fastmcp import FastMCP  # pylint: disable=unused-import

T = TypeVar("T", bound="FastMCP")

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)-8s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(Path(__file__).stem)

PREFERRED_LANGS = ["en", "en-US", "en-GB", "es", "es-419", "es-ES"]

# ----------------- Helpers -----------------
def get_video_id(url: str) -> str:
    """Extract the YouTube video ID from a URL.
        Args: url: The YouTube video URL.
    """
    url = url.strip()
    if not url:
        raise ValueError("Empty URL")

    # Short-link service: https://youtu.be/VIDEO_ID
    m = re.search(r"youtu\.be/([A-Za-z0-9_\-]{6,})", url)
    if m:
        return m.group(1)

    # Standard watch URLs: https://www.youtube.com/watch?v=VIDEO_ID
    m = re.search(r"[?&]v=([A-Za-z0-9_\-]{6,})", url)
    if m:
        return m.group(1)

    raise ValueError("Invalid YouTube URL")

# ----------------- Output management -----------------

def _get_outputs_dir() -> Path:
    """Base folder for project outputs (inside mymcpserver/outputs)."""
    return Path(__file__).resolve().parents[3] / "outputs"

def _get_transcripts_dir() -> Path:
    """Folder for transcript outputs."""
    out_dir = _get_outputs_dir() / "transcripts"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir

def _get_transcript_cache_path(video_id: str) -> Path:
    """Return the path to the cached Whisper transcript JSON for this video."""
    return _get_transcripts_dir() / f"{video_id}.whisper.json"


# ----------------- Main Function to retrieve transcripts  -----------------

def fetch_transcript(
    url: str,
    prefer_langs: Optional[List[str]] = None,
) -> FetchedTranscript | None:
    """
    Return the transcript for the YouTube video with the given URL.
    If no transcript is available, download the audio and use Whisper to transcribe it.
    """

    if prefer_langs is None:
        prefer_langs = ["en", "es"]
    video_id = get_video_id(url)
    prefer_langs = prefer_langs or ["en", "es"]
    transcript: FetchedTranscript | Dict | None = None
    transcripts: List | None = None

    ytt_api = YouTubeTranscriptApi()
    # 1) If no transcripts are available, see if we have a cached Whisper transcript.
    try:
        transcripts = ytt_api.list(video_id=video_id)
    except (TranscriptsDisabled, NoTranscriptFound) as e:
        logger.info("✅ No transcripts: %s", e)
        audio_transcript = _get_transcript_cache_path(video_id)
        if audio_transcript.exists():
            return audio_transcript
        return None

    # 2) Transcripts are available.
    # Log available languages
    langs_list = [getattr(tr, "language_code", "?") for tr in transcripts]
    logger.debug("✅ Available languages: %s", langs_list)

    # 3) Try preferred languages directly (this returns the raw list[dict])
    for lang in prefer_langs:
        if lang in langs_list:
            try:
                transcript = ytt_api.fetch(
                    video_id=video_id,
                    languages=[lang],
                    preserve_formatting=True,
                )
                logger.info("✅ Using transcript in preferred language: %s", lang)
                break
            except (NoTranscriptFound, TranscriptsDisabled):
                continue

        # 4) Fallback: take the *first* available Transcript and try to
        #    translate to prefer_langs[0]
        if transcript is None:
            first_tr = next(iter(transcripts), None)
            if first_tr is not None:
                try:
                    logger.info(
                        "Translating first available transcript to %s",
                        prefer_langs[0],
                    )
                    transcript = (
                        first_tr
                        .translate(prefer_langs[0])
                        .fetch(preserve_formatting=True)
                    )
                except (NotTranslatable, TranslationLanguageNotAvailable):
                    # 5) Final fallback: use the first available Transcript as-is.
                    logger.warning(
                        "⚠ Translation failed; returning subtitles in "
                        "original language %s.",
                        getattr(first_tr, "language_code", "?"),
                    )
                    transcript = first_tr.fetch(preserve_formatting=True)

    return transcript


# ----------------- MCP TOOLS -----------------

def youtube_json(url: str, prefer_langs: list[str]  = ["en", "es"]) -> str | None:
    """
    Extracts the transcript of a YouTube video and returns the transcript
    formatted as JSON.

        Params:
            url: The YouTube video URL
            prefer_langs: List of preferred language IDs for transcripts.

        Returns:
            The JSON format of the YouTube transcript, or None.
    """

    transcript = fetch_transcript(url, prefer_langs)

    if transcript is None:
        return None

    transcript_list = transcript.to_raw_data()

    json_transcript = json.dumps(transcript_list, ensure_ascii=False, indent=2)
    return json_transcript


def youtube_text(url: str, prefer_langs: Optional[List[str]] = None) -> str | None:
    """
    Extracts the transcript of a YouTube video and returns the text.

        Params:
            url: The YouTube video URL
            prefer_langs: List of preferred language IDs for transcripts.

        Returns:
            The text of the YouTube transcript, or None.
    """

    if prefer_langs is None:
        prefer_langs = ["en", "es"]

    transcribed_text = ""
    transcript = fetch_transcript(url, prefer_langs)
    if transcript is None:
        return None

    # Convert to raw data (list of dicts)
    transcript_list = transcript.to_raw_data()
    # Combine all text snippets into a single string.
    for snippet in transcript_list:
        transcribed_text += snippet["text"] + " "

    return transcribed_text.strip()

# ----------------- MCP integration -----------------

def register(mcp: T) -> None:
    """
    Register YouTube to text tools with the MCP instance.

        Params:
            mcp: The MCP instance to register the tools with.
    """
    logger.debug("✅ Registering YouTube transcript tools")
    # during server startup / tool registration.
    mcp.tool(tags=["public", "api"])(youtube_json)
    mcp.tool(tags=["public", "api"])(youtube_text)


# ----------------- CLI -----------------
def main() -> None:
    """ CLI entry point to test the YouTube to text tool. """
    from datetime import timedelta

    # CLI for testing the YouTube to text tool.
    # yt_url = "https://www.youtube.com/watch?v=DAYJZLERqe8"    # 6:32 comedy
    # yt_url = "https://www.youtube.com/watch?v=_uQrJ0TkZlc"    # 6 + hours!
    # yt_url = "https://www.youtube.com/watch?v=Ro_MScTDfU4"    # 30:34 Python tutorial < 30 Mins
    # yt_url = "https://www.youtube.com/watch?v=gJz4lByMHUg"    # Just music
    # yt_url = "https://youtu.be/N23vXA-ai5M?list=PLC37ED4C488778E7E&index=1"
    # yt_url = "https://youtu.be/N23vXA-ai5M"
    yt_url = "https://www.youtube.com/watch?v=ulebPxBw8Uw"

    while not yt_url:
        yt_url = input("Enter YouTube URL: ").strip()
        if not yt_url:
            logger.warning("⚠️ Please paste a valid YouTube URL.")

    start = time.perf_counter()
    json_trans = youtube_json(yt_url)
    elapsed = time.perf_counter()-start
    print("\n\n--- JSON TRANSCRIPT ---\n")
    print(f"{json_trans}")
    print(f"\n✅ Transcribed in {str(timedelta(seconds=elapsed))} seconds.\n")

    start = time.perf_counter()
    text_trans = youtube_text(yt_url)
    elapsed = time.perf_counter()-start
    print("\n\n--- TEXT TRANSCRIPT ---\n")
    print(f"{text_trans}")
    print(f"\n✅ Transcribed in {str(timedelta(seconds=elapsed))} seconds.\n")
    
if __name__ == "__main__":
    main()