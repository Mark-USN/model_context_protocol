# infra/logging_config.py
from __future__ import annotations
import logging
import sys
from typing import Optional

DEFAULT_FORMAT = "[%(asctime)s] %(levelname)-8s %(name)s: %(message)s"
DEFAULT_DATEFMT = "%Y-%m-%d %H:%M:%S"

def setup_logging(
    *,
    level: int = logging.INFO,
    fmt: str = DEFAULT_FORMAT,
    datefmt: str = DEFAULT_DATEFMT,
    force: bool = False,
) -> None:
    """
    Configure root logging once for the whole app.

    - Call this exactly once in your *entry point*.
    - In libraries/modules, only use logging.getLogger(__name__).
    """
    handlers = [logging.StreamHandler(sys.stdout)]
    logging.basicConfig(
        level=level,
        format=fmt,
        datefmt=datefmt,
        handlers=handlers,
        force=force,   # Python 3.8+: override any existing config if True
    )

    # Optional: quiet noisy libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)



