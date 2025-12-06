# youtube_search.py
""" Search for the most revelavent youtube video or videos on a given topic. """

import logging
from typing import TypeVar
from pathlib import Path
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



def get_most_relevant_video_url(query:str, maxResults:int=1)->str | list:
    """ Search YouTube for the most relevant video(s) on a given topic.
    Args:
        query (str): The search query/topic.
        maxResults (int): The maximum number of results to return (1-50).
    Returns:
        str | list: The URL of the most relevant video, or a list of URLs if maxResults > 1.
    """
    if maxResults < 1:
        maxResults = 1
    elif maxResults > 50:
        maxResults = 50

    API_KEY = "AIzaSyAGsxSmpJdV-oJomUvFeQrowZqo2rHA0gw"

    youtube = build("youtube", "v3", developerKey=API_KEY)

    request = youtube.search().list(         # pylint: disable=no-member
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

def get_video_info(query:str, maxResults:int=1, order="viewCount" ):
    """ Search YouTube for videos on a given topic and return video information.
        Args:
            query (str): The search query/topic.
            maxResults (int): The maximum number of results to return (1-50).
            order (str): The order of the results. Options: "date", "rating", "relevance", 
                            "title", "videoCount", "viewCount"."
        Returns:
            dict: The response from the YouTube API containing video information.       
    """

    if maxResults < 1:
        maxResults = 1
    elif maxResults > 50:
        maxResults = 50

    if order not in ["date", "rating", "relevance", "title", "videoCount"]:
        order="viewCount"

    API_KEY = ""

    youtube = build("youtube", "v3", developerKey=API_KEY)

    request = youtube.search().list(         # pylint: disable=no-member
        part="snippet",
        q=query,
        type="video",
        maxResults=maxResults,
        order=order
    )

    response = request.execute()
    return response



def register(mcp: T):
    """Register math tools with MCPServer."""
    logger.info("Registering math tools")
    mcp.tool(tags=["public", "api"])(get_most_relevant_video_url)
    mcp.tool(tags=["public", "api"])(get_video_info)

# ----------------- CLI -----------------
if __name__ == "__main__":
    """ CLI for testing the YouTube search tool. """
    # Change this to url = "" to prompt for input.
    qry = "Python Optional Tutorial"
    while not qry:
        qry = input("Enter YouTube Search query: ").strip()
        if not qry:
            logger.warning("⚠️ Please paste a valid search query.")
    try:
        urls = get_most_relevant_video_url(qry, 50)
        print(f"Most Relevant Youtube Videos are:\n{urls}")

        results = get_video_info(qry, maxResults=5, order="date")
        print(f"Video Info by date:\n{results}")
 
    except Exception as e:
        logger.error("❌ Error: %s", e)
