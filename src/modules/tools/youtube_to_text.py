import re
import json
import logging
import subprocess
from pathlib import Path
from typing import List, Optional, TypeVar
# 20251027 MMH Moved youTube api imports to here.
from youtube_transcript_api import YouTubeTranscriptApi, FetchedTranscript
# 20251027 MMH Added youTube api formatters. 
from youtube_transcript_api.formatters import (
   JSONFormatter, 
   PrettyPrintFormatter, 
   NotTranslatable, 
   TranslationLanguageNotAvailable
)

from fastmcp import FastMCP

T = TypeVar("T", bound="FastMCP")

logger = logging.getLogger(Path(__file__).stem)

# FFMPEG_DIR = r""  # Example: r"C:\Program Files\ffmpeg\bin"
PREFERRED_LANGS = ["en", "en-US", "en-GB", "es", "es-419", "es-ES"]

# ----------------- Helpers -----------------
def get_video_id(url: str) -> str:
    url = url.strip()
    if not url:
        raise ValueError("Empty URL")

    # YouTube uses a short-link service for videos that looks like:
    # https://youtu.be/VIDEO_ID or https://youtu.be/dQw4w9WgXcQ
    m = re.search(r"youtu\.be/([A-Za-z0-9_\-]{6,})", url)
    if m:
        return m.group(1)

    m = re.search(r"[?&]v=([A-Za-z0-9_\-]{6,})", url)
    if m:
        return m.group(1)

    raise ValueError("Invalid YouTube URL")


# def _normalize_entries_to_dicts(entries: List[object]) -> List[dict]:
#     """Normalize subtitle objects to dicts with {start, duration, text}."""
#     normalized = []
#     for e in entries:
#         if isinstance(e, dict):
#             normalized.append({
#                 "start": float(e.get("start", 0.0)),
#                 "duration": float(e.get("duration", 0.0)),
#                 "text": e.get("text", "")
#             })
#         else:
#             start = getattr(e, "start", 0.0)
#             duration = getattr(e, "duration", 0.0)
#             text = getattr(e, "text", "")
#             normalized.append({
#                 "start": float(start) if start is not None else 0.0,
#                 "duration": float(duration) if duration is not None else 0.0,
#                 # 20251026 MMH text is already defaulted to "" in getattr above
#                 # 
#                 "text": text
#             })
#     return normalized


# def fetch_subtitles(video_id: str, prefer_langs: Optional[List[str]] = None) -> Optional[List[dict]]:
def fetch_transcript(video_id: str, prefer_langs: Optional[List[str]] = None) -> Optional[FetchedTranscript]:
    """ Try to fetch YouTube subtitles if available.
        Return: youtube transcript or None
    """
    # 20251027 MMH Changed to return youTube api raw format directly so that formatters could be used.
    # 20251027 MMH Added preserve_formatting=True to fetches.

    prefer_langs = prefer_langs or ["en", "es"]
    # 20251027 MMH Moved youTube api imports to top of file.
    # try:
    #     from youtube_transcript_api import YouTubeTranscriptApi
    #     # 20251027 MMH Added youTube api formatters. 
    #     from youtube_transcript_api.formatters import JSONFormatter, TextFormatter
    # except Exception as e:
    #     logger.warning("Could not import youtube_transcript_api: %s", e)
    #     return None

    try:
        ytt_api = YouTubeTranscriptApi()
        transcripts = ytt_api.list(video_id)
        # 20251027 MMH Log available languages
        langs = [getattr(tr, "language_code", "?") for tr in transcripts]
        logger.debug("Available languages: %s", langs)

        for tr in transcripts:
            if getattr(tr, "language_code", "") in prefer_langs:
                return tr.fetch(preserve_formatting=True)
                # 20251027 MMH Original code below
                # raw = tr.fetch()
                # return _normalize_entries_to_dicts(raw)

        # Fallback to the first available transcript and try to translate it.
        if transcripts:
            # 20251027 MMH Original code below
            # return transcripts[0].fetch(preserve_formatting=True)
            # raw = transcripts[0].fetch()
            # return _normalize_entries_to_dicts(raw)
            try:
                logger.info("Translating transcript to preferred language: %s", prefer_langs[0])
                return transcripts[0].translate(prefer_langs[0]).fetch(preserve_formatting=True) 
            except (NotTranslatable, TranslationLanguageNotAvailable):
                logger.warn(f"Translation failed returning subtitles in default language {langs[0]}.")
                return transcripts[0].fetch(preserve_formatting=True)
    except Exception as e:
        logger.warning("Could not fetch subtitles: %s", e)
        return None

    return None


