"""
Structured logger.
- Local / TTY: Rich-formatted coloured output + log file.
- Headless / Docker / cloud: plain timestamped stdout (no ANSI codes)
  so cloud log viewers display clean, searchable lines.
"""

import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from config import settings

_configured = False
_PLAIN_FMT  = logging.Formatter(
    "%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def get_logger(name: str = "crypsavvy") -> logging.Logger:
    global _configured
    logger = logging.getLogger(name)

    if not _configured:
        log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
        logger.setLevel(log_level)

        if sys.stdout.isatty():
            # Interactive terminal — use Rich for coloured output
            from rich.logging import RichHandler
            console_handler = RichHandler(
                rich_tracebacks=True,
                show_path=False,
                markup=True,
            )
            console_handler.setLevel(log_level)
            logger.addHandler(console_handler)
        else:
            # Headless / cloud — plain stdout so cloud logs stay clean
            stream_handler = logging.StreamHandler(sys.stdout)
            stream_handler.setLevel(log_level)
            stream_handler.setFormatter(_PLAIN_FMT)
            logger.addHandler(stream_handler)

        # File handler (skipped in Docker/cloud — logs go to stdout only)
        if sys.stdout.isatty():
            log_path = os.path.abspath(settings.LOG_FILE)
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            file_handler = logging.FileHandler(log_path, encoding="utf-8")
            file_handler.setLevel(log_level)
            file_handler.setFormatter(_PLAIN_FMT)
            logger.addHandler(file_handler)

        _configured = True

    return logger
