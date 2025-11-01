from operator import contains
import re
import json
import logging
import time
import subprocess
import whisper
from dataclasses import asdict
from pathlib import Path
from typing import List, Dict, Optional, TypeVar
# 20251027 MMH Moved youTube api imports to here.
from youtube_transcript_api import (
    YouTubeTranscriptApi, 
    FetchedTranscript,
    NotTranslatable, 
    TranslationLanguageNotAvailable
)

from fastmcp import FastMCP

# TODO 20251027 MMH: Chage to use yt-dlp and ffmpeg modules instead
#                       of external programs.

# TODO 20251101 MMH: Move ffmpeg.exe into package and allow it's installation
#                       thru automated means.                      .

T = TypeVar("T", bound="FastMCP")

logging.basicConfig(
    # level=logging.DEBUG if settings.debug else logging.INFO,
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)-8s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(Path(__file__).stem)


if "Mark-USN" in __file__:
    FFMPEG_PATH = r"C:\Program Files\FFmpeg\ffmpeg\bin\ffmpeg.exe"
else:
    FFMPEG_PATH = r"C:\Program Files\ffmpeg\bin\ffmpeg.exe"

PREFERRED_LANGS = ["en", "en-US", "en-GB", "es", "es-419", "es-ES"]

# Set to True to force using Whisper even if subtitles are available.
FORCE_AUDIO_TRANSCRIPT = False


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

# ----------------- Main Function to retrieve transcripts  -----------------

def fetch_transcript(url:str, prefer_langs: Optional[List[str]] = None) -> FetchedTranscript | Dict | None:
    """ 
    Return the transcript for the YouTube video with the given ID.
        Params: url, prefer_lang,
        Return: youtube transcript or None
    """
    # 20251027 MMH Added preserve_formatting=True to fetches.
    # 20251029 MMH Moved getting video_id to here.
    # 20251031 MMH added .to_raw_data() to convert yt transcripts to Dicts

    video_id = get_video_id(url)
    prefer_langs = prefer_langs or ["en", "es"]
    transcript = None

    try:
        ytt_api = YouTubeTranscriptApi()
        transcripts = ytt_api.list(video_id)
        # 20251027 MMH Log available languages
        langs_list = [getattr(tr, "language_code", "?") for tr in transcripts]
        logger.debug("Available languages: %s", langs_list)

        if FORCE_AUDIO_TRANSCRIPT == False and len(langs_list) >= 0:
            for lang in prefer_langs:
                if lang in langs_list :
                    transcript = ytt_api.fetch(video_id, languages=[lang], preserve_formatting=True)
                    break
            # Fallback to the first available transcript and try to translate it.
            if transcript is None:
                try:
                    logger.info("Translating transcript to preferred language: %s", prefer_langs[0])
                    transcript =  transcripts[0].translate(prefer_langs[0]).fetch(preserve_formatting=True) 
                except (NotTranslatable, TranslationLanguageNotAvailable):
                    logger.warn(f"Translation failed returning subtitles in default language {langs_list[0]}.")
                    transcript = transcripts[0].fetch(preserve_formatting=True)
        if transcript is None:
            # Returns a dict
            transcript = fetch_transcript_from_audio(url=url, video_id=video_id, audio_format="mp3" )

    except Exception as e:
        logger.warning("Could not fetch subtitles: %s", e)
        return None

    return transcript


# ----------------- Output management -----------------
def _get_outputs_dir() -> Path:
    """Base folder for project outputs (inside mymcpserver/outputs)."""
    return Path(__file__).resolve().parents[3] / "outputs"

def _get_transcripts_dir() -> Path:
    out_dir = _get_outputs_dir() / "transcripts"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir

