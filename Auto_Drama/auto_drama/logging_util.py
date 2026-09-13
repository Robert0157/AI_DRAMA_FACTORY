# -*- coding: utf-8 -*-
"""Unified logging: console + rotating file. English comments per project rule."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_configured = False
_FORMAT = "%(asctime)s [AUTO-DRAMA] %(levelname)s  %(name)s  %(message)s"
_DATE = "%Y-%m-%d %H:%M:%S"


def setup_logging(log_path: Path | None = None, level: int = logging.INFO) -> logging.Logger:
    """Configure root Auto_Drama logger once; returns the 'auto_drama' logger."""
    global _configured
    logger = logging.getLogger("auto_drama")
    if _configured:
        return logger
    logger.setLevel(level)
    fmt = logging.Formatter(_FORMAT, datefmt=_DATE)

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    logger.addHandler(console)

    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(str(log_path), maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    logger.propagate = False
    _configured = True
    return logger


def get_logger() -> logging.Logger:
    """Get the shared logger, configuring with defaults if not yet set up."""
    return logging.getLogger("auto_drama")
