"""Regression tests for output decoding and process termination.

These cover the bug where asyncio subprocesses yield `bytes` while the code
treated the lines as `str`, which crashed every single run.
"""

import asyncio
import sys
import unittest

from cline_bot.cline_client import ClineRun

TERMINATION_POLL_SECONDS = 0.2
TERMINATION_ATTEMPTS = 50
SLEEP_SCRIPT = "import time; time.sleep(60)"


async def start_run(arguments: list) -> ClineRun:
    process = await asyncio.create_subprocess_exec(
        *arguments,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    return ClineRun(process)


async def collect_output_of(arguments: list) -> "tuple[list[str], int]":
    """Run a script and collect its output within a single event loop.

    The process and the collector must share one loop, otherwise asyncio
    refuses to attach the pipe to a different loop.
    """
    run = await start_run(arguments)
    return await run.collect_output()


class CollectOutputTest(unittest.TestCase):
    def test_decodes_byte_lines_into_text(self) -> None:
        """The output must be str, not bytes, or every run raises TypeError."""
        lines, exit_code = asyncio.run(
            collect_output_of([sys.executable, "-c", "print('hello world')"])
        )

        self.assertEqual(lines, ["hello world"])
        self.assertIsInstance(lines[0], str)
        self.assertEqual(exit_code, 0)

    def test_strips_ansi_escape_codes(self) -> None:
        script = "import sys; sys.stdout.write('\\x1b[32mgreen\\x1b[0m\\n')"

        lines, _ = asyncio.run(collect_output_of([sys.executable, "-c", script]))

        self.assertEqual(lines, ["green"])

    def test_drops_blank_lines(self) -> None:
        script = "print('a'); print(); print('   '); print('b')"

        lines, _ = asyncio.run(collect_output_of([sys.executable, "-c", script]))

        self.assertEqual(lines, ["a", "b"])

    def test_reports_a_non_zero_exit_code(self) -> None:
        _, exit_code = asyncio.run(
            collect_output_of([sys.executable, "-c", "import sys; sys.exit(3)"])
        )

        self.assertEqual(exit_code, 3)

    def test_truncates_output_beyond_the_limit(self) -> None:
        script = "for index in range(200000):\n    print('x' * 100)\n"

        lines, _ = asyncio.run(collect_output_of([sys.executable, "-c", script]))

        self.assertEqual(lines[-1], "[output truncated: limit reached]")


class TerminateTest(unittest.TestCase):
    def test_terminate_stops_the_process(self) -> None:
        async def scenario() -> bool:
            run = await start_run([sys.executable, "-c", SLEEP_SCRIPT])
            self.assertTrue(run.is_running)

            run.terminate()
            for _ in range(TERMINATION_ATTEMPTS):
                if not run.is_running:
                    return True
                await asyncio.sleep(TERMINATION_POLL_SECONDS)
            return False

        self.assertTrue(asyncio.run(scenario()))

    def test_terminate_is_safe_on_a_finished_process(self) -> None:
        async def scenario() -> None:
            run = await start_run([sys.executable, "-c", "pass"])
            await run.collect_output()

            run.terminate()

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
