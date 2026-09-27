"""Telegram command handlers.

Handlers stay thin: they validate input, delegate to the service layer and
format the reply. All process execution lives in `ClineClient`.
"""

import asyncio
import logging
from pathlib import Path
from typing import List, Optional

from telegram import Update
from telegram.constants import ChatAction
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from .authorization import AuthorizationPolicy
from .cline_client import ClineClient, ClineRun
from .config import AppConfig
from .screen import ScreenError, capture_screenshot, escape_for_send_keys, send_keys
from .session_registry import ChatSession, SessionRegistry
from .text_utils import split_into_chunks

LOGGER = logging.getLogger(__name__)

STATUS_REFRESH_SECONDS = 3
HISTORY_PROMPT_LENGTH = 70
SESSION_LIST_SIZE = 8
PROMPT_HEADER_LENGTH = 800

HELP_TEXT = (
    "🤖 *Telegram → Cline CLI bridge*\n\n"
    "Send any text and it is executed as a prompt by the Cline CLI.\n\n"
    "Commands:\n"
    "/cd <path> — change the working directory\n"
    "/mode plan|act — switch the agent mode\n"
    "/model <id> — switch the model, /model default follows the provider\n"
    "/new — start a fresh Cline session\n"
    "/status — show the current state\n"
    "/stop — cancel the running task\n"
    "/history — list recent Cline sessions\n"
    "/shell <command> — run a PowerShell command\n"
    "/screen — send a screenshot of the desktop\n"
    "/type <text> — type into the focused window\n"
    "/key <ENTER|TAB|ESC> — send a keystroke\n"
    "/approve on|off — toggle automatic tool approval"
)


