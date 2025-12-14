#./src/debug_stub.py

import signal
import logging
from pathlib import Path

import modules.tools.youtube_transcript as yt_to_text
import modules.tools.youtube_audio_transcript as yt_fm_audio
import modules.tools.youtube_search as yt_search
from modules.utils.api_keys import api_vault


def debug_stub():
    """ A simple debug stub to test importing the youtube_to_text tool.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger = logging.getLogger(Path(__file__).stem)
    try:
        # api_keys = api_vault()
        # google_key = api_keys.get_value("GOOGLE_KEY")
        # print(f"The value for Google_Key is: {google_key}")

        # yt_to_text.main()
        yt_fm_audio.main()
        # yt_search.main()
#        logger.info(f"Successfully imported tool: youtube_to_text")

    except Exception as e:
        logger.error(f"Failed to import YouSearch Tool: %s", e)
#        logger.error(f"Failed to import YouTubeToText Tool: %s", e)
        # logger.error(f"api_key threw an exception: %s", e)


if __name__ == "__main__":
    debug_stub()
