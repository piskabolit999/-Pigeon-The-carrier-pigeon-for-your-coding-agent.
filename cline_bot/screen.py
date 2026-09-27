"""Screen capture and synthetic input for the `/screen` commands.

The bot can photograph the desktop and send it to the chat, and can type or
press keys. Both work by running short PowerShell snippets, which avoids
adding a screenshot or automation dependency to the project.
"""

import asyncio
import logging
import os
import subprocess
import tempfile
from pathlib import Path

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
SCREENSHOT_TIMEOUT_SECONDS = 30
INPUT_TIMEOUT_SECONDS = 15
SCREENSHOT_QUALITY = 80

LOGGER = logging.getLogger(__name__)


class ScreenError(Exception):
    """Raised when a screen action cannot be performed."""


CAPTURE_SCREENSHOT_SCRIPT = """
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
$bounds = [System.Windows.Forms.SystemInformation]::VirtualScreen
$bitmap = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
$bitmap.Save($env:PIGEON_SCREENSHOT_PATH, [System.Drawing.Imaging.ImageFormat]::Png)
$graphics.Dispose()
$bitmap.Dispose()
Write-Output "saved"
"""

ACTIVATE_FOREGROUND_SCRIPT = """
$signature = @'
[DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
'@
Add-Type -MemberDefinition $signature -Name Native -Namespace Screen
$handle = [Screen.Native]::GetForegroundWindow()
if ($handle -eq [IntPtr]::Zero) { Write-Error "no foreground window"; exit 1 }
[void][Screen.Native]::SetForegroundWindow($handle)
Write-Output "focused"
"""

SEND_KEYS_SCRIPT = """
Add-Type -AssemblyName System.Windows.Forms
if ([string]::IsNullOrEmpty($env:PIGEON_KEYS)) { Write-Error "no keys given"; exit 1 }
[System.Windows.Forms.SendKeys]::SendWait($env:PIGEON_KEYS)
Write-Output "sent"
"""


def _run_powershell(script: str, environment: dict, timeout: int) -> str:
    process = subprocess.Popen(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy", "Bypass",
            "-Command", script,
        ],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=CREATE_NO_WINDOW,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        raise ScreenError(f"the screen action timed out after {timeout}s")

    output = (stdout.decode("utf-8", "replace") + stderr.decode("utf-8", "replace")).strip()
    if process.returncode != 0:
        # Swallowing this made a failing keystroke look like a delivered one.
        raise ScreenError(output or "the screen action failed")
    return output


async def capture_screenshot() -> Path:
    """Grab the whole virtual desktop into a temporary PNG."""
    target = Path(tempfile.gettempdir()) / "pigeon-screen.png"
    if target.exists():
        target.unlink()

    environment = os.environ.copy()
    environment["PIGEON_SCREENSHOT_PATH"] = str(target)
    await asyncio.to_thread(
        _run_powershell, CAPTURE_SCREENSHOT_SCRIPT, environment, SCREENSHOT_TIMEOUT_SECONDS
    )
    if not target.exists():
        raise ScreenError("the screenshot was not created")
    return target


async def send_keys(keys: str) -> None:
    """Send already-escaped keys to the focused window.

    The string is passed through unchanged: `/key` already wraps the key in
    braces, and SendKeys needs those. Escaping again here would turn `{ENTER}`
    into a literal `{{ENTER}}` and type the word instead of pressing it.
    """
    environment = os.environ.copy()
    environment["PIGEON_KEYS"] = keys
    # A background process has no foreground window of its own, so the
    # desktop may be locked or another session may hold focus. Re-asserting
    # the foreground window first makes the keystroke land where the user sees it.
    await asyncio.to_thread(
        _run_powershell, ACTIVATE_FOREGROUND_SCRIPT, os.environ.copy(), INPUT_TIMEOUT_SECONDS
    )
    await asyncio.to_thread(
        _run_powershell, SEND_KEYS_SCRIPT, environment, INPUT_TIMEOUT_SECONDS
    )


SUPPORTED_KEYS = (
    "ENTER", "TAB", "ESC", "SPACE", "BACKSPACE", "DELETE", "HOME", "END",
    "UP", "DOWN", "LEFT", "RIGHT", "F5", "CTRL+A", "CTRL+C", "CTRL+V",
)


def build_key_sequence(key_name: str) -> str:
    """Return the SendKeys sequence for a supported key.

    The allowlist matters: SendKeys understands {LAUNCH}, {SLEEP} and other
    directives, so an unrestricted string from the chat would be able to do
    more than press a key.
    """
    normalized = key_name.strip().upper()
    if normalized not in SUPPORTED_KEYS:
        raise ScreenError(
            f"Unsupported key {key_name}. Try: {', '.join(SUPPORTED_KEYS[:6])}..."
        )
    return f"{{{normalized}}}"


def escape_for_send_keys(text: str) -> str:
    """Escape characters that SendKeys treats as special."""
    special = {"+": "{+}", "^": "{^}", "%": "{%}", "~": "{~}"}
    return "".join(special.get(character, character) for character in text)