# ----------------- Output management -----------------
def _get_outputs_dir() -> Path:
    """Base folder for project outputs (inside mymcpserver/outputs)."""
    return Path(__file__).resolve().parents[1] / "outputs"

def _get_transcripts_dir() -> Path:
    out_dir = _get_outputs_dir() / "transcripts"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir

# def _get_audio_dir() -> Path:
#     out_dir = _get_outputs_dir() / "audio"
#     out_dir.mkdir(parents=True, exist_ok=True)
#     return out_dir

def save_txt_and_json_from_subtitles(entries: list[dict], video_id: str) -> tuple[Path, Path]:
    out_dir = _get_transcripts_dir()
    txt_path = out_dir / f"transcript_{video_id}.txt"
    json_path = out_dir / f"transcript_{video_id}.json"

    txt_path.write_text("\n".join(e["text"] for e in entries), encoding="utf-8")
    json_path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.info("💾 Saved transcript to %s and %s", txt_path, json_path)
    return txt_path, json_path


def get_json_transcript(raw_transcript: FetchedTranscript)->str:
    """
        get_json_transcript
        Params: raw_transcript The transcript returned by youTube
        Returns: A json formatted variation of the data
    """
    # .format_transcript(transcript) turns the transcript into a JSON string.
    return JSONFormatter().format_transcript(raw_transcript, indent=2)

def get_text_transcript(raw_transcript: FetchedTranscript)->str:
    """
        get_text_transcript
        Params: raw_transcript The transcript returned by youTube
        Returns: The text derived from the transcript and formatted 
    """
    # .format_transcript(transcript) turns the transcript into a JSON string.
    return PrettyPrintFormatter().format_transcript(raw_transcript)

def save_raw_subtitles(transcript: FetchedTranscript, video_id: str) -> tuple[Path, Path]:
    out_dir = _get_transcripts_dir()
    raw_path = out_dir / f"transcript_{video_id}.raw"
    txt_path = out_dir / f"transcript_{video_id}.txt"
    json_path = out_dir / f"transcript_{video_id}.json"

    raw_path.write_text(f"{transcript}", encoding="utf-8")

    # .format_transcript(transcript) turns the transcript into a JSON string.
    json_formatted = JSONFormatter().format_transcript(transcript, indent=2)
    # Now we can write it out to a file.
    with open(json_path, 'w', encoding='utf-8') as json_file:
        json_file.write(json_formatted)
        logger.info(f"💾 Saved transcript to {json_path}")

    # .format_transcript(transcript) turns the transcript into pretty text.
    pretty_formatted = PrettyPrintFormatter().format_transcript(transcript)
    # Now we can write it out to a file.
    with open(txt_path, 'w', encoding='utf-8') as txt_file:
        txt_file.write(pretty_formatted)
        logger.info(f"💾 Saved transcript to {txt_path}")

    return raw_path, json_path, txt_path



# def save_txt_and_json_from_text(text: str, video_id: str) -> tuple[Path, Path]:
#     out_dir = _get_transcripts_dir()
#     txt_path = out_dir / f"transcript_{video_id}.txt"
#     json_path = out_dir / f"transcript_{video_id}.json"

#     txt_path.write_text(text, encoding="utf-8")
#     json_path.write_text(
#         json.dumps([{"index": 0, "text": text}], ensure_ascii=False, indent=2),
#         encoding="utf-8",
#     )

#     logger.info("💾 Saved transcript to %s and %s", txt_path, json_path)
#     return txt_path, json_path


# # ----------------- Audio + Whisper -----------------
# def download_audio(url: str, video_id: str, out_ext: str = "mp3") -> Path:
#     """Download audio from a YouTube video using yt-dlp."""
#     out_dir = _get_audio_dir()
#     out_file = out_dir / f"{video_id}.{out_ext}"

