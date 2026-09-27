"""Registers the bot to start automatically with Windows.

The bot installs itself into Task Scheduler on first run, so the user never has
to run a separate setup script. The task runs `pythonw.exe`, which has no
console window, and restarts automatically if the process dies.

PowerShell's `Register-ScheduledTask` is used instead of `schtasks` because
`schtasks /Create` demands elevation even for a per-user logon task, while the
cmdlet succeeds with the rights a normal user already has.
"""

import logging
import subprocess
import sys
from pathlib import Path

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
TASK_NAME = "ClineTelegramBot"
TASK_DESCRIPTION = "Background Telegram bridge to Cline CLI"
RESTART_COUNT = 999
RESTART_INTERVAL_MINUTES = 1
REGISTRATION_TIMEOUT_SECONDS = 60


class AutostartError(Exception):
    """Raised when the autostart task cannot be installed."""


LOGGER = logging.getLogger(__name__)


def build_registration_script(python_executable: str, entry_point: Path) -> str:
    """Compose the PowerShell script that creates the logon task.

    `-LogonType Interactive` is required: the bot polls Telegram, which only
    works while the user session exists.

    Backslashes are not escaped, because PowerShell single-quoted strings
    treat a backslash as a literal character. Escaping them would corrupt the
    path, since the entry point lives at `C:\\...`.
    """
    return (
        f"$action = New-ScheduledTaskAction "
        f"-Execute '{python_executable}' -Argument '\"{entry_point}\"'; "
        f"$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME; "
        f"$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries "
        f"-DontStopIfGoingOnBatteries -StartWhenAvailable "
        f"-RestartCount {RESTART_COUNT} "
        f"-RestartInterval (New-TimeSpan -Minutes {RESTART_INTERVAL_MINUTES}) "
        f"-ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew; "
        f"$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME "
        f"-LogonType Interactive -RunLevel Limited; "
        f"Register-ScheduledTask -TaskName '{TASK_NAME}' -Action $action "
        f"-Trigger $trigger -Settings $settings -Principal $principal "
        f"-Description '{TASK_DESCRIPTION}' -Force | Out-Null"
    )


def find_windowless_python() -> str:
    """Return pythonw.exe, which runs without a console window."""
    candidate = Path(sys.executable).parent / "pythonw.exe"
    if not candidate.exists():
        raise AutostartError(f"pythonw.exe not found next to {sys.executable}")
    return str(candidate)


def _run_powershell(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy", "Bypass",
            "-Command", script,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=REGISTRATION_TIMEOUT_SECONDS,
        creationflags=CREATE_NO_WINDOW,
    )


def is_task_installed() -> bool:
    """Report whether the autostart task already exists."""
    result = _run_powershell(
        f"if (Get-ScheduledTask -TaskName '{TASK_NAME}' "
        f"-ErrorAction SilentlyContinue) {{ exit 0 }} else {{ exit 1 }}"
    )
    return result.returncode == 0


def install_autostart(entry_point: Path) -> None:
    """Create the logon task, replacing any previous installation."""
    python_executable = find_windowless_python()
    script = build_registration_script(python_executable, entry_point)
    LOGGER.info("Installing autostart task %r", TASK_NAME)

    result = _run_powershell(script)
    if result.returncode != 0:
        raise AutostartError(
            f"task registration failed ({result.returncode}): "
            f"{result.stderr.strip() or result.stdout.strip()}"
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
