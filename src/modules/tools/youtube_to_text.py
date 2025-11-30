""" YouTube to Text Tool for FastMCP. Get or generate
    transcripts from YouTube videos.
"""
from __future__ import annotations
import re
import json
import logging
import time
from pathlib import Path
from typing import List, Dict, Optional, TypeVar

import numpy as np
import whisper
from yt_dlp import YoutubeDL
from youtube_transcript_api import (
    YouTubeTranscriptApi,
    FetchedTranscript,
    TranscriptsDisabled,
    NoTranscriptFound,
    NotTranslatable,
    TranslationLanguageNotAvailable,
)
from fastmcp import FastMCP  # pylint: disable=unused-import
from ..utils.ffmpeg_bootstrap import ensure_ffmpeg_on_path, get_ffmpeg_binary_path

T = TypeVar("T", bound="FastMCP")

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)-8s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(Path(__file__).stem)

PREFERRED_LANGS = ["en", "en-US", "en-GB", "es", "es-419", "es-ES"]

# Set to True to force using Whisper even if subtitles are available.
FORCE_AUDIO_TRANSCRIPT = False

# ----------------- Whisper chunking configuration -----------------
# Duration (in seconds) for each Whisper chunk
CHUNK_DURATION_SECONDS = 30.0
# Overlap (in seconds) between consecutive chunks
CHUNK_OVERLAP_SECONDS = 5.0


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


# ----------------- Main Function to retrieve transcripts  -----------------

def fetch_transcript(
    url: str,
    prefer_langs: Optional[List[str]] = None,
) -> FetchedTranscript | Dict | None:
    """
    Return the transcript for the YouTube video with the given URL.
    If no transcript is available, download the audio and use Whisper to transcribe it.
    """
    video_id = get_video_id(url)
    prefer_langs = prefer_langs or ["en", "es"]
    transcript: FetchedTranscript | Dict | None = None

    ytt_api = YouTubeTranscriptApi()
    transcripts = ytt_api.list(video_id=video_id)

    # Log available languages
    langs_list = [getattr(tr, "language_code", "?") for tr in transcripts]
    logger.debug("✅ Available languages: %s", langs_list)

    if not FORCE_AUDIO_TRANSCRIPT and len(langs_list) > 0:
        # 1) Try preferred languages directly (this returns the raw list[dict])
        for lang in prefer_langs:
            try:
                transcript = ytt_api.fetch(
                    video_id=video_id,
                    languages=[lang],
                    preserve_formatting=True,
                )
                logger.info("✅ Using transcript in preferred language: %s", lang)
                break
            except NoTranscriptFound | TranscriptsDisabled:
                continue

        # 2) Fallback: take the *first* available Transcript and try to
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
                    logger.warning(
                        "⚠ Translation failed; returning subtitles in "
                        "original language %s.",
                        getattr(first_tr, "language_code", "?"),
                    )
                    transcript = first_tr.fetch(preserve_formatting=True)

    # 3) Final fallback: Whisper from audio
    if transcript is None:
        transcript = fetch_transcript_from_audio(url=url, video_id=video_id)

    return transcript


# ----------------- Output management -----------------

def _get_outputs_dir() -> Path:
    """Base folder for project outputs (inside mymcpserver/outputs)."""
    return Path(__file__).resolve().parents[3] / "outputs"


def _get_transcripts_dir() -> Path:
    """Folder for transcript outputs."""
    out_dir = _get_outputs_dir() / "transcripts"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def _get_audio_dir() -> Path:
    """Folder for temporary storage of yt_dlp audio outputs.

    We delete these if they are over a day old in the code below.
    """
    out_dir = _get_outputs_dir() / "audio"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


# ----------------- Audio + Whisper -----------------

