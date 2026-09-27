"""Text helpers shared by the Telegram layer and the Cline CLI client."""

import re
from typing import List

# Cline CLI renders styled terminal output. Telegram cannot display it,
# so every chunk must be plain text.
ANSI_ESCAPE_PATTERN = re.compile(
    r"""
    \x1b\][^\x07]*\x07   # OSC sequences (window titles)
    | \x1b\[[0-9;?]*[a-zA-Z]  # CSI sequences (colors, cursor moves)
    | \x1b[=>]            # keyboard enable/disable
    | \r                 # carriage returns from progress redraws
    """,
    re.VERBOSE,
)

# Telegram rejects messages longer than 4096 characters. The limit is kept
# slightly below that value to leave room for the surrounding markup.
MAX_MESSAGE_LENGTH = 3500


def strip_ansi_codes(text: str) -> str:
    """Remove terminal control sequences from a string."""
    return ANSI_ESCAPE_PATTERN.sub("", text)


def split_into_chunks(text: str, max_length: int = MAX_MESSAGE_LENGTH) -> List[str]:
    """Split text into Telegram-sized chunks, preferring line boundaries.

    Falls back to hard slicing when a single line exceeds the limit, so the
    function never returns a chunk that Telegram would reject.
    """
    if len(text) <= max_length:
        return [text] if text else []

    chunks: List[str] = []
    current_buffer = ""

    for line in text.splitlines(keepends=True):
        if len(current_buffer) + len(line) <= max_length:
            current_buffer += line
            continue

        if current_buffer:
            chunks.append(current_buffer)
            current_buffer = ""

        if len(line) <= max_length:
            current_buffer = line
            continue

        # A single oversized line has no natural boundary, so slice it.
        for start in range(0, len(line), max_length):
            chunks.append(line[start : start + max_length])

    if current_buffer:
        chunks.append(current_buffer)

    return chunks
