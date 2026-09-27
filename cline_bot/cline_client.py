"""Thin wrapper around the Cline CLI executable.

The module isolates every detail of how the external process is located and
launched, so the Telegram handlers only deal with prompts and output lines.
"""

import asyncio
import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

from .text_utils import strip_ansi_codes

HISTORY_PAGE_SIZE = 5
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
TERMINATION_GRACE_SECONDS = 5
MAX_OUTPUT_CHARACTERS = 400_000
OUTPUT_ENCODING = "utf-8"
TRUNCATION_NOTICE = "[output truncated: limit reached]"
DISABLED_THINKING_LEVEL = "none"
HISTORY_SCAN_LIMIT = 50
MAX_TRANSCRIPT_EXCERPTS = 25
INCLUDED_ROLES = ("user", "assistant")

LOGGER = logging.getLogger(__name__)


class ClineClientError(Exception):
    """Raised when the Cline CLI cannot be located or inspected."""


class ClineRun:
    """A single running Cline CLI process.

    Wraps the process so it can be terminated reliably. Cancelling the asyncio
    task that awaits the output does NOT stop the child process, so the process
    handle is kept here and killed explicitly on cancellation.
    """

    def __init__(self, process) -> None:
        self._process = process

    @property
    def is_running(self) -> bool:
        return self._process.returncode is None

    async def collect_output(self) -> "tuple[list[str], int]":
        """Drain stdout until the process exits and return (lines, exit code)."""
        collected: List[str] = []
        total_characters = 0
        has_truncated = False

        try:
            async for raw_line in self._process.stdout:
                line = strip_ansi_codes(raw_line.decode(OUTPUT_ENCODING, "replace"))
                line = line.rstrip()
                if not line.strip():
                    continue
                # Bound the buffer so a runaway agent cannot exhaust memory.
                total_characters += len(line)
                if total_characters > MAX_OUTPUT_CHARACTERS:
                    collected.append(TRUNCATION_NOTICE)
                    has_truncated = True
                    break
                collected.append(line)
        except asyncio.CancelledError:
            # The reader is torn down mid-await, so close the transport
            # explicitly to avoid leaking the pipe handle.
            self._close_stream()
            raise

        # Stop reading once the limit is hit. Without this the process keeps
        # running and blocks forever on a full pipe, so wait() never returns.
        if has_truncated:
            self.terminate()

        return collected, await self._process.wait()

    def _close_stream(self) -> None:
        """Release the stdout pipe, ignoring an already closed stream."""
        if self._process.stdout is None:
            return
        try:
            self._process.stdout.close()
        except (OSError, RuntimeError) as error:
            LOGGER.debug("Could not close the output stream: %s", error)

    def terminate(self) -> None:
        """Kill the process tree, because clite spawns node child processes."""
        if not self.is_running:
            return
        self._kill_process_tree()

    def _kill_process_tree(self) -> None:
        """Terminate the process and its children on Windows."""
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(self._process.pid)],
                capture_output=True,
                timeout=TERMINATION_GRACE_SECONDS,
                creationflags=CREATE_NO_WINDOW,
            )
        except (subprocess.SubprocessError, OSError) as error:
            LOGGER.warning("taskkill failed, falling back to terminate: %s", error)
            self._process.terminate()