def download_audio(url: str, video_id: str) -> Path:
    """Download audio from a YouTube video using yt-dlp, with simple caching."""
    audio_dir = _get_audio_dir()

    # If we already have any file named <video_id>.* reuse it
    existing = sorted(audio_dir.glob(f"{video_id}.*"))
    if existing:
        audio_path = existing[0]
    else:
        output_template = str(audio_dir / "%(id)s.%(ext)s")

        # Make sure we have an ffmpeg directory for yt_dlp to use.
        ffmpeg_dir = get_ffmpeg_binary_path()

        ydl_opts = {
            "extract-audio": True,               # Extract audio from video.
            "verbose": False,
            "quiet": True,                       # Suppress normal output.
            "no_warnings": True,
            "skip_download": False,
            "extract_flat": False,
            "format": "bestaudio/best",
            "outtmpl": output_template,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "wav",
                    "preferredquality": "192",
                }
            ],
        }

        if ffmpeg_dir:
            # Explicitly tell yt_dlp where ffmpeg lives
            ydl_opts["ffmpeg_location"] = ffmpeg_dir

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            # FFmpegExtractAudio will produce <id>.wav in the same dir
            audio_path = audio_dir / f"{info['id']}.wav"

    # Clean up old audio files (older than 24 hours) in the audio directory.
    cutoff = time.time() - (24 * 3600)
    for f in audio_dir.iterdir():
        if f.is_file() and f.stat().st_mtime < cutoff:
            f.unlink(missing_ok=True)

    return audio_path


def transcribe_with_whisper(
    audio_path: Path,
    model_name: str = "small",
    chunk_duration: float = CHUNK_DURATION_SECONDS,
    overlap: float = CHUNK_OVERLAP_SECONDS,
) -> Optional[Dict]:
    """Transcribe an audio file using OpenAI Whisper in overlapping chunks.

    The audio is split into chunks of `chunk_duration` seconds with `overlap`
    seconds of overlap between consecutive chunks. Each chunk is fed to Whisper,
    and the results are concatenated.

    Args:
        audio_path: Path to the audio file.
        model_name: Whisper model name to use (default: "small").
        chunk_duration: Duration (in seconds) of each chunk (default: 30.0).
        overlap: Overlap (in seconds) between chunks (default: 5.0).

    Returns:
        A dict with:
            - "text": full concatenated transcript
            - "segments": list of chunk-level segments with start/end times
            - "chunk_duration": chunk duration used
            - "overlap": overlap used
    """
    logger.info(
        "🎧 Transcribing %s with Whisper model '%s' in %.1fs chunks (overlap %.1fs)",
        audio_path,
        model_name,
        chunk_duration,
        overlap,
    )

    # Load the model once
    model = whisper.load_model(model_name)

    # Load and resample audio to 16 kHz mono using Whisper's helper
    audio = whisper.load_audio(str(audio_path))
    # Whisper.load_audio already resamples to 16 kHz internally
    sample_rate = 16000

    samples_per_chunk = int(chunk_duration * sample_rate)
    overlap_samples = int(overlap * sample_rate)

    if samples_per_chunk <= 0:
        raise ValueError("chunk_duration must be > 0")

    # Guard against pathological overlap >= duration
    if overlap_samples >= samples_per_chunk:
        logger.warning(
            "Overlap (%.1fs) >= chunk duration (%.1fs); disabling overlap.",
            overlap,
            chunk_duration,
        )
        overlap_samples = 0

    step = samples_per_chunk - overlap_samples

    full_text_parts: List[str] = []
    segments: List[Dict] = []

    # Iterate over the audio in steps of "step" samples
    chunk_index = 0
    num_samples = audio.shape[0]

    for start_sample in range(0, num_samples, step):
        end_sample = start_sample + samples_per_chunk
        segment_audio = audio[start_sample:end_sample]

        if segment_audio.size == 0:
            break

        # Approximate times in seconds for this chunk
        start_time = start_sample / sample_rate
        end_time = min(num_samples, end_sample) / sample_rate

        logger.debug(
            "🧩 Chunk %d: samples [%d:%d] -> time [%.2f, %.2f]s",
            chunk_index,
            start_sample,
            end_sample,
            start_time,
            end_time,
        )

        # Whisper expects a float32 array (which load_audio already returns)
        result = whisper.transcribe(model, segment_audio)

        chunk_text = result.get("text", "").strip()
        if chunk_text:
            full_text_parts.append(chunk_text)
            segments.append(
                {
                    "index": chunk_index,
                    "start": start_time,
                    "end": end_time,
                    "text": chunk_text,
                },
            )

        chunk_index += 1

        if end_sample >= num_samples:
            break

    combined_text = " ".join(full_text_parts).strip()

    return {
        "text": combined_text,
        "segments": segments,
        "chunk_duration": chunk_duration,
        "overlap": overlap,
    }


