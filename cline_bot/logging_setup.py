"""Logging setup: one stream to the console, one rotating file on disk."""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
MAX_LOG_BYTES = 2 * 1024 * 1024
LOG_BACKUP_COUNT = 3


def configure_logging(log_file_path: Path) -> None:
    """Send every log record to stdout and to a rotating file."""
    log_file_path.parent.mkdir(parents=True, exist_ok=True)

    file_handler = RotatingFileHandler(
        log_file_path,
        maxBytes=MAX_LOG_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    stream_handler = logging.StreamHandler(sys.stdout)

    logging.basicConfig(
        level=logging.INFO,
        format=LOG_FORMAT,
        handlers=[stream_handler, file_handler],
    )
