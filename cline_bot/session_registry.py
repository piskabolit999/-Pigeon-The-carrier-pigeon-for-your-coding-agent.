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


@dataclass
class ChatSession:
    """Mutable state of a single Telegram conversation."""

    working_directory: str
    agent_mode: str
    is_auto_approved: bool
    is_busy: bool = False
    running_process: Optional[ClineRun] = field(default=None, repr=False)
    running_output_task: Optional[asyncio.Task] = field(default=None, repr=False)
    cline_session_id: Optional[str] = None

    @property
    def has_running_task(self) -> bool:
        return self.running_process is not None or self.running_output_task is not None

    def describe(self) -> str:
        """Render the state for the /status command."""
        return "\n".join(
            [
                "Current session state",
                f"directory: {self.working_directory}",
                f"agent mode: {self.agent_mode}",
                f"cline session: {self.cline_session_id or '(new)'}",
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
