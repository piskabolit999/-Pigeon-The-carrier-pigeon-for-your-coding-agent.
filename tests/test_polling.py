"""Unit tests for the polling lifecycle.

`Application.run_polling` raises `RuntimeError: There is no current event
loop` on Python 3.12+, so Pigeon drives the lifecycle itself. These tests fail
if the bot ever goes back to the library helper.
"""

import asyncio
import unittest
from unittest import mock

from cline_bot.polling import poll_until_stopped, run_polling_forever

SECONDS_TO_WAIT = 0.2


class FakeUpdater:
    def __init__(self) -> None:
        self.was_started = False
        self.was_stopped = False

    async def start_polling(self, drop_pending_updates: bool) -> None:
        self.was_started = True

    async def stop(self) -> None:
        self.was_stopped = True


class FakeApplication:
    def __init__(self) -> None:
        self.updater = FakeUpdater()
        self.was_initialized = False
        self.was_started = False
        self.was_stopped = False
        self.was_shutdown = False

    async def initialize(self) -> None:
        self.was_initialized = True

    async def start(self) -> None:
        self.was_started = True

    async def stop(self) -> None:
        self.was_stopped = True

    async def shutdown(self) -> None:
        self.was_shutdown = True


def run_until_first_output(application: FakeApplication) -> None:
    """Cancel the poll as soon as the updater has started."""

    async def scenario() -> None:
        poll_task = asyncio.create_task(
            poll_until_stopped(application, drop_pending_updates=True)
        )
        while not application.updater.was_started:
            await asyncio.sleep(0.01)
        poll_task.cancel()
        try:
            await poll_task
        except asyncio.CancelledError:
            pass

    asyncio.run(scenario())


class PollUntilStoppedTest(unittest.TestCase):
    def test_initializes_before_polling(self) -> None:
        application = FakeApplication()

        run_until_first_output(application)

        self.assertTrue(application.was_initialized)

    def test_starts_the_updater(self) -> None:
        application = FakeApplication()

        run_until_first_output(application)

        self.assertTrue(application.updater.was_started)

    def test_stops_everything_on_cancellation(self) -> None:
        application = FakeApplication()

        run_until_first_output(application)

        self.assertTrue(application.updater.was_stopped)
        self.assertTrue(application.was_stopped)
        self.assertTrue(application.was_shutdown)


class RunPollingForeverTest(unittest.TestCase):
    def test_swallows_keyboard_interrupt(self) -> None:
        # Ctrl+C during polling must not print a traceback.
        with mock.patch(
            "cline_bot.polling.asyncio.run", side_effect=KeyboardInterrupt
        ):
            with mock.patch("cline_bot.polling.poll_until_stopped"):
                run_polling_forever(FakeApplication())

    def test_does_not_use_the_library_run_polling(self) -> None:
        # Guards against a regression to Application.run_polling, which is
        # broken on Python 3.12 and newer.
        with mock.patch(
            "cline_bot.polling.asyncio.run", side_effect=KeyboardInterrupt
        ):
            application = mock.Mock()
            run_polling_forever(application)
            application.run_polling.assert_not_called()


if __name__ == "__main__":
    unittest.main()
