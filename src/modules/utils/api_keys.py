""" A simple API keys management class using python-dotenv."""
import os
import dotenv
import logging
from pathlib import Path

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


class api_vault(object):
    """A simple API class example."""

    def __init__(self,keys_file:str='.env'):
        try:
            self.keys_path = dotenv.find_dotenv(keys_file,
                                            raise_error_if_not_found=True)
            if dotenv.load_dotenv(self.keys_path):
                self.keys = dotenv.dotenv_values()

        except Exception as e:
            logger.error(f"Error loading keys from {keys_file}: {e}")
            raise e

    def get_value(self, key:str):
        value = self.keys[key]
        return value



if __name__ == "__main__":
    api = api.api_keys()
    value = api.get_value("GOOGLE_KEY")
    print(f"The value for Google_Key is: {value}")
