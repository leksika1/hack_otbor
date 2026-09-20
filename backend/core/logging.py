"""Logging setup. Never logs API keys or whole session logs."""

from __future__ import annotations

import logging
import sys

__all__ = ["setup_logging"]

_FORMAT = "%(asctime)s %(levelname)-8s %(name)s | %(message)s"
_configured = False


def setup_logging(level: str = "INFO") -> None:
    """Configure root logging once, writing to stdout (container friendly)."""
    global _configured
    if _configured:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_FORMAT))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    _configured = True
