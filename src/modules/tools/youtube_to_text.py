# tools/youtube_to_text.py

import re
import json
import subprocess
import logging
from pathlib import Path
from typing import List, Optional, TypeVar
from fastmcp import FastMCP

T = TypeVar("T", bound="FastMCP")

logger = logging.getLogger(Path(__file__).stem)

FFMPEG_DIR = r""  # Example: r"C:\Program Files\ffmpeg\bin"
PREFERRED_LANGS = ["en", "en-US", "en-GB", "es", "es-419", "es-ES"]

# ----------------- Helpers -----------------
def get_video_id(url: str) -> str:
    url = url.strip()
    if not url:
        raise ValueError("Empty URL")

    m = re.search(r"youtu\.be/([A-Za-z0-9_\-]{6,})", url)
    if m:
        return m.group(1)

    m = re.search(r"[?&]v=([A-Za-z0-9_\-]{6,})", url)
    if m:
        return m.group(1)

    raise ValueError("Invalid YouTube URL")


def _normalize_entries_to_dicts(entries: List[object]) -> List[dict]:
    """Normaliza los objetos de subtítulos a dicts con {start, duration, text}."""
    normalized = []
    for e in entries:
        if isinstance(e, dict):
            normalized.append({
                "start": float(e.get("start", 0.0)),
                "duration": float(e.get("duration", 0.0)),
                "text": e.get("text", "")
            })
        else:
            start = getattr(e, "start", 0.0)
            duration = getattr(e, "duration", 0.0)
            text = getattr(e, "text", "")
            normalized.append({
                "start": float(start) if start is not None else 0.0,
                "duration": float(duration) if duration is not None else 0.0,
                "text": text or ""
            })
    return normalized


def fetch_subtitles(video_id: str, prefer_langs: Optional[List[str]] = None) -> Optional[List[dict]]:
    """Intenta obtener subtítulos de YouTube si están disponibles."""
    prefer_langs = prefer_langs or ["en", "es"]
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except Exception as e:
        logger.warning("No se pudo importar youtube_transcript_api: %s", e)
        return None

    try:
        api = YouTubeTranscriptApi()
        transcripts = api.list(video_id)
        langs = [getattr(tr, "language_code", "?") for tr in transcripts]
        logger.debug("Idiomas disponibles: %s", langs)

        for tr in transcripts:
            if getattr(tr, "language_code", "") in prefer_langs:
                raw = tr.fetch()
                return _normalize_entries_to_dicts(raw)

        if transcripts:
            raw = transcripts[0].fetch()
            return _normalize_entries_to_dicts(raw)

    except Exception as e:
        logger.warning("No se pudo obtener subtítulos: %s", e)
        return None

    return None


# ----------------- Output management -----------------
def _get_outputs_dir() -> Path:
    """Carpeta base para outputs del proyecto (dentro de mymcpserver/outputs)."""
    return Path(__file__).resolve().parents[1] / "outputs"

def _get_transcripts_dir() -> Path:
    out_dir = _get_outputs_dir() / "transcripts"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir

def _get_audio_dir() -> Path:
    out_dir = _get_outputs_dir() / "audio"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir

def save_txt_and_json_from_subtitles(entries: list[dict], video_id: str) -> tuple[Path, Path]:
    out_dir = _get_transcripts_dir()
    txt_path = out_dir / f"transcript_{video_id}.txt"
    json_path = out_dir / f"transcript_{video_id}.json"

    txt_path.write_text("\n".join(e["text"] for e in entries), encoding="utf-8")
    json_path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.info("💾 Guardado transcript en %s y %s", txt_path, json_path)
    return txt_path, json_path

def save_txt_and_json_from_text(text: str, video_id: str) -> tuple[Path, Path]:
    out_dir = _get_transcripts_dir()
    txt_path = out_dir / f"transcript_{video_id}.txt"
    json_path = out_dir / f"transcript_{video_id}.json"

    txt_path.write_text(text, encoding="utf-8")
    json_path.write_text(
        json.dumps([{"index": 0, "text": text}], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    logger.info("💾 Guardado transcript en %s y %s", txt_path, json_path)
    return txt_path, json_path


# ----------------- Audio + Whisper -----------------
def download_audio(url: str, video_id: str, out_ext: str = "mp3") -> Path:
    """Descarga el audio de un video de YouTube usando yt-dlp."""
    out_dir = _get_audio_dir()
    out_file = out_dir / f"{video_id}.{out_ext}"

    cmd = ["yt-dlp", "-x", "--audio-format", out_ext, "-o", str(out_file), url]
    if FFMPEG_DIR:
        cmd.extend(["--ffmpeg-location", FFMPEG_DIR])

    logger.debug("Ejecutando comando: %s", " ".join(cmd))
    subprocess.run(cmd, check=True)

    return out_file


def transcribe_with_whisper(path: Path, model_name: str = "base") -> str:
    """Transcribe un archivo de audio usando OpenAI Whisper."""
    import whisper
    model = whisper.load_model(model_name)
    result = model.transcribe(str(path))
    return result.get("text", "").strip()


# ----------------- Pipeline -----------------
def youtube_to_text(url: str, force_whisper: bool = False) -> str:
    video_id = get_video_id(url)

    if not force_whisper:
        logger.info("Buscando subtítulos...")
        subs = fetch_subtitles(video_id, PREFERRED_LANGS)
        if subs:
            logger.info("✅ Subtítulos encontrados.")
            save_txt_and_json_from_subtitles(subs, video_id)
            return " ".join(e["text"] for e in subs)

    logger.warning("⚠️ No hay subtítulos. Descargando audio y transcribiendo con Whisper...")
    audio = download_audio(url, video_id, out_ext="mp3")
    text = transcribe_with_whisper(audio, model_name="base")
    try:
        audio.unlink(missing_ok=True)
    except Exception as e:
        logger.debug("No se pudo borrar el archivo de audio temporal: %s", e)
    save_txt_and_json_from_text(text, video_id)
    return text


# ----------------- MCP integration -----------------
def register(mcp: T):
    logger.debug("Registrando tool youtube_transcript")

    @mcp.tool(tags=["public"])
    def youtube_transcript(url: str) -> dict:
        """
        Extrae el transcript de un video de YouTube.
        - Si hay subtítulos disponibles, los usa.
        - Si no hay, descarga el audio y transcribe con Whisper.
        
        Devuelve un diccionario con:
        - "text": transcript en texto plano
        - "txt_path": ruta del archivo .txt generado
        - "json_path": ruta del archivo .json generado
        """
        text = youtube_to_text(url, force_whisper=False)

        video_id = get_video_id(url)
        txt_path = _get_transcripts_dir() / f"transcript_{video_id}.txt"
        json_path = _get_transcripts_dir() / f"transcript_{video_id}.json"

        return {
            "text": text,
            "txt_path": str(txt_path),
            "json_path": str(json_path),
        }



# ----------------- CLI -----------------
if __name__ == "__main__":
    url = ""
    while not url:
        url = input("Enter YouTube URL: ").strip()
        if not url:
            logger.warning("⚠️ Please paste a valid YouTube URL.")

    try:
        result = youtube_to_text(url, force_whisper=False)
        print("\n--- TRANSCRIPT ---\n")
        print(result)
    except subprocess.CalledProcessError as e:
        logger.error("❌ yt-dlp/FFmpeg error: %s", e)
    except Exception as e:
        logger.error("❌ Error: %s", e)
