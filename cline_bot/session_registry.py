"""Per-chat runtime state.

Each Telegram chat owns its own working directory, agent mode and Cline
session, so several people (or projects) can use the same bot process.
"""

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from .cline_client import ClineRun
from .config import AppConfig

MAX_REMEMBERED_TURNS = 6
MAX_REMEMBERED_ANSWER_CHARACTERS = 2000


@dataclass
class ChatSession:
    """Mutable state of a single Telegram conversation."""

    working_directory: str
    agent_mode: str
    is_auto_approved: bool
    model_id: Optional[str] = None
    is_busy: bool = False
    turns: list = field(default_factory=list, repr=False)
    running_process: Optional[ClineRun] = field(default=None, repr=False)
    running_output_task: Optional[asyncio.Task] = field(default=None, repr=False)

    @property
    def has_running_task(self) -> bool:
        return self.running_process is not None or self.running_output_task is not None

    def remember_turn(self, prompt: str, answer: str) -> None:
        """Store one exchange so the next prompt can carry the context.

        The CLI cannot resume a session without a TTY, so continuity is
        rebuilt by replaying the recent turns into the next prompt.
        """
        trimmed_answer = answer[-MAX_REMEMBERED_ANSWER_CHARACTERS:]
        self.turns.append((prompt, trimmed_answer))
        del self.turns[:-MAX_REMEMBERED_TURNS]

    def forget_turns(self) -> None:
        self.turns.clear()

    def build_prompt_with_context(self, prompt: str) -> str:
        """Prefix the prompt with the earlier turns of this conversation."""
        if not self.turns:
            return prompt
        history = "\n\n".join(
            f"[earlier request]\n{previous}\n[earlier answer]\n{answer}"
            for previous, answer in self.turns
        )
        return f"{history}\n\n[next request]\n{prompt}"

    def describe(self) -> str:
        """Render the state for the /status command."""
        return "\n".join(
            [
                "Current session state",
                f"directory: {self.working_directory}",
                f"agent mode: {self.agent_mode}",
                f"model: {self.model_id or 'provider default'}",
                f"remembered turns: {len(self.turns)}",
                f"auto approve: {self.is_auto_approved}",
                f"busy: {self.is_busy}",
            ]
        )


class SessionRegistry:
    """Creates and stores the session of every known chat."""

    def __init__(self, config: AppConfig):
        self._config = config
        self._sessions: Dict[int, ChatSession] = {}

    def get_or_create(self, chat_id: int) -> ChatSession:
        session = self._sessions.get(chat_id)
        if session is None:
            session = ChatSession(
                working_directory=self._config.default_working_directory,
                agent_mode=self._config.default_agent_mode,
                is_auto_approved=self._config.auto_approve_tools,
            )
            self._sessions[chat_id] = session
        return session

    def resolve_working_directory(self, session: ChatSession) -> str:
        """Return a directory that exists, falling back to the home folder."""
        candidate = Path(session.working_directory)
        if candidate.is_dir():
            return str(candidate)
        fallback = Path(self._config.default_working_directory)
        session.working_directory = str(
            fallback if fallback.is_dir() else Path.home()
        )
        return session.working_directory