def fetch_transcript_from_audio(url: str, video_id: str) -> Optional[Dict]:
    """Download audio from YouTube and transcribe it with Whisper.

        Args:
            url: The YouTube video URL.
            video_id: The YouTube video ID.

        Returns:
            The transcript as a dictionary, or None if transcription failed.
    """
    logger.warning("⚠️ No subtitles. Downloading audio and transcribing with Whisper...")

    # Ensure ffmpeg exists and is on PATH for this process (for whisper).
    ffmpeg_dir = ensure_ffmpeg_on_path()
    logger.info("✅ Using ffmpeg from: %s", ffmpeg_dir)

    audio_path = download_audio(url, video_id)
    transcript = transcribe_with_whisper(
        audio_path,
        # 20251130 MMH Changed from "base" to "small" gives better transcripts
        # especially for technical content.
        model_name="small",             
        chunk_duration=CHUNK_DURATION_SECONDS,
        overlap=CHUNK_OVERLAP_SECONDS,
    )
    return transcript


# ----------------- MCP TOOLS -----------------

def youtube_json(url: str = "", prefer_lang: list[str] | None = None) -> str | None:
    """
    Extracts the transcript of a YouTube video and returns the transcript
    formatted as JSON.

        Params:
            url: The YouTube video URL
            prefer_lang: List of preferred language IDs for transcripts.

        Returns:
            The JSON format of the YouTube transcript, or None.
    """
    if prefer_lang is None:
        prefer_lang = ["en", "es"]

    transcript = fetch_transcript(url, prefer_lang)

    if transcript is None:
        return None

    if isinstance(transcript, FetchedTranscript):
        transcript_list = transcript.to_raw_data()
    else:
        # Whisper (or any other audio-based) path returns a dict already
        transcript_list = transcript

    json_transcript = json.dumps(transcript_list, ensure_ascii=False, indent=2)
    return json_transcript


def youtube_text(url: str = "", prefer_lang: List[str] | None = None) -> str | None:
    """
    Extracts the transcript of a YouTube video and returns the text.

        Params:
            url: The YouTube video URL
            prefer_lang: List of preferred language IDs for transcripts.

        Returns:
            The text of the YouTube transcript, or None.
    """
    if prefer_lang is None:
        prefer_lang = ["en", "es"]

    transcribed_text = ""
    transcript = fetch_transcript(url, prefer_lang)
    if transcript is None:
        return None

    if isinstance(transcript, FetchedTranscript):
        # Convert to raw data (list of dicts)
        transcript_list = transcript.to_raw_data()
        # Combine all text snippets into a single string.
        for snippet in transcript_list:
            transcribed_text += snippet["text"] + " "
    else:
        # Whisper's dict has a "text" key with the full text.
        transcribed_text = transcript.get("text", "")

    return transcribed_text.strip()


# ----------------- MCP integration -----------------

def register(mcp: T) -> None:
    """
    Register YouTube to text tools with the MCP instance.

        Params:
            mcp: The MCP instance to register the tools with.
    """
    logger.debug("✅ Registering YouTube transcript tools")
    # Do NOT call ensure_ffmpeg_on_path() here to avoid side effects
    # during server startup / tool registration.
    mcp.tool(tags=["public", "api"])(youtube_json)
    mcp.tool(tags=["public", "api"])(youtube_text)


# ----------------- CLI -----------------

if __name__ == "__main__":
    # CLI for testing the YouTube to text tool.
    yt_url = "https://www.youtube.com/watch?v=DAYJZLERqe8"
    while not yt_url:
        yt_url = input("Enter YouTube URL: ").strip()
        if not yt_url:
            logger.warning("⚠️ Please paste a valid YouTube URL.")

    ffmpeg_path = ensure_ffmpeg_on_path()
    if not ffmpeg_path:
        raise SystemExit(
            "❌ FFmpeg is not available. Please install "
            "FFmpeg and ensure it is on the system PATH."
        )
    logger.info("✅ Using ffmpeg at %s", get_ffmpeg_binary_path())

    json_trans = youtube_json(yt_url)
    print("\n\n--- JSON TRANSCRIPT ---\n")
    print(f"{json_trans}")

    text_trans = youtube_text(yt_url)
    print("\n\n--- TEXT TRANSCRIPT ---\n")
    print(f"{text_trans}")