class ClineClient:
    """Runs prompts through the Cline CLI and reads its session history."""

    def __init__(self, command: str, run_timeout_seconds: int, thinking_level: str):
        self._launcher = self._resolve_launcher(command)
        self._run_timeout_seconds = run_timeout_seconds
        self._thinking_level = thinking_level

    @staticmethod
    def _resolve_launcher(command: str) -> List[str]:
        """Return the argv prefix that starts the CLI without a shell.

        The npm shim `clite.cmd` forwards its arguments through `cmd.exe`,
        which re-encodes them using the console code page. That mangles emoji
        and non-Latin text. Invoking the underlying Node entry point directly
        keeps the arguments as UTF-8 and avoids a shell layer entirely.
        """
        node_entry = ClineClient._find_node_entry(command)
        if node_entry:
            node = shutil.which("node") or "node"
            return [node, str(node_entry)]

        executable = ClineClient._find_executable(command)
        if executable is None:
            raise ClineClientError(
                f"Cannot find '{command}'. Install Cline CLI with "
                "'npm install -g @cline/cli' or set 'clite_command'."
            )
        if executable.lower().endswith((".cmd", ".bat")):
            return [os.environ.get("COMSPEC", "cmd.exe"), "/c", executable]
        return [executable]

    @staticmethod
    def _find_node_entry(command: str) -> Optional[Path]:
        """Locate the CLI entry script inside the global npm package."""
        npm_root = Path(os.environ.get("APPDATA", "")) / "npm" / "node_modules"
        candidate = npm_root / "@cline" / "cli" / "bin" / command
        return candidate if candidate.is_file() else None

    @staticmethod
    def _find_executable(command: str) -> Optional[str]:
        if os.path.isabs(command) and Path(command).exists():
            return command
        discovered = shutil.which(command)
        if discovered:
            return discovered
        npm_shim = Path(os.environ.get("APPDATA", "")) / "npm" / f"{command}.cmd"
        return str(npm_shim) if npm_shim.exists() else None


    def build_command(
        self,
        prompt: str,
        working_directory: str,
        agent_mode: str,
        is_auto_approved: bool,
        model_id: Optional[str] = None,
    ) -> List[str]:
        """Compose the CLI argument list for a single run.

        `--id` is deliberately not used. Resuming a session makes the CLI
        switch to its interactive TUI, which aborts with "interactive mode
        requires a TTY" whenever stdin and stdout are pipes, and a bot is
        always pipes. Conversation continuity is handled by prepending the
        earlier turns to the prompt instead.
        """
        arguments = self._launcher + [
            prompt,
            "--cwd", working_directory,
            "--timeout", str(self._run_timeout_seconds),
            "--auto-approve", "true" if is_auto_approved else "false",
        ]
        if agent_mode == "plan":
            arguments.append("--plan")
        # Reasoning models reject `--thinking none`, so the flag is omitted to
        # let the provider choose rather than failing the whole run.
        if self._thinking_level != DISABLED_THINKING_LEVEL:
            arguments += ["--thinking", self._thinking_level]
        # Omitting the flag keeps whatever the provider has configured, so the
        # bot never silently overrides a model the user chose in the CLI.
        if model_id:
            arguments += ["--model", model_id]
        return arguments

    def _build_environment(self) -> dict:
        """Disable colors and prompts so the output stays machine readable."""
        environment = os.environ.copy()
        environment.update({"TERM": "dumb", "NO_COLOR": "1"})
        environment.pop("WT_SESSION", None)
        return environment

    async def start_prompt(
        self,
        prompt: str,
        working_directory: str,
        agent_mode: str,
        is_auto_approved: bool,
        model_id: Optional[str] = None,
    ) -> ClineRun:
        """Spawn the CLI for a prompt and return a handle to the run."""
        arguments = self.build_command(
            prompt, working_directory, agent_mode, is_auto_approved, model_id
        )
        process = await asyncio.create_subprocess_exec(
            *arguments,
            cwd=working_directory,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            stdin=asyncio.subprocess.DEVNULL,
            env=self._build_environment(),
            creationflags=CREATE_NO_WINDOW,
        )
        return ClineRun(process)

    def terminate(self, run: ClineRun) -> None:
        """Stop a running CLI process, ignoring an already finished one."""
        run.terminate()

    def fetch_recent_sessions(self, limit: int = HISTORY_PAGE_SIZE) -> List[dict]:
        """Return the most recent CLI sessions, newest first."""
        result = subprocess.run(
            self._launcher + ["history", "--json", "--limit", str(limit)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            creationflags=CREATE_NO_WINDOW,
        )
        return self._parse_history(result.stdout)

    @staticmethod
    def _parse_history(raw_output: str) -> List[dict]:
        try:
            sessions = json.loads(raw_output or "[]")
        except json.JSONDecodeError as error:
            LOGGER.warning("Could not parse session history: %s", error)
            return []
        return sessions if isinstance(sessions, list) else []

    def session_context(self, session_id: str) -> str:
        """Summarise a stored session so its work can be continued.

        The CLI can only resume a session interactively, which a bot cannot
        do. Reading the saved transcript instead lets a chat pick up where a
        desktop or terminal session left off.

        Only prose blocks are kept. Most stored messages are tool calls and
        their results, so taking the last N messages would return almost no
        readable context; taking the last N text blocks does.
        """
        messages = self.fetch_session_messages(session_id)
        excerpts = [
            f"[{message['role']}] {text}"
            for message in messages
            if message.get("role") in INCLUDED_ROLES
            for text in [self._message_text(message)]
            if text.strip()
        ]
        if not excerpts:
            return ""
        transcript = "\n\n".join(excerpts[-MAX_TRANSCRIPT_EXCERPTS:])
        return (
            f"The following is the transcript of an earlier session "
            f"({session_id}) on this project. Continue its work.\n\n{transcript}"
        )

    def fetch_session_messages(self, session_id: str) -> List[dict]:
        """Load the saved message list of a session, empty when unreadable."""
        messages_path = self._find_messages_path(session_id)
        if messages_path is None:
            return []
        try:
            payload = json.loads(messages_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            LOGGER.warning("Could not read session %s: %s", session_id, error)
            return []
        messages = payload.get("messages") if isinstance(payload, dict) else None
        return messages if isinstance(messages, list) else []

    def _find_messages_path(self, session_id: str) -> Optional[Path]:
        """Locate the transcript of a session inside the CLI data directory."""
        for session in self.fetch_recent_sessions(HISTORY_SCAN_LIMIT):
            if session.get("sessionId") != session_id:
                continue
            recorded_path = session.get("messagesPath")
            if recorded_path and Path(recorded_path).is_file():
                return Path(recorded_path)
        for candidate in self._sessions_directory().glob(f"*{session_id}*.json"):
            return candidate
        return None

    def _sessions_directory(self) -> Path:
        return self._data_directory / "sessions"

    @property
    def _data_directory(self) -> Path:
        override = os.environ.get("CLINE_DATA_DIR")
        if override:
            return Path(override)
        return Path.home() / ".cline" / "data"

    @staticmethod
    def _message_text(message: dict) -> str:
        """Return the plain text of a message regardless of its content shape."""
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = [
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            ]
            return "".join(parts)
        return ""
