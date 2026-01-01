from __future__ import annotations
import os
import re
import json
import logging
import time
# import datetime
import asyncio
import concurrent.futures
import threading
from pathlib import Path
from typing import Any, List, Dict, Optional, TypeVar
import whisper
from yt_dlp import YoutubeDL
from youtube_transcript_api import FetchedTranscript


from fastmcp import FastMCP  # pylint: disable=unused-import
from ..utils.ffmpeg_bootstrap import ensure_ffmpeg_on_path, get_ffmpeg_binary_path
# from youtube_transcript_api import YouTubeTranscriptApi, FetchedTranscript

T = TypeVar("T", bound="FastMCP")

# -----------------------------
# Logging setup
# -----------------------------
logger = logging.getLogger(__name__)

PREFERRED_LANGS = ["en", "en-US", "en-GB", "es", "es-419", "es-ES"]

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

# ----------------- Output management -----------------

def _get_cache_dir() -> Path:
    """Base folder for project cache (inside mymcpserver/cache)."""
    return Path(__file__).resolve().parents[3] / "cache"

def _get_transcripts_dir() -> Path:
    """Folder for transcript cache."""
    out_dir = _get_cache_dir() / "transcripts"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir

def _get_audio_dir() -> Path:
    """Folder for temporary storage of yt_dlp audio cache.
    We delete these if they are over a day old in the code below.
    """
    out_dir = _get_cache_dir() / "audio"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir

def _get_transcript_cache_path(video_id: str) -> Path:
    """Return the path to the cached Whisper transcript JSON for this video."""
    return _get_transcripts_dir() / f"{video_id}.json"

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

    return audio_path


# =========================
# SYNC (blocking) SECTION
# =========================

