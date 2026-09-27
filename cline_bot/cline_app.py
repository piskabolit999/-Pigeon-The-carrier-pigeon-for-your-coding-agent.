"""Launching and focusing the Cline desktop application.

`/cline` should feel idempotent: it starts the app when it is closed and
brings the existing window forward when it is already open. An optional prompt
is typed into the window so a task can be handed over from the chat.
"""

import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Optional

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
PROCESS_NAME = "cline-app"
LAUNCH_TIMEOUT_SECONDS = 40
LAUNCH_POLL_SECONDS = 1
STARTUP_GRACE_SECONDS = 3
FOCUS_SCRIPT = """
$signature = @'
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
[DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr hWnd);
'@
Add-Type -MemberDefinition $signature -Name Native -Namespace Pigeon
$process = Get-Process -Id $env:PIGEON_PID -ErrorAction SilentlyContinue
if ($null -eq $process) { Write-Error "the Cline window is gone"; exit 1 }
[void][Pigeon.Native]::ShowWindow($process.MainWindowHandle, 9)
[void][Pigeon.Native]::BringWindowToTop($process.MainWindowHandle)
[void][Pigeon.Native]::SetForegroundWindow($process.MainWindowHandle)
Write-Output "focused"
"""

LOGGER = logging.getLogger(__name__)


class ClineAppError(Exception):
    """Raised when the desktop application cannot be started or focused."""


def find_executable() -> Optional[Path]:
    """Locate cline-app.exe next to the Cline data directory."""
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Cline" / "cline-app.exe",
        Path.cwd() / "cline-app.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def find_running_process() -> subprocess.CompletedProcess:
    """Ask tasklist about the desktop application, in CSV for reliable parsing."""
    return subprocess.run(
        [
            "tasklist",
            "/FI", f"IMAGENAME eq {PROCESS_NAME}.exe",
            "/NH", "/FO", "CSV",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
        creationflags=CREATE_NO_WINDOW,
    )


def find_window_process_id() -> Optional[int]:
    """Return the process id of the desktop application.

    CSV output is parsed instead of the column layout, which is padded with
    spaces that vary with the locale and the process name length.
    """
    for line in (find_running_process().stdout or "").splitlines():
        fields = [field.strip().strip('"') for field in line.split(",")]
        if len(fields) >= 2 and fields[0].lower() == f"{PROCESS_NAME}.exe":
            try:
                return int(fields[1])
            except ValueError:
                continue
    return None


def is_running() -> bool:
    """Report whether the desktop application is already open."""
    return find_window_process_id() is not None


def launch(executable: Path) -> None:
    """Start the application and wait until its process appears."""
    subprocess.Popen(
        [str(executable)],
        cwd=str(executable.parent),
        creationflags=CREATE_NO_WINDOW,
    )
    deadline = time.time() + LAUNCH_TIMEOUT_SECONDS
    while time.time() < deadline:
        if is_running():
            time.sleep(STARTUP_GRACE_SECONDS)
            return
        time.sleep(LAUNCH_POLL_SECONDS)
    raise ClineAppError("Cline did not start within the timeout")


def focus(window_process_id: int) -> None:
    """Bring the application window to the front."""
    environment = os.environ.copy()
    environment["PIGEON_PID"] = str(window_process_id)
    result = subprocess.run(
        [
            "powershell", "-NoProfile", "-NonInteractive",
            "-ExecutionPolicy", "Bypass", "-Command", FOCUS_SCRIPT,
        ],
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
        creationflags=CREATE_NO_WINDOW,
    )
    if result.returncode != 0:
        raise ClineAppError(
            (result.stderr or result.stdout or "").strip() or "could not focus Cline"
        )


def describe_state() -> str:
    """Return what `/cline` will do, for the reply to the chat."""
    return "Cline is already open" if is_running() else "Cline is not running"
