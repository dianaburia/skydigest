"""Shared logging configuration for CLI runners and scheduled jobs."""

import logging


def setup_logging(level: int = logging.INFO) -> None:
    """Configure the root logger for one process.

    Applies a compact format for our own loggers and silences httpx's
    INFO logger, which would otherwise print full request URLs (and any
    secrets in query strings — happened once with the NASA API key).
    """
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
