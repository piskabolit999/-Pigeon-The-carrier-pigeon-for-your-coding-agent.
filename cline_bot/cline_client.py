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
from typing import List, Optional, Set

from .text_utils import strip_ansi_codes

HISTORY_PAGE_SIZE = 5
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
TERMINATION_GRACE_SECONDS = 5
MAX_OUTPUT_CHARACTERS = 400_000
OUTPUT_ENCODING = "utf-8"
TRUNCATION_NOTICE = "[output truncated: limit reached]"

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

        # Stop reading once the limit is hit. Without this the process keeps
        # running and blocks forever on a full pipe, so wait() never returns.
        if has_truncated:
            self.terminate()

        return collected, await self._process.wait()

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
        """Return the argv prefix that starts the CLI.

        npm installs `clite` as a `.cmd` shim, which Windows cannot execute
        directly, so shims are wrapped in the command interpreter.
        """
        executable = command
        if not (os.path.isabs(command) and Path(command).exists()):
            discovered = shutil.which(command)
            if discovered:
                executable = discovered
            else:
                npm_shim = Path(os.environ.get("APPDATA", "")) / "npm" / f"{command}.cmd"
                if not npm_shim.exists():
                    raise ClineClientError(
                        f"Cannot find '{command}'. Install Cline CLI with "
                        "'npm install -g @cline/cli' or set 'clite_command'."
                    )
                executable = str(npm_shim)

        if executable.lower().endswith((".cmd", ".bat")):
            return [os.environ.get("COMSPEC", "cmd.exe"), "/c", executable]
        return [executable]

    def build_command(
        self,
        prompt: str,
        working_directory: str,
        agent_mode: str,
        is_auto_approved: bool,
        session_id: Optional[str] = None,
    ) -> List[str]:
        """Compose the CLI argument list for a single run."""
        arguments = self._launcher + [
            prompt,
            "--cwd", working_directory,
            "--thinking", self._thinking_level,
            "--timeout", str(self._run_timeout_seconds),
            "--auto-approve", "true" if is_auto_approved else "false",
        ]
        if agent_mode == "plan":
            arguments.append("--plan")
        if session_id:
            arguments += ["--id", session_id]
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
        session_id: Optional[str] = None,
    ) -> ClineRun:
        """Spawn the CLI for a prompt and return a handle to the run."""
        arguments = self.build_command(
            prompt, working_directory, agent_mode, is_auto_approved, session_id
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

    def find_cli_session_started_after(
        self, known_session_ids: Set[str]
    ) -> Optional[str]:
        """Return the CLI session created after the given snapshot.

        Taking a snapshot before the run and diffing afterwards guarantees the
        bot resumes its OWN session. Reading simply "the newest session" would
        hijack an unrelated session, for example one the user started in their
        own terminal at the same time.
        """
        for session in self.fetch_recent_sessions():
            session_id = session.get("sessionId")
            if session.get("source") == "cli" and session_id not in known_session_ids:
                return session_id
        return None

    def snapshot_cli_session_ids(self) -> Set[str]:
        """Record the CLI sessions that already exist."""
        return {
            session["sessionId"]
            for session in self.fetch_recent_sessions()
            if session.get("source") == "cli" and session.get("sessionId")
        }
