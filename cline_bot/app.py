"""Application composition root.

Wires the services together, registers the Telegram handlers and starts
long polling. This is the only module that knows about all the others.
"""

import json
import logging
import sys
from pathlib import Path

from telegram.ext import Application, CommandHandler, MessageHandler, filters

from .authorization import AuthorizationPolicy
from .autostart import AutostartError, install_if_missing
from .cline_client import ClineClient
from .config import AppConfig, ConfigurationError, load_config
from .handlers import BotHandlers
from .logging_setup import configure_logging
from .polling import run_polling_forever
from .session_registry import SessionRegistry

LOGGER = logging.getLogger(__name__)

EXIT_CODE_INVALID_CONFIGURATION = 2

COMMAND_ROUTES = {
    "start": "start",
    "help": "start",
    "pair": "pair",
    "cd": "change_directory",
    "mode": "change_mode",
    "model": "change_model",
    "new": "start_new_session",
    "status": "show_status",
    "stop": "stop_running_task",
    "history": "show_history",
    "shell": "run_shell_command",
    "screen": "take_screenshot",
    "type": "type_on_screen",
    "key": "press_key",
    "approve": "toggle_auto_approve",
}


def build_handlers(config: AppConfig) -> BotHandlers:
    """Create the handler object with all of its collaborators."""
    return BotHandlers(
        config=config,
        policy=AuthorizationPolicy(config),
        sessions=SessionRegistry(config),
        cline=ClineClient(
            command=config.clite_command,
            run_timeout_seconds=config.run_timeout_seconds,
            thinking_level=config.thinking_level,
        ),
    )


def register_handlers(application: Application, bot: BotHandlers) -> None:
    """Attach every command and the catch-all prompt handler."""
    for command, method_name in COMMAND_ROUTES.items():
        application.add_handler(CommandHandler(command, getattr(bot, method_name)))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_prompt)
    )


def register_error_handler(application: Application) -> None:
    def log_error(update, context) -> None:
        LOGGER.error("Update failed: %s", context.error, exc_info=context.error)

    application.add_error_handler(log_error)


def main() -> None:
    config = load_config_or_exit()
    configure_logging(config.log_file_path)
    install_autostart_if_needed()

    application = Application.builder().token(config.telegram_bot_token).build()
    register_handlers(application, build_handlers(config))
    register_error_handler(application)

    LOGGER.info("Bot started, polling for updates")
    run_polling_forever(application, drop_pending_updates=True)


def install_autostart_if_needed() -> None:
    """Register the logon task on first start so the bot survives a reboot.

    A failure here is logged but never fatal: the bot is still usable when it
    was started by hand, and autostart is a convenience rather than a
    requirement for correctness.
    """
    entry_point = Path(__file__).resolve().parent.parent / "run_bot.py"
    try:
        was_installed = install_if_missing(entry_point)
    except (AutostartError, OSError) as error:
        LOGGER.warning("Could not install autostart: %s", error)
        return

    if was_installed:
        LOGGER.info("Autostart installed; the bot will start on every logon")
    else:
        LOGGER.info("Autostart already installed")


def load_config_or_exit() -> AppConfig:
    """Load the configuration, reporting problems without a stack trace."""
    try:
        return load_config()
    except (ConfigurationError, json.JSONDecodeError) as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        raise SystemExit(EXIT_CODE_INVALID_CONFIGURATION)