class BotHandlers:
    """Binds the application services to the Telegram update handlers."""

    def __init__(
        self,
        config: AppConfig,
        policy: AuthorizationPolicy,
        sessions: SessionRegistry,
        cline: ClineClient,
    ) -> None:
        self._config = config
        self._policy = policy
        self._sessions = sessions
        self._cline = cline

    # ----------------------------------------------------------------- #
    # Authorization
    # ----------------------------------------------------------------- #
    async def _resolve_session(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> Optional[ChatSession]:
        """Return the chat session, or None when access must be denied."""
        chat = update.effective_chat
        message_text = (update.message.text or "") if update.message else ""
        is_authorized, is_pairing = self._policy.check(chat.id, message_text)

        if is_pairing:
            await self._reply_pairing_result(update, is_authorized)
            return None
        if not is_authorized:
            LOGGER.warning("Rejected chat %s", chat.id)
            await update.effective_message.reply_text(
                self._policy.unauthorized_message()
            )
            return None

        return self._sessions.get_or_create(chat.id)

    async def _reply_pairing_result(self, update: Update, is_authorized: bool) -> None:
        if is_authorized:
            await update.effective_message.reply_text("✅ Paired.")
            return
        await update.effective_message.reply_text(
            self._policy.pair_error_message() or "Pairing failed."
        )

    # ----------------------------------------------------------------- #
    # Commands
    # ----------------------------------------------------------------- #
    async def pair(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Authorize a new chat using the configured pairing code."""
        await self._resolve_session(update, context)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await self._resolve_session(update, context) is None:
            return
        await update.effective_message.reply_text(HELP_TEXT, parse_mode="Markdown")

    async def change_directory(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        session = await self._resolve_session(update, context)
        if session is None:
            return
        if not context.args:
            await update.effective_message.reply_text(
                f"Current: {session.working_directory}"
            )
            return

        target = self._build_directory_path(session, " ".join(context.args))
        if not target.is_dir():
            await update.effective_message.reply_text(f"❌ Not a directory: {target}")
            return

        session.working_directory = str(target.resolve())
        await update.effective_message.reply_text(f"📂 {session.working_directory}")

    @staticmethod
    def _build_directory_path(session: ChatSession, raw_path: str) -> Path:
        candidate = Path(raw_path).expanduser()
        if candidate.is_absolute():
            return candidate
        return Path(session.working_directory) / candidate

    async def change_mode(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        session = await self._resolve_session(update, context)
        if session is None:
            return
        requested_mode = context.args[0].lower() if context.args else None
        if requested_mode in ("plan", "act") and requested_mode != session.agent_mode:
            session.agent_mode = requested_mode
        await update.effective_message.reply_text(f"🧩 agent mode: {session.agent_mode}")

    async def change_model(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        session = await self._resolve_session(update, context)
        if session is None:
            return
        if not context.args:
            await update.effective_message.reply_text(
                f"Current model: {session.model_id or 'provider default'}\n\n"
                "Usage: /model <model-id>, or /model default to follow the "
                "provider setting."
            )
            return

        requested_model = " ".join(context.args)
        session.model_id = None if requested_model == "default" else requested_model
        # The CLI binds a model to a session, so a new one is required.
        await update.effective_message.reply_text(
            f"🧠 model: {session.model_id or 'provider default'}"
        )

    async def take_screenshot(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send the current desktop to the chat."""
        if await self._resolve_session(update, context) is None:
            return
        await update.effective_message.reply_text("📸 Capturing…")
        try:
            screenshot = await capture_screenshot()
        except ScreenError as error:
            await update.effective_message.reply_text(f"❌ {error}")
            return
        await update.effective_message.reply_photo(
            photo=open(screenshot, "rb"), caption="🖥 Current screen"
        )

    async def type_on_screen(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Type text into whatever window currently has focus."""
        if await self._resolve_session(update, context) is None:
            return
        if not context.args:
            await update.effective_message.reply_text("Usage: /type <text>")
            return
        text = escape_for_send_keys(" ".join(context.args))
        try:
            await send_keys(text)
        except ScreenError as error:
            await update.effective_message.reply_text(f"❌ {error}")
            return
        await update.effective_message.reply_text("⌨️ Typed into the focused window.")

    async def press_key(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send a keystroke, for example ENTER or TAB."""
        if await self._resolve_session(update, context) is None:
            return
        if not context.args:
            await update.effective_message.reply_text("Usage: /key <ENTER|TAB|ESC>")
            return
        key_name = context.args[0].upper()
        try:
            await send_keys(f"{{{key_name}}}")
        except ScreenError as error:
            await update.effective_message.reply_text(f"❌ {error}")
            return
        await update.effective_message.reply_text(f"🔘 Sent {key_name}.")

    async def start_new_session(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        session = await self._resolve_session(update, context)
        if session is None:
            return
        session.forget_history()
        await update.effective_message.reply_text("🆕 The next prompt starts fresh.")

    async def adopt_session(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Continue from a session that already exists on this machine."""
        session = await self._resolve_session(update, context)
        if session is None:
            return
        if not context.args:
            await update.effective_message.reply_text(
                "Usage: /use <session-id>. Find ids with /sessions."
            )
            return

        requested_id = context.args[0]
        transcript = self._cline.session_context(requested_id)
        if not transcript:
            await update.effective_message.reply_text(
                f"❌ Could not read session {requested_id}."
            )
            return

        session.adopt_session(requested_id, transcript)
        await update.effective_message.reply_text(
            f"🪢 Continuing from {requested_id}. The next prompt picks it up."
        )

    async def show_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        session = await self._resolve_session(update, context)
        if session is None:
            return
        self._sessions.resolve_working_directory(session)
        await update.effective_message.reply_text(session.describe())

    async def stop_running_task(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        session = await self._resolve_session(update, context)
        if session is None:
            return
        if not session.has_running_task:
            await update.effective_message.reply_text("Nothing is running.")
            return
        self._cancel_running_process(session)
        await update.effective_message.reply_text("🛑 Cancelled.")

    async def show_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await self._resolve_session(update, context) is None:
            return
        sessions = self._cline.fetch_recent_sessions(SESSION_LIST_SIZE)
        if not sessions:
            await update.effective_message.reply_text("No sessions found.")
            return
        await self._reply_to_chat(
            update,
            "🗂 Recent sessions — continue one with /use <id>\n"
            + "\n".join(self._describe_history(sessions)),
        )

    @staticmethod
    def _describe_history(sessions: List[dict]) -> List[str]:
        return [
            f"• {entry.get('sessionId')} [{entry.get('source')}] "
            f"{str(entry.get('prompt') or '')[:HISTORY_PROMPT_LENGTH]}"
            for entry in sessions
        ]

    async def toggle_auto_approve(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        session = await self._resolve_session(update, context)
        if session is None:
            return
        requested_state = context.args[0].lower() if context.args else None
        if requested_state in ("on", "off"):
            session.is_auto_approved = requested_state == "on"
        await update.effective_message.reply_text(
            f"auto approve: {session.is_auto_approved}"
        )

    async def run_shell_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        session = await self._resolve_session(update, context)
        if session is None:
            return
        if not context.args:
            await update.effective_message.reply_text("Usage: /shell <command>")
            return

        command_text = " ".join(context.args)
        await update.effective_message.send_chat_action(ChatAction.TYPING)
        output = await self._execute_shell_command(session, command_text)
        await self._reply_to_chat(update, f"$ {command_text}\n\n{output}")

    async def _execute_shell_command(
        self, session: ChatSession, command_text: str
    ) -> str:
        """Run a shell command in the chat directory with a hard timeout."""
        process = await asyncio.create_subprocess_shell(
            command_text,
            cwd=self._sessions.resolve_working_directory(session),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            stdout, _ = await asyncio.wait_for(
                process.communicate(), timeout=self._config.shell_timeout_seconds
            )
        except asyncio.TimeoutError:
            process.kill()
            return f"[timed out after {self._config.shell_timeout_seconds}s]"
        return stdout.decode("utf-8", errors="replace").strip() or "(no output)"

    # ----------------------------------------------------------------- #
    # Prompt execution
    # ----------------------------------------------------------------- #
    async def handle_prompt(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        session = await self._resolve_session(update, context)
        if session is None:
            return
        prompt = (update.message.text or "").strip()
        if not prompt:
            return
        if session.is_busy:
            await update.effective_message.reply_text(
                "⏳ A task is already running. Use /stop to cancel it."
            )
            return
        await self._execute_prompt(update, session, prompt)

    async def _execute_prompt(
        self, update: Update, session: ChatSession, prompt: str
    ) -> None:
        session.is_busy = True
        working_directory = self._sessions.resolve_working_directory(session)
        header_message = await update.effective_message.reply_text(
            f"🚀 Started\n📂 {working_directory}\n"
            f"🧩 mode: {session.agent_mode}\n\n{prompt[:PROMPT_HEADER_LENGTH]}"
        )
        status_message = await update.effective_message.reply_text("⏳ Working…")

        try:
            output_lines, exit_code = await self._run_with_progress(
                status_message, session, prompt, working_directory
            )
        except asyncio.CancelledError:
            await self._reply_to_message(header_message, "🛑 Cancelled.")
            raise
        finally:
            session.is_busy = False
            session.running_process = None
            await self._delete_message(status_message)

        report = self._build_report(output_lines, exit_code)
        await self._reply_to_message(header_message, report)
        session.remember_turn(prompt, report)

    async def _run_with_progress(
        self,
        status_message,
        session: ChatSession,
        prompt: str,
        working_directory: str,
    ) -> "tuple[list[str], int]":
        """Run the prompt and keep the status message alive while it works."""
        run = await self._cline.start_prompt(
            session.build_prompt_with_context(prompt),
            working_directory,
            session.agent_mode,
            session.is_auto_approved,
            session.model_id,
        )
        session.running_process = run
        output_task = asyncio.create_task(run.collect_output())
        session.running_output_task = output_task

        while not output_task.done():
            finished, _ = await asyncio.wait(
                {output_task}, timeout=STATUS_REFRESH_SECONDS
            )
            if not finished:
                await self._refresh_status_message(status_message)

        return output_task.result()

    @staticmethod
    async def _refresh_status_message(status_message) -> None:
        """Best-effort edit; a failure here must not abort the run."""
        try:
            await status_message.edit_text("⏳ Working on the Cline CLI…")
        except TelegramError as error:
            LOGGER.debug("Could not refresh the status message: %s", error)

    @staticmethod
    def _build_report(output_lines: List[str], exit_code: int) -> str:
        body = "\n".join(output_lines) or "(no output)"
        suffix = f"\n\n— exit code: {exit_code}" if exit_code != 0 else ""
        return f"✅ Done{suffix}\n\n{body}"

    def _cancel_running_process(self, session: ChatSession) -> None:
        """Stop the CLI process tree, then release the awaiting task.

        Both steps are required: cancelling the task alone leaves the spawned
        process running, and killing the process alone leaves the task pending.
        """
        run = session.running_process
        output_task = session.running_output_task

        if isinstance(run, ClineRun):
            run.terminate()
        if output_task is not None and not output_task.done():
            output_task.cancel()

        session.running_process = None
        session.running_output_task = None

    # ----------------------------------------------------------------- #
    # Reply helpers
    # ----------------------------------------------------------------- #
    async def _reply_to_message(self, message, text: str) -> None:
        for chunk in split_into_chunks(text, self._config.max_message_length):
            await self._safe_reply(message, chunk)

    async def _reply_to_chat(self, update: Update, text: str) -> None:
        for chunk in split_into_chunks(text, self._config.max_message_length):
            await self._safe_reply(update.effective_message, chunk)

    @staticmethod
    async def _safe_reply(message, text: str) -> None:
        try:
            await message.reply_text(text)
        except TelegramError as error:
            LOGGER.warning("Could not deliver a message: %s", error)

    @staticmethod
    async def _delete_message(message) -> None:
        try:
            await message.delete()
        except TelegramError as error:
            LOGGER.debug("Could not delete the status message: %s", error)


