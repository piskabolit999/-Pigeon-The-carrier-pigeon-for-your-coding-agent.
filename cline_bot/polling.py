"""Starts and stops long polling in a way that works on Python 3.12+.

`Application.run_polling` calls `asyncio.get_event_loop()`, which raises
`RuntimeError` on Python 3.12 and newer because an event loop is no longer
created implicitly in the main thread. The polling lifecycle is therefore
driven explicitly here through the asynchronous API.
"""

import asyncio
import logging
import signal

from telegram.ext import Application

SHUTDOWN_SIGNALS = (signal.SIGINT, signal.SIGTERM)
LOGGER = logging.getLogger(__name__)


async def poll_until_stopped(application: Application, drop_pending_updates: bool) -> None:
    """Receive updates until a shutdown signal arrives or the task is cancelled."""
    stop_event = asyncio.Event()
    _install_signal_handlers(stop_event)

    await application.initialize()
    await application.start()
    try:
        await application.updater.start_polling(drop_pending_updates=drop_pending_updates)
        LOGGER.info("Polling for updates")
        await stop_event.wait()
    finally:
        await application.updater.stop()
        await application.stop()
        await application.shutdown()
        LOGGER.info("Polling stopped")


def _install_signal_handlers(stop_event: asyncio.Event) -> None:
    """Ask the loop to stop on Ctrl+C or a service shutdown."""

    def request_stop() -> None:
        stop_event.set()

    for shutdown_signal in SHUTDOWN_SIGNALS:
        try:
            asyncio.get_running_loop().add_signal_handler(shutdown_signal, request_stop)
        except (NotImplementedError, ValueError, AttributeError):
            # Windows does not support add_signal_handler for SIGTERM, and
            # Python < 3.8 has no add_signal_handler at all.
            pass


def run_polling_forever(application: Application, drop_pending_updates: bool = True) -> None:
    """Own the event loop for the lifetime of the bot."""
    try:
        asyncio.run(poll_until_stopped(application, drop_pending_updates))
    except KeyboardInterrupt:
        LOGGER.info("Interrupted by the user")
