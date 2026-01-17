# infra/logging_config.py
from __future__ import annotations

import logging
import sys
from pathlib import Path

DEFAULT_FORMAT = "[%(asctime)s] %(levelname)-8s %(name)s: %(message)s"
DEFAULT_DATEFMT = "%Y-%m-%d %H:%M:%S"


def setup_logging(
    *,
    level: int = logging.INFO,
    fmt: str = DEFAULT_FORMAT,
    datefmt: str = DEFAULT_DATEFMT,
    force: bool = True,
    log_file: str | Path | None = None,
) -> None:
    """
    Configure root logging once for the whole app.

    - Call this exactly once in your *entry point*.
    - In libraries/modules, only use logging.getLogger(__name__).
    """

    # 1) Make stdout UTF-8 so emoji/unicode won't crash on Windows cp1252 consoles.
    #    `errors="replace"` prevents logging from ever throwing if something is still unencodable.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        # Some environments may not support reconfigure; ignore safely.
        pass

    handlers: list[logging.Handler] = []

    # Console handler (now safe because stdout is UTF-8)
    handlers.append(logging.StreamHandler(sys.stdout))

    # 2) Optional: also log to a UTF-8 file (best for services/servers)
    if log_file is not None:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_path, encoding="utf-8"))

    logging.basicConfig(
        level=level,
        format=fmt,
        datefmt=datefmt,
        handlers=handlers,
        force=force,  # True is typically what you want in an app entry point
    )

    # Optional: quiet noisy libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