#     cmd = ["yt-dlp", "-x", "--audio-format", out_ext, "-o", str(out_file), url]
#     if FFMPEG_DIR:
#         cmd.extend(["--ffmpeg-location", FFMPEG_DIR])

#     logger.debug("Running command: %s", " ".join(cmd))
#     subprocess.run(cmd, check=True)

#     return out_file


# def transcribe_with_whisper(path: Path, model_name: str = "base") -> str:
#     """Transcribe an audio file using OpenAI Whisper."""
#     import whisper
#     model = whisper.load_model(model_name)
#     result = model.transcribe(str(path))
#     return result.get("text", "").strip()


# # ----------------- Pipeline -----------------
# def youtube_to_text(url: str, force_whisper: bool = False) -> str:
#     video_id = get_video_id(url)

#     if not force_whisper:
#         logger.info("Searching for subtitles...")
#         subs = fetch_subtitles(video_id, PREFERRED_LANGS)
#         if subs:
#             logger.info("✅ Subtitles found.")
#             save_raw_subtitles(subs, video_id)
#             return " ".join(e["text"] for e in subs)

#     logger.warning("⚠️ No subtitles. Downloading audio and transcribing with Whisper...")
#     audio = download_audio(url, video_id, out_ext="mp3")
#     text = transcribe_with_whisper(audio, model_name="base")
#     try:
#         audio.unlink(missing_ok=True)
#     except Exception as e:
#         logger.debug("Could not delete temporary audio file: %s", e)
#     save_txt_and_json_from_text(text, video_id)
#     return text


def youtube_transcript(url: str, prefer_lang: List[str] =  ["en", "es"]) -> FetchedTranscript:
    """
    Extracts the transcript of a YouTube video and return it.
    Paramts: url The YouTube video URL
                prefer_lang List of preferred languages for subtitles   
    Returns: The youTube transcript 
    """

    video_id = get_video_id(url)
    return fetch_transcript(video_id, prefer_lang)
    # text = youtube_to_text(url, force_whisper=False)

    # video_id = get_video_id(url)
    # txt_path = _get_transcripts_dir() / f"transcript_{video_id}.txt"
    # json_path = _get_transcripts_dir() / f"transcript_{video_id}.json"

    # return {
    #     "text": text,
    #     "txt_path": str(txt_path),
    #     "json_path": str(json_path),
    # }


def youtube_json(url: str, prefer_lang: List[str] =  ["en", "es"]) -> str:
    """
    Extracts the transcript of a YouTube video and return the transcript 
    formatted as json.
    Paramts: url The YouTube video URL
                prefer_lang List of preferred languages for subtitles   
    Returns: The json format of the youTube transcript 
    """

    video_id = get_video_id(url)
    raw_transcript = fetch_transcript(video_id, prefer_lang)
    return get_json_transcript(raw_transcript)
 
    
def youtube_text(url: str, prefer_lang: List[str] =  ["en", "es"]) -> str:
    """
    Extracts the transcript of a YouTube video and return the text.
    Paramts: url The YouTube video URL
                prefer_lang List of preferred languages for subtitles   
    Returns: The text of the youTube transcript 
    """

    video_id = get_video_id(url)
    raw_transcript = fetch_transcript(video_id, prefer_lang)
    return get_text_transcript(raw_transcript)
         

# ----------------- MCP integration -----------------
def register(mcp: T):
    logger.debug("Registering tool youtube_transcript")
    mcp.tool(tags=["public", "api"])(youtube_transcript)
    mcp.tool(tags=["public", "api"])(youtube_json)
    mcp.tool(tags=["public", "api"])(youtube_text)


# ----------------- CLI -----------------
if __name__ == "__main__":
    url = ""
    while not url:
        url = input("Enter YouTube URL: ").strip()
        if not url:
            logger.warning("⚠️ Please paste a valid YouTube URL.")

    try:
        # result = youtube_to_text(url, force_whisper=False)
        video_id = get_video_id(url)
        raw_transcript = fetch_transcript(video_id)
        result = get_text_transcript(raw_transcript)
        print("\n--- TRANSCRIPT ---\n")
        print(result)
    except subprocess.CalledProcessError as e:
        logger.error("❌ yt-dlp/FFmpeg error: %s", e)
    except Exception as e:
        logger.error("❌ Error: %s", e)
