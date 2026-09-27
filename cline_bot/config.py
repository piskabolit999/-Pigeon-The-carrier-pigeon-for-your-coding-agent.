"""Application configuration.

Values come from `config.json` in the project root. The bot token may also be
supplied through the `CLINE_BOT_TOKEN` environment variable so that secrets
never have to be written to disk.
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE_PATH = PROJECT_ROOT / "config.json"
TOKEN_ENVIRONMENT_VARIABLE = "CLINE_BOT_TOKEN"

SUPPORTED_AGENT_MODES = ("plan", "act")
SUPPORTED_THINKING_LEVELS = ("none", "low", "medium", "high", "xhigh")
DEFAULT_AGENT_MODE = "act"
DEFAULT_THINKING_LEVEL = "medium"
DEFAULT_RUN_TIMEOUT_SECONDS = 3600
DEFAULT_SHELL_TIMEOUT_SECONDS = 60
DEFAULT_MAX_MESSAGE_LENGTH = 3500
DEFAULT_CLITE_COMMAND = "clite"


class ConfigurationError(Exception):
    """Raised when the application cannot start with the given configuration."""


@dataclass(frozen=True)
class AppConfig:
    """Validated application settings."""

    telegram_bot_token: str
    allowed_chat_ids: List[int] = field(default_factory=list)
    pairing_code: Optional[str] = None
    default_working_directory: str = str(Path.home())
    default_agent_mode: str = DEFAULT_AGENT_MODE
    auto_approve_tools: bool = True
    run_timeout_seconds: int = DEFAULT_RUN_TIMEOUT_SECONDS
    shell_timeout_seconds: int = DEFAULT_SHELL_TIMEOUT_SECONDS
    thinking_level: str = DEFAULT_THINKING_LEVEL
    clite_command: str = DEFAULT_CLITE_COMMAND
    max_message_length: int = DEFAULT_MAX_MESSAGE_LENGTH
    log_file_path: Path = PROJECT_ROOT / "logs" / "bot.log"

    def __post_init__(self) -> None:
        self._validate()

    def _validate(self) -> None:
        if not self.telegram_bot_token:
            raise ConfigurationError(
                "Telegram bot token is missing. Set 'telegram_bot_token' in "
                f"{CONFIG_FILE_PATH.name} or the {TOKEN_ENVIRONMENT_VARIABLE} "
                "environment variable."
            )
        if self.default_agent_mode not in SUPPORTED_AGENT_MODES:
            raise ConfigurationError(
                f"default_agent_mode must be one of {SUPPORTED_AGENT_MODES}."
            )
        if self.thinking_level not in SUPPORTED_THINKING_LEVELS:
            raise ConfigurationError(
                f"thinking_level must be one of {SUPPORTED_THINKING_LEVELS}."
            )

    def save_allowed_chat_ids(self) -> None:
        """Persist the whitelist back to disk so it survives a restart."""
        raw_config = _read_raw_config()
        raw_config["allowed_chat_ids"] = self.allowed_chat_ids
        CONFIG_FILE_PATH.write_text(
            json.dumps(raw_config, indent=2, ensure_ascii=False), encoding="utf-8"
        )


def _read_raw_config() -> Dict[str, Any]:
    """Read config.json, reporting a parse error with a usable message.

    A malformed file is a common mistake, and the default JSON error does not
    say which file is broken or that the bot cannot start because of it.
    """
    if not CONFIG_FILE_PATH.exists():
        return {}
    raw_text = CONFIG_FILE_PATH.read_text(encoding="utf-8")
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as error:
        raise ConfigurationError(
            f"{CONFIG_FILE_PATH.name} is not valid JSON: {error}. "
            f"Check for a missing comma, a trailing comma, or an unquoted "
            f"placeholder such as [allowed_chat_ids]."
        ) from error
    if not isinstance(parsed, dict):
        raise ConfigurationError(
            f"{CONFIG_FILE_PATH.name} must contain a JSON object at the top level."
        )
    return parsed


def _resolve_token(raw_config: Dict[str, Any]) -> str:
    environment_token = os.environ.get(TOKEN_ENVIRONMENT_VARIABLE, "").strip()
    if environment_token:
        return environment_token
    return str(raw_config.get("telegram_bot_token", "")).strip()


def load_config() -> AppConfig:
    """Build the application configuration from disk and the environment."""
    raw_config = _read_raw_config()
    return AppConfig(
        telegram_bot_token=_resolve_token(raw_config),
        allowed_chat_ids=list(raw_config.get("allowed_chat_ids") or []),
        pairing_code=raw_config.get("pairing_code"),
        default_working_directory=raw_config.get(
            "default_cwd", str(Path.home())
        ),
        default_agent_mode=raw_config.get("default_mode", DEFAULT_AGENT_MODE),
        auto_approve_tools=bool(raw_config.get("auto_approve", True)),
        run_timeout_seconds=int(
            raw_config.get("timeout_seconds", DEFAULT_RUN_TIMEOUT_SECONDS)
        ),
        shell_timeout_seconds=int(
            raw_config.get("shell_timeout_seconds", DEFAULT_SHELL_TIMEOUT_SECONDS)
        ),
        thinking_level=raw_config.get("thinking_level", DEFAULT_THINKING_LEVEL),
        clite_command=raw_config.get("clite_command", DEFAULT_CLITE_COMMAND),
        max_message_length=int(
            raw_config.get("max_message_length", DEFAULT_MAX_MESSAGE_LENGTH)
        ),
        log_file_path=PROJECT_ROOT
        / raw_config.get("log_file", str(Path("logs") / "bot.log")),
    )
