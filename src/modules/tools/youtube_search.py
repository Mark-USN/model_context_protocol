# math_tools.py

import logging
from typing import TypeVar
from pathlib import Path
# from youtubesearchpython import VideosSearch
from fastmcp import FastMCP
from googleapiclient.discovery import build


T = TypeVar("T", bound=FastMCP)

# -----------------------------
# Logging setup
# -----------------------------
logging.basicConfig(
    # level=logging.DEBUG if settings.debug else logging.INFO,
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)-8s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(Path(__file__).stem)



def get_most_relevant_video_url(query, maxResults=1)->str | list:

    if maxResults < 1:
        maxResults = 1
    elif maxResults > 50:
        maxResults = 50

    API_KEY = ""

    youtube = build("youtube", "v3", developerKey=API_KEY)

    request = youtube.search().list(
        part="snippet",
        q=query,
        type="video",
        maxResults=maxResults,
        order="relevance"
    )

    response = request.execute()

    # Extract URLs
    video_urls = [
        f"https://www.youtube.com/watch?v={item['id']['videoId']}"
        for item in response["items"]
    ]
    
    return video_urls[0] if maxResults == 1 else video_urls

def get_video_info(query, maxResults=1, order="viewCount" ):

    if maxResults < 1:
        maxResults = 1
    elif maxResults > 50:
        maxResults = 50

    if order not in ["date", "rating", "relevance", "title", "videoCount"]:
        order="viewCount"

    API_KEY = "AIzaSyAGsxSmpJdV-oJomUvFeQrowZqo2rHA0gw"

    youtube = build("youtube", "v3", developerKey=API_KEY)

    request = youtube.search().list(
        part="snippet",
        q=query,
        type="video",
        maxResults=maxResults,
        order=order
    )

    response = request.execute()
    return response

    # Extract URLs
    # video_urls = [
    #     f"https://www.youtube.com/watch?v={item['id']['videoId']}"
    #     for item in response["items"]
    # ]
    # if maxResults == 1:
    #     return video_url[0]

    # for url in video_urls:
    #     return video_urls



def register(mcp: T):
    """Register math tools with MCPServer."""
    logger.info("Registering math tools")
    mcp.tool(tags=["public", "api"])(get_most_popular_video_url)

# ----------------- CLI -----------------
if __name__ == "__main__":
    """ CLI for testing the YouTube search tool. """
    # Change this to url = "" to prompt for input.
    query = "Python Optional Tutorial"
    while not query:
        query = input("Enter YouTube Search query: ").strip()
        if not query:
            logger.warning("⚠️ Please paste a valid search query.")
    try:
        urls = get_most_relevant_video_url(query, 50)
        print(f"Most Relevant Youtube Videos are:\n{urls}")

        results = get_video_info(query, maxResults=5, order="date")
        print(f"Video Info by date:\n{results}")
 
    except Exception as e:
        logger.error("❌ Error: %s", e)