def transcribe_with_whisper(
    audio_path: Path,
    model_name: str = "small",
    chunk_duration: float = CHUNK_DURATION_SECONDS,
    overlap: float = CHUNK_OVERLAP_SECONDS,
) -> Optional[List[Dict]]:
    """Transcribe an audio file using OpenAI Whisper in overlapping chunks.

    NOTE: This is a *blocking* implementation. For MCP server responsiveness and
    cancellation support, see `transcribe_with_whisper_async()` below.

    The audio is split into chunks of `chunk_duration` seconds with `overlap`
    seconds of overlap between consecutive chunks. Each chunk is fed to Whisper,
    and the results are concatenated.

    Args:
        audio_path: Path to the audio file.
        model_name: Whisper model name to use (default: "small").
        chunk_duration: Duration (in seconds) of each chunk (default: 30.0).
        overlap: Overlap (in seconds) between chunks (default: 5.0).

    Returns:
        A list of Whisper chunk dicts, or None if transcription fails.
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
    sample_rate = 16000  # Whisper.load_audio resamples to 16k internally

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
    if step <= 0:
        # Extra defense; should not happen after the guard above
        step = samples_per_chunk

    chunks: List[Dict] = []
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

        # Whisper expects audio array; whisper.transcribe runs the model.
        chunk = whisper.transcribe(model, segment_audio)
        chunks.append(chunk)
        chunk_index += 1

        if end_sample >= num_samples:
            break

    # Done with the audio file
    audio_path.unlink(missing_ok=True)
    return chunks



def fetch_audio_transcript(
    url: str,
    prefer_langs: Optional[List[str]] = None,
) -> FetchedTranscript | List[Dict] | None:
    """Download audio from YouTube and transcribe it with Whisper, with caching.

        Args:
            url: The YouTube video URL.
            video_id: The YouTube video ID.

        Returns:
            The transcript as a dictionary, or None if transcription failed.
    """
    if prefer_langs is None:
        prefer_langs = ["en", "es"]
    video_id = get_video_id(url)
    cache_path = _get_transcript_cache_path(video_id)

    # 1) If we already have a cached transcript, reuse it.
    if cache_path.exists():
        logger.info("✅ Using cached Whisper transcript for %s", video_id)
        try:
            # Touch the cache file so purge_cache() keeps it
            with cache_path.open("r", encoding="utf-8") as f:
                transcript = json.load(f)
            if transcript:
                now = time.time()
                os.utime(cache_path, (now, now))
            return transcript

        except Exception as exc:  # pragma: no cover - cache read is best-effort
            logger.warning(
                "⚠️ Failed to load cached transcript %s: %s; recomputing.",
                cache_path,
                exc,
            )

    # # 2) No cache (or cache failed) – do the full Whisper path.
    # logger.warning("⚠️ No subtitles. Downloading audio and transcribing with Whisper...")

    # Ensure ffmpeg exists and is on PATH for this process (for whisper).
    ffmpeg_dir = ensure_ffmpeg_on_path()
    logger.info("✅ Using ffmpeg from: %s", ffmpeg_dir)

    chunks: List[Dict] = []
    audio_path = download_audio(url, video_id)
    chunks = transcribe_with_whisper(
        audio_path,
        # 20251130 MMH Changed from "base" to "small" gives better transcripts
        # especially for technical content.
        model_name="small",
        chunk_duration=CHUNK_DURATION_SECONDS,
        overlap=CHUNK_OVERLAP_SECONDS,
    )

    # 3) Save to cache if we got a transcript.
    if chunks is not None:
        try:
            with cache_path.open("w", encoding="utf-8") as f:
                json.dump(chunks, f, ensure_ascii=False, indent=2)
            logger.info("💾 Saved Whisper transcript cache to %s", cache_path)
        except Exception as exc:  # pragma: no cover - cache write is best-effort
            logger.warning(
                "⚠️ Failed to write transcript cache %s: %s",
                cache_path,
                exc,
            )

    return chunks

def youtube_audio_json(url: str, prefer_langs: Optional[List[str]] = None) -> Any: # Dict | str | None:
    """
    Extracts the transcript of a YouTube video and returns the transcript
    formatted as JSON.

        Params:
            url: The YouTube video URL
            prefer_langs: List of preferred language IDs for transcripts.

        Returns:
            The JSON format of the YouTube transcript, or None.
    """

    if prefer_langs is None:
        prefer_langs = ["en", "es"]

    transcript_list = fetch_audio_transcript(url, prefer_langs)

    if transcript_list is None:
        return None

    json_transcript = json.dumps(transcript_list, ensure_ascii=False, indent=2)
    return json_transcript


def youtube_audio_text(url: str = "", prefer_langs: Optional[List[str]]=None) -> Any: # Dict | str | None:
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
    transcript_list = fetch_audio_transcript(url, prefer_langs)
    if transcript_list is None:
        return None

    # Whisper's dict has a "text" key with the full text.
    full_text_parts = [pt['text'] for pt in transcript_list]
    transcribed_text = " ".join(full_text_parts).strip()

    return transcribed_text.strip()




# =========================
# ASYNC (cooperative) SECTION
# =========================
#
# Goal: allow MCP long-jobs to be cancelled while transcribing.
# Strategy:
#   * keep the MCP tool function async
#   * yield to the event loop between chunks (await sleep(0))
#   * do the heavy Whisper work in a dedicated single worker thread so the loop
#     stays responsive and cancellation can be observed between chunks.
#
# IMPORTANT LIMITATION:
#   Cancellation is *cooperative* and takes effect BETWEEN chunks.
#   If a single chunk transcription takes a long time, cancellation will be
#   delayed until that chunk completes. To improve responsiveness, use a smaller
#   chunk_duration (e.g., 10-15s).

_WHISPER_THREAD_LOCAL = threading.local()

def _get_thread_local_whisper_model(model_name: str):
    """Load/cache Whisper model in the *worker thread* (thread-local)."""
    model = getattr(_WHISPER_THREAD_LOCAL, "model", None)
    cached_name = getattr(_WHISPER_THREAD_LOCAL, "model_name", None)
    if model is None or cached_name != model_name:
        _WHISPER_THREAD_LOCAL.model = whisper.load_model(model_name)
        _WHISPER_THREAD_LOCAL.model_name = model_name
    return _WHISPER_THREAD_LOCAL.model

def _transcribe_chunk_in_worker_thread(model_name: str, segment_audio):
    """Runs inside the dedicated worker thread."""
    model = _get_thread_local_whisper_model(model_name)
    return whisper.transcribe(model, segment_audio)

async def transcribe_with_whisper_async(
    audio_path: Path,
    model_name: str = "small",
    chunk_duration: float = CHUNK_DURATION_SECONDS,
    overlap: float = CHUNK_OVERLAP_SECONDS,
    *,
    yield_every_n_chunks: int = 1,
) -> Optional[List[Dict]]:
    """Async/transcribable variant of `transcribe_with_whisper`.

    This function yields control back to the event loop between chunks so the job
    can be cancelled by the caller.

    Args:
        audio_path: Path to the audio file.
        model_name: Whisper model name to use.
        chunk_duration: Duration (in seconds) of each chunk.
        overlap: Overlap (in seconds) between chunks.
        yield_every_n_chunks: Yield to loop every N chunks (default: 1).

    Returns:
        List of Whisper chunk dicts, or None if transcription fails.
    """
    logger.info(
        "🎧 (async) Transcribing %s with Whisper model '%s' in %.1fs chunks (overlap %.1fs)",
        audio_path,
        model_name,
        chunk_duration,
        overlap,
    )

    # Load and resample audio (this is blocking but usually fast-ish; keep it sync).
    audio = whisper.load_audio(str(audio_path))
    sample_rate = 16000

    samples_per_chunk = int(chunk_duration * sample_rate)
    overlap_samples = int(overlap * sample_rate)

    if samples_per_chunk <= 0:
        raise ValueError("chunk_duration must be > 0")

    if overlap_samples >= samples_per_chunk:
        logger.warning(
            "Overlap (%.1fs) >= chunk duration (%.1fs); disabling overlap.",
            overlap,
            chunk_duration,
        )
        overlap_samples = 0

    step = samples_per_chunk - overlap_samples
    if step <= 0:
        step = samples_per_chunk

    chunks: List[Dict] = []
    chunk_index = 0
    num_samples = audio.shape[0]

    # Dedicated single worker thread: keeps model pinned to one thread and avoids
    # 'random thread' issues that can happen if the default threadpool hops threads.
    loop = asyncio.get_running_loop()
    with concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="whisper") as ex:
        for start_sample in range(0, num_samples, step):
            # Checkpoint: if the caller cancelled, this is where CancelledError lands.
            if yield_every_n_chunks > 0 and (chunk_index % yield_every_n_chunks) == 0:
                await asyncio.sleep(0)

            end_sample = start_sample + samples_per_chunk
            segment_audio = audio[start_sample:end_sample]

            if segment_audio.size == 0:
                break

            start_time = start_sample / sample_rate
            end_time = min(num_samples, end_sample) / sample_rate

            logger.debug(
                "🧩 (async) Chunk %d: samples [%d:%d] -> time [%.2f, %.2f]s",
                chunk_index,
                start_sample,
                end_sample,
                start_time,
                end_time,
            )

            try:
                chunk = await loop.run_in_executor(
                    ex, _transcribe_chunk_in_worker_thread, model_name, segment_audio
                )
            except asyncio.CancelledError:
                # Best effort cleanup; note: a chunk already running in the worker
                # thread will still run to completion, but we stop awaiting more work.
                logger.info("🛑 Transcription cancelled during chunk %d.", chunk_index)
                raise

            chunks.append(chunk)
            chunk_index += 1

            if end_sample >= num_samples:
                break

    audio_path.unlink(missing_ok=True)
    return chunks



async def fetch_audio_transcript_async(
    url: str,
    prefer_langs: Optional[List[str]] = None,
    *,
    model_name: str = "small",
    chunk_duration: float = CHUNK_DURATION_SECONDS,
    overlap: float = CHUNK_OVERLAP_SECONDS,
) -> Optional[List[Dict]]:
    """Async wrapper around `fetch_audio_transcript` with cooperative cancellation.

    Major differences from the sync version:
      * audio download happens in a worker thread
      * transcription uses `transcribe_with_whisper_async()` so cancellation can be
        observed between chunks

    Cancellation behavior:
      * Cancelling the MCP long-job raises `asyncio.CancelledError`.
      * Cancellation takes effect BETWEEN chunks (see async transcribe notes).
    """
    if prefer_langs is None:
        prefer_langs = ["en", "es"]

    video_id = get_video_id(url)
    cache_path = _get_transcript_cache_path(video_id)

    if cache_path.exists():
        logger.info("✅ Using cached Whisper transcript for %s", video_id)
        try:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception as exc:  # pragma: no cover
            logger.warning("⚠️ Failed to load cached transcript %s: %s; recomputing.", cache_path, exc)

    # Ensure ffmpeg on PATH
    ffmpeg_dir = ensure_ffmpeg_on_path()
    logger.info("✅ Using ffmpeg from: %s", ffmpeg_dir)

    # Download audio (blocking) -> worker thread
    try:
        audio_path = await asyncio.to_thread(download_audio, url, video_id)
    except asyncio.CancelledError:
        logger.info("🛑 Cancelled during audio download.")
        raise

    # Yield after download so cancellation can be observed immediately.
    await asyncio.sleep(0)

    # Transcribe with cooperative cancellation
    chunks: Optional[List[Dict]] = None
    try:
        chunks = await transcribe_with_whisper_async(
            audio_path,
            model_name=model_name,
            chunk_duration=chunk_duration,
            overlap=overlap,
            yield_every_n_chunks=1,
        )
    except asyncio.CancelledError:
        # If cancelled, best effort cleanup of the downloaded audio file
        audio_path.unlink(missing_ok=True)
        raise

    # Cache result
    if chunks is not None:
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(chunks, f, ensure_ascii=False, indent=2)
            logger.info("💾 Saved Whisper transcript cache to %s", cache_path)
        except Exception as exc:  # pragma: no cover
            logger.warning("⚠️ Failed to write transcript cache %s: %s", cache_path, exc)

    return chunks


async def youtube_audio_json_async(url: str, prefer_langs: Optional[List[str]] = None) -> str | None:
    """Async version of youtube_audio_json (supports cooperative cancellation)."""
    chunks = await fetch_audio_transcript_async(url, prefer_langs)
    if chunks is None:
        return None
    return json.dumps(chunks, ensure_ascii=False, indent=2)


async def youtube_audio_text_async(url: str, prefer_langs: Optional[List[str]] = None) -> str | None:
    """Async version of youtube_audio_text (supports cooperative cancellation)."""
    chunks = await fetch_audio_transcript_async(url, prefer_langs)
    if chunks is None:
        return None
    # Same logic as youtube_audio_text: join segment texts
    full_text_parts: List[str] = []
    for chunk in chunks:
        text_part = (chunk.get("text") or "").strip()
        if text_part:
            full_text_parts.append(text_part)
    return " ".join(full_text_parts).strip()



# ----------------- MCP integration -----------------

def register_long(mcp: T) -> None:
    """
    Register YouTube to text audio tools with the MCP instance as a long job.

    This registers ASYNC variants so the job can be cancelled while transcribing.
    The sync versions remain available for CLI/testing.
    """
    logger.debug("✅ Registering YouTube audio transcript tools (async/cancellable)")
    mcp.tool(tags=["public", "api"])(youtube_audio_json_async)
    mcp.tool(tags=["public", "api"])(youtube_audio_text_async)

    # Optional: also register sync versions under their old names (uncomment if desired)
    # mcp.tool(tags=["public", "api"])(youtube_audio_json)
    # mcp.tool(tags=["public", "api"])(youtube_audio_text)
# ----------------- CLI -----------------


def main() -> None:
    """ CLI entry point to test the YouTube to text tool. """
    import fastmcp, torch
    from datetime import timedelta
    print("\nfastmcp:", fastmcp.__version__)
    print("torch:", torch.__version__)
    print("CUDA available:", torch.cuda.is_available())
    print("Device count:", torch.cuda.device_count())
    print("Whisper models available:", whisper.available_models())

    # CLI for testing the YouTube to text tool.
    yt_url = "https://www.youtube.com/watch?v=DAYJZLERqe8"    # 6:32 comedy
    # yt_url = "https://www.youtube.com/watch?v=_uQrJ0TkZlc"    # 6 + hours!
    # yt_url = "https://www.youtube.com/watch?v=Ro_MScTDfU4"    # 30:34 Python tutorial < 30 Mins
    # yt_url = "https://www.youtube.com/watch?v=gJz4lByMHUg"    # Just music
    # yt_url = "https://youtu.be/N23vXA-ai5M?list=PLC37ED4C488778E7E&index=1"
    # yt_url = "https://youtu.be/N23vXA-ai5M"
    # yt_url = "https://www.youtube.com/watch?v=ulebPxBw8Uw"

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

    start = time.perf_counter()
    json_trans = youtube_audio_json(yt_url)
    elapsed = time.perf_counter()-start
    print("\n\n--- JSON AUDIO TRANSCRIPT ---\n")
    print(f"{json_trans}")
    print(f"\n✅ Transcribed in {str(timedelta(seconds=elapsed))} seconds.\n")

    start = time.perf_counter()
    text_trans = youtube_audio_text(yt_url)
    elapsed = time.perf_counter()-start
    print("\n\n--- TEXT AUDIO TRANSCRIPT ---\n")
    print(f"{text_trans}")
    print(f"\n✅ Transcribed in {str(timedelta(seconds=elapsed))} seconds.\n")
    
if __name__ == "__main__":
    main()

