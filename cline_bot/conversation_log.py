"""Persistent per-chat conversation history.

The Cline CLI can only resume a session interactively, which a bot cannot do,
so every run starts a fresh CLI session. Continuity is rebuilt by replaying the
previous exchanges into the next prompt instead.

The log lives on disk so a conversation survives a bot restart, and grows only
up to a character budget: replaying an entire long session would eventually
make the prompt unusable.
"""

import json
import logging
from pathlib import Path
from typing import List, Tuple

DEFAULT_HISTORY_BUDGET_CHARACTERS = 24_000
MAX_TURN_ANSWER_CHARACTERS = 2_000

LOGGER = logging.getLogger(__name__)


class ConversationLog:
    """A durable list of (request, answer) pairs for one chat."""

    def __init__(
        self,
        directory: Path,
        chat_id: int,
        budget_characters: int = DEFAULT_HISTORY_BUDGET_CHARACTERS,
    ) -> None:
        self._path = directory / f"conversation-{chat_id}.jsonl"
        self._budget = budget_characters
        self._turns: List[Tuple[str, str]] = self._load()

    def append(self, request: str, answer: str) -> None:
        """Record one exchange, keeping the file the source of truth."""
        trimmed_answer = answer[-MAX_TURN_ANSWER_CHARACTERS:]
        self._turns.append((request, trimmed_answer))
        self._trim_to_budget()
        self._write()

    def turns(self) -> List[Tuple[str, str]]:
        return list(self._turns)

    def clear(self) -> None:
        self._turns.clear()
        self._path.unlink(missing_ok=True)

    def render(self) -> str:
        """Return the history as a prompt fragment, or an empty string."""
        if not self._turns:
            return ""
        blocks = [
            f"[earlier request]\n{request}\n[earlier answer]\n{answer}"
            for request, answer in self._turns
        ]
        return "\n\n".join(blocks)

    def _trim_to_budget(self) -> None:
        """Drop the oldest turns until the replay fits the budget."""
        while self._render_length() > self._budget and len(self._turns) > 1:
            self._turns.pop(0)

    def _render_length(self) -> int:
        return sum(len(request) + len(answer) for request, answer in self._turns)

    def _load(self) -> List[Tuple[str, str]]:
        if not self._path.is_file():
            return []
        turns: List[Tuple[str, str]] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                turns.append((entry["request"], entry["answer"]))
            except (json.JSONDecodeError, KeyError, TypeError):
                LOGGER.warning("Skipping a damaged history line in %s", self._path)
        return turns

    def _write(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            json.dumps({"request": request, "answer": answer}, ensure_ascii=False)
            for request, answer in self._turns
        ]
        self._path.write_text("\n".join(lines) + "\n", encoding="utf-8")
