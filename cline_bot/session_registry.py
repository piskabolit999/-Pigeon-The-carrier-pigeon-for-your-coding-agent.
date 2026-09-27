"""Per-chat runtime state.

Each Telegram chat owns its working directory, agent mode, model and a durable
conversation log, so several people or projects can share one bot process.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from .cline_client import ClineRun
from .config import AppConfig
from .conversation_log import ConversationLog


@dataclass
class ChatSession:
    """Mutable state of a single Telegram conversation."""

    working_directory: str
    agent_mode: str
    is_auto_approved: bool
    conversation: ConversationLog
    model_id: Optional[str] = None
    is_busy: bool = False
    adopted_session: Optional[str] = None
    adopted_transcript: str = field(default="", repr=False)
    running_process: Optional[ClineRun] = field(default=None, repr=False)
    running_output_task: Optional[object] = field(default=None, repr=False)

    @property
    def has_running_task(self) -> bool:
        return self.running_process is not None or self.running_output_task is not None

    def remember_turn(self, prompt: str, answer: str) -> None:
        """Store one exchange so the next prompt can carry the context."""
        self.conversation.append(prompt, answer)

    def adopt_session(self, session_id: str, transcript: str) -> None:
        """Adopt a stored session transcript as the start of this chat."""
        self.adopted_session = session_id
        self.adopted_transcript = transcript

    def forget_history(self) -> None:
        """Drop the remembered conversation and any adopted transcript."""
        self.conversation.clear()
        self.adopted_session = None
        self.adopted_transcript = ""

    def build_prompt_with_context(self, prompt: str) -> str:
        """Prefix the prompt with the adopted transcript and the history."""
        parts = [
            part
            for part in (self.adopted_transcript, self.conversation.render())
            if part
        ]
        if not parts:
            return prompt
        return "\n\n".join(parts) + f"\n\n[next request]\n{prompt}"

    def describe(self) -> str:
        """Render the state for the /status command."""
        return "\n".join(
            [
                "Current session state",
                f"directory: {self.working_directory}",
                f"agent mode: {self.agent_mode}",
                f"model: {self.model_id or 'provider default'}",
                f"remembered turns: {len(self.conversation.turns())}",
                f"adopted session: {self.adopted_session or 'none'}",
                f"auto approve: {self.is_auto_approved}",
                f"busy: {self.is_busy}",
            ]
        )


class SessionRegistry:
    """Creates and stores the session of every known chat."""

    def __init__(self, config: AppConfig, history_directory: Optional[Path] = None):
        self._config = config
        self._history_directory = history_directory or config.log_file_path.parent
        self._sessions: Dict[int, ChatSession] = {}

    def get_or_create(self, chat_id: int) -> ChatSession:
        session = self._sessions.get(chat_id)
        if session is None:
            session = ChatSession(
                working_directory=self._config.default_working_directory,
                agent_mode=self._config.default_agent_mode,
                is_auto_approved=self._config.auto_approve_tools,
                conversation=ConversationLog(self._history_directory, chat_id),
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
