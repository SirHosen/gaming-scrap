#!/usr/bin/env python3
"""
Lightweight logging + colourised console output.
Logs go to both stdout (coloured) and a file (plain text).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from nestfetch.config import LOG_FILENAME, OUTPUT_DIR

# ── ANSI colours ───────────────────────────────────────────────────────────
class Colours:
    GREEN   = "\033[92m"
    CYAN    = "\033[96m"
    YELLOW  = "\033[93m"
    RED     = "\033[91m"
    WHITE   = "\033[97m"
    GREY    = "\033[90m"
    BOLD    = "\033[1m"
    RESET   = "\033[0m"
    UNDERLINE = "\033[4m"


class _ColourFormatter(logging.Formatter):
    """Colourise log levels on the console stream only."""

    LEVEL_COLOURS = {
        logging.DEBUG: Colours.GREY,
        logging.INFO: Colours.CYAN,
        logging.WARNING: Colours.YELLOW,
        logging.ERROR: Colours.RED,
        logging.CRITICAL: Colours.BOLD + Colours.RED,
    }

    def format(self, record: logging.LogRecord) -> str:
        colour = self.LEVEL_COLOURS.get(record.levelno, "")
        record.msg = f"{colour}{record.msg}{Colours.RESET}"
        return super().format(record)


def setup_logger(name: str = "nestfetch", level: int = logging.INFO) -> logging.Logger:
    """Configure a logger that writes to both console (coloured) and file."""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if logger.handlers:                       # avoid duplicate handlers on re-import
        return logger

    fmt = "%(asctime)s │ %(levelname)-8s │ %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    # ── Console handler ────────────────────────────────────────────────
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(_ColourFormatter(fmt, datefmt=datefmt))
    logger.addHandler(console)

    # ── File handler ───────────────────────────────────────────────────
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(
        Path(OUTPUT_DIR) / LOG_FILENAME, encoding="utf-8"
    )
    file_handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
    logger.addHandler(file_handler)

    return logger


# Module-level singleton for convenience
log = setup_logger()
