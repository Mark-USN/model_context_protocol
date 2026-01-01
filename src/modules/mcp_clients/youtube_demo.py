"""
YouTube demo and transcript helpers for UniversalClient.

Extracted from UniversalClient to keep the client class focused on MCP mechanics.
"""

import time
import logging
from typing import List
from datetime import timedelta

logger = logging.getLogger(__name__)


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
        client.yt_search = "mcp long job tools"

    while not client.yt_search:
        client.yt_search = input("\033[1mEnter Search for YouTube: \033[0m").strip()
        if not client.yt_search:
            logger.warning("⚠️ Please enter a valid search term.")

    # youtube_search
    print(
        "\n\nExecuting 'get_most_relevant_video_url' tool "
        f"with parameters {client.yt_search}, {client.MAX_SEARCH_RESULTS}.",
    )

    yt_url_result = await client.call_tool(
        "get_most_relevant_video_url",
        {"query": client.yt_search, "maxResults": client.MAX_SEARCH_RESULTS},
    )

    urls = yt_url_result.data
    if isinstance(urls, str):
        print(f"\nMost relevant YouTube URL: {urls}")
    elif isinstance(urls, List):
        print("\nMost relevant YouTube URLs:\n")
        for url in urls:
            print(f"- {url}")

    await get_all_transcripts(client, urls)


# ---------------------------------------------------------------------
# YouTube Transcript Methods (Subtitles/Captions)
# ---------------------------------------------------------------------

async def get_a_json_transcript(client, url: str) -> None:
    """Get transcripts for a given YouTube URL using youtube_json."""
    print(
        "\n\nExecuting 'youtube_json' tool "
        f"with parameters {url}",
    )
    start = time.perf_counter()

    json_result = await client.call_tool("youtube_json", {"url": url})

    elapsed = int(time.perf_counter() - start)
    video_id = client.get_video_id(url)

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

    text_result = await client.call_tool("youtube_text", {"url": url})
    
    elapsed = int(time.perf_counter() - start)
    video_id = client.get_video_id(url)

    txt_path = client.base_output_dir() / f"{video_id}.txt"
    with open(txt_path, "w", encoding="utf-8") as txt_file:
        txt_file.write(str(text_result.data))

    print(f"\nResult of youtube_text tool in {txt_path}")
    print(f"The transcription of {video_id}.txt took {timedelta(seconds=elapsed)}")


# ---------------------------------------------------------------------
# YouTube Audio Transcript Methods
# ---------------------------------------------------------------------

async def get_an_audio_json_transcript(client, url: str) -> None:
    """Get transcripts for a given YouTube URL using youtube_audio_json_async."""
    tool = "youtube_audio_json_async"
   
    token = client.token()  

    if token is None:
        print(
            f"\n\nExecuting '{tool}' tool "
            f"to transcribe {url}",
        )
    else:
        print(
            f"\n\nExecuting '{tool}' tool with token:\n"
            f" {token}\n"
            f" to transcribe url: {url}",
        )


    args = {"url": url}
    if token is not None:
        args["token"] = token

    start = time.perf_counter()
    json_result = await client.call_tools_polite(tool, args)
    elapsed = int(time.perf_counter() - start)

    video_id = client.get_video_id(url)

    json_path = client.base_output_dir() / f"{video_id}_audio.json"
    with open(json_path, "w", encoding="utf-8") as json_file:
        json_file.write(str(json_result.data['result']))

    print(f"\nResult of {tool} in {json_path}\n")
    print(f"The transcription of {video_id}_audio.json took {timedelta(seconds=elapsed)}")


async def get_an_audio_text_transcript(client, url: str) -> None:
    """Get transcripts for a given YouTube URL using youtube_audio_text_async."""
    tool = "youtube_audio_text_async"

    token = client.token()  

    if token is None:
        print(f"\n\nExecuting '{tool}' tool to transcribe {url}")
    else:
        print(
            f"\n\nExecuting '{tool}' tool with token:\n"
            f" {token}\n"
            f" to transcribe url: {url}",
        )

    args = {"url": url}
    if token is not None:
        args["token"] = token

    start = time.perf_counter()
    text_result = await client.call_tools_polite(tool, args)
    elapsed = int(time.perf_counter() - start)
    

    video_id = client.get_video_id(url)

    txt_path = client.base_output_dir() / f"{video_id}_audio.txt"
    with open(txt_path, "w", encoding="utf-8") as txt_file:
        txt_file.write(str(text_result.data['result']))

    print(f"\nResult of {tool} in {txt_path}")
    print(f"The transcription of {video_id}_audio.txt took {timedelta(seconds=elapsed)}")

# ---------------------------------------------------------------------
# Main function to get transcripts cycling through all tool types for
# multiple URLs
# ---------------------------------------------------------------------
async def get_all_transcripts(client, urls: str | List) -> None:
    """Get transcripts for a URL or list of URLs (rotates tool types)."""
    # If a token is returned, use it in the audio tools.
    await client.get_token()

    if isinstance(urls, List):
        for idx, url in enumerate(urls):
            match idx % 4:
                case 0:
                    await get_a_json_transcript(client, url)
                case 1:
                    await get_an_audio_text_transcript(client, url)
                case 2:
                    await get_a_text_transcript(client, url)
                case 3:
                    await get_an_audio_json_transcript(client, url)
    else:
        await get_a_text_transcript(client, urls)

