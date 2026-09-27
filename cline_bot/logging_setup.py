"""Logging setup: one stream to the console, one rotating file on disk.

Every log record passes through a redacting filter first. The HTTP client
logs full request URLs, and every Telegram URL embeds the bot token, so an
unfiltered log file ends up holding a live credential. It is a real risk: a
user committed such a log and published the token.
"""

import logging
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
MAX_LOG_BYTES = 2 * 1024 * 1024
LOG_BACKUP_COUNT = 3
REDACTED = "***REDACTED***"

# Matches the secret half of `.../bot<token>/...` in any logged URL.
TELEGRAM_TOKEN_IN_URL = re.compile(r"(/bot)[^/\s]+")


class SecretRedactingFilter(logging.Filter):
    """Strip credentials from log records before they are written."""

    def filter(self, record: logging.LogRecord) -> bool:
        # Render the %-arguments first: the token often arrives as an
        # argument, so redacting the raw format string would miss it and
        # discarding the arguments would leave the raw placeholders in the log.
        rendered_message = record.getMessage()
        record.msg = TELEGRAM_TOKEN_IN_URL.sub(rf"\1{REDACTED}", rendered_message)
        record.args = ()
        return True


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
    redacting_filter = SecretRedactingFilter()

    for handler in (file_handler, stream_handler):
        handler.addFilter(redacting_filter)

    logging.basicConfig(
        level=logging.INFO,
        format=LOG_FORMAT,
        handlers=[stream_handler, file_handler],
    )
    # The HTTP client logs through the root logger, so the filter has to sit
    # on the logger itself as well to catch records before any handler.
    logging.getLogger().addFilter(redacting_filter)

