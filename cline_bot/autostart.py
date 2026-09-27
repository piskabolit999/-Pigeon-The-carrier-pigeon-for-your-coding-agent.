"""Registers the bot to start automatically with Windows.

The bot installs itself into Task Scheduler so the user does not have to run a
separate setup script. The task runs `pythonw.exe`, which has no console window,
and is configured to restart on failure.
"""

import logging
import subprocess
import sys
from pathlib import Path

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
TASK_NAME = "ClineTelegramBot"


class AutostartError(Exception):
    """Raised when the autostart task cannot be installed."""


LOGGER = logging.getLogger(__name__)


def build_registration_command(python_executable: str, entry_point: Path) -> list:
    """Compose the schtasks arguments that create the logon task.

    `/IT` runs the task only while the user is logged on, which is what
    Telegram polling needs: there is no user session to attach to otherwise.
    """
    return [
        "schtasks", "/Create",
        "/F",
        "/SC", "ONLOGON",
        "/TN", TASK_NAME,
        "/TR", f'"{python_executable}" "{entry_point}"',
        "/RL", "LIMITED",
        "/IT",
    ]


def find_windowless_python() -> str:
    """Return pythonw.exe, which runs without a console window."""
    interpreter_directory = Path(sys.executable).parent
    candidate = interpreter_directory / "pythonw.exe"
    if not candidate.exists():
        raise AutostartError(f"pythonw.exe not found next to {sys.executable}")
    return str(candidate)


def is_task_installed() -> bool:
    """Report whether the autostart task already exists."""
    result = subprocess.run(
        ["schtasks", "/Query", "/TN", TASK_NAME],
        capture_output=True,
        creationflags=CREATE_NO_WINDOW,
    )
    return result.returncode == 0


def install_autostart(entry_point: Path) -> None:
    """Create the logon task, replacing any previous installation."""
    python_executable = find_windowless_python()
    command = build_registration_command(python_executable, entry_point)
    LOGGER.info("Installing autostart task: %s", " ".join(command))

    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise AutostartError(
            f"schtasks failed ({result.returncode}): {result.stderr.strip()}"
        )
    LOGGER.info("Autostart task %r installed", TASK_NAME)


def install_if_missing(entry_point: Path) -> bool:
    """Install the autostart task unless it is already present.

    Returns True when a new task was created.
    """
    if is_task_installed():
        LOGGER.info("Autostart task %r already present", TASK_NAME)
        return False
    install_autostart(entry_point)
    return True
