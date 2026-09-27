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

SEND_KEYS_SCRIPT = """
Add-Type -AssemblyName System.Windows.Forms
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
    return (stdout.decode("utf-8", "replace") + stderr.decode("utf-8", "replace")).strip()


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
    """Type text or press keys on the focused window."""
    normalized = keys.replace("{", "{{").replace("}", "}}")
    environment = os.environ.copy()
    environment["PIGEON_KEYS"] = normalized
    await asyncio.to_thread(
        _run_powershell, SEND_KEYS_SCRIPT, environment, INPUT_TIMEOUT_SECONDS
    )


def escape_for_send_keys(text: str) -> str:
    """Escape characters that SendKeys treats as special."""
    special = {"+": "{+}", "^": "{^}", "%": "{%}", "~": "{~}"}
    return "".join(special.get(character, character) for character in text)