def _get_audio_dir() -> Path:
    out_dir = _get_outputs_dir() / "audio"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def save_txt_and_json_from_transcript(transcript: list[dict], video_id: str) -> tuple[Path, Path]:
    out_dir = _get_transcripts_dir()
    txt_path = out_dir / f"transcript_{video_id}.txt"
    json_path = out_dir / f"transcript_{video_id}.json"
    trans_text = ""

    if transcript == None or len(transcript) == 0:
        return None

    for snippet in transcript:
        trans_text += snippet["text"] + " "   

    txt_path.write_text(f"{trans_text}", encoding="utf-8")
    json_path.write_text(json.dumps(transcript, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.info("💾 Saved transcript to %s and %s", txt_path, json_path)
    return txt_path, json_path


# ----------------- Audio + Whisper -----------------
def download_audio(url: str, video_id: str, audio_format: str = "mp3") -> Path:
    """Download audio from a YouTube video using yt-dlp."""
    audio_dir = _get_audio_dir()
    audio_name = f"{video_id}"
    audio_ext = audio_format

    audio_path = audio_dir / f"{video_id}.{audio_format}"

    # 20251031 MMH If the file is already cached, skip downloading.
    if not audio_path.exists():
        # 20251030 MMH yt-dlp - A feature-rich command-line audio/video downloader
        #   -x, --extract-audio  Extract audio from video
        #   -o, --output [TYPES:]TEMPLATE  It is not recommended to add the extension
        #   -P, --paths [TYPES:]PATH
        #   --audio-format See Below
        #   --ffmpeg-location PATH Location of the ffmpeg binary; either the path to 
        #                          the binary or its containing directory
        #
        # 20251030 MMH Audio Formats supported
        # (currently supported: best (default), aac, alac, flac, m4a, mp3, opus, vorbis, wav)

        cmd = ["yt-dlp", "-x", "--audio-format", audio_format, "-o", audio_name, "-P", 
                  str(audio_dir),"--ffmpeg-location", FFMPEG_PATH, url]

        logger.debug(f"Running command: {cmd}")
        # Loads the youtube audio into the specified name and path.
        # result is just there for debugging purposes.
        result = subprocess.run(cmd, check=True)
    
    # Clean up old audio files (older than 24 hours) in the audio directory.
    cutoff = time.time() - (24 * 3600)
    for file in audio_dir.iterdir():
        if file.is_file():
            if file.stat().st_mtime < cutoff:
                file.unlink()

    return audio_path


def transcribe_with_whisper(audio_path: Path, model_name: str = "base") -> Optional[Dict]:
    """Transcribe an audio file using OpenAI Whisper."""
    model = whisper.load_model(model_name)
    # loaded_audio = whisper.load_audio(str(audio_path))
    # whisper_audio = whisper.pad_or_trim(loaded_audio)

    # # make log-Mel spectrogram and move to the same device as the model
    # mel = whisper.log_mel_spectrogram(whisper_audio, n_mels=model.dims.n_mels).to(model.device)
    # # detect the spoken language
    # _, probs = model.detect_language(mel)
    # logger.info(f"Whisper detected language: {max(probs, key=probs.get)}")

    # # decode the audio
    # options = whisper.DecodingOptions(without_timestamps = False)

    transcript = whisper.transcribe(model, str(audio_path) )

    # return the recognized text
    return transcript


def fetch_transcript_from_audio(url: str, video_id: str, audio_format: str = "mp3") -> Optional[Dict]:
    logger.warning("⚠️ No subtitles. Downloading audio and transcribing with Whisper...")

    audio_path = download_audio(url, video_id, audio_format)
    transcript = transcribe_with_whisper(audio_path, model_name="base")
    # try:
    #     audio_path.unlink(missing_ok=True)
    # except Exception as e:
    #     logger.debug("Could not delete temporary audio file: %s", e)
    # save_txt_and_json_from_text(text, video_id)
    return transcript



# ----------------- MCP TOOLS -----------------
def youtube_json(url: str, prefer_lang: List[str] =  ["en", "es"]) -> str:
    """
    Extracts the transcript of a YouTube video and return the transcript 
    formatted as json.
        Params: url The YouTube video URL
                prefer_lang List of preferred language IDs for transcripts.   
        Returns: The json format of the youTube transcript 
    """

    transcript = fetch_transcript(url, prefer_lang)

    if transcript is None:
        return
    if isinstance(transcript, FetchedTranscript):
        # Convert to raw data (list of dicts)
        transcript_list = transcript.to_raw_data()  
    else:
        transcript_list = transcript
    json_transcript = json.dumps(transcript_list, ensure_ascii=False, indent=2)
    return(json_transcript)
    
def youtube_text(url: str, prefer_lang: List[str] =  ["en", "es"]) -> str:
    """
    Extracts the transcript of a YouTube video and return the text.
        Params: url: The YouTube video URL
                prefer_lang: List of preferred language IDs for transcripts   
        Returns: The text of the youTube transcript 
    """
    transcribed_text = ""
    transcript = fetch_transcript(url, prefer_lang)
    if transcript == None:
        return None
    if isinstance(transcript, FetchedTranscript):
        transcript_list = transcript.to_raw_data()
        for snippet in transcript_list:
            transcribed_text += snippet["text"] + " "
    else:
        transcribed_text = transcript.get("text", "")
  
    return transcribed_text.strip()


# ----------------- MCP integration -----------------
def register(mcp: T):
    """
    Register YouTube to text tools with the MCP instance.
        Params: mcp The MCP instance to register the tools with.`
        Returns: None
        Side Effects: Registers the tools with the MCP instance.
    """

    logger.debug("Registering tool youtube_transcript")
    mcp.tool(tags=["public", "api"])(youtube_json)
    mcp.tool(tags=["public", "api"])(youtube_text)


# ----------------- CLI -----------------
if __name__ == "__main__":
    url = "https://www.youtube.com/watch?v=DAYJZLERqe8"
    while not url:
        url = input("Enter YouTube URL: ").strip()
        if not url:
            logger.warning("⚠️ Please paste a valid YouTube URL.")
    try:
        # result = youtube_to_text(url, force_whisper=False)
        # video_id = get_video_id(url)
        
        json_transcript = youtube_json(url)
        print("\n\n--- JSON TRANSCRIPT ---\n")
        print(f"{json_transcript}")

        text_transcript = youtube_text(url)
        print("\n\n--- TEXT TRANSCRIPT ---\n")
        print(f"{text_transcript}")
    except subprocess.CalledProcessError as e:
        logger.error("❌ yt-dlp/FFmpeg error: %s", e)
    except Exception as e:
        logger.error("❌ Error: %s", e)
