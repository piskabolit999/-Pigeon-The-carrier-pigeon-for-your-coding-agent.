"""Unit tests for the autostart registration script."""

import unittest
from pathlib import Path

from cline_bot.autostart import (
    TASK_NAME,
    build_registration_script,
    find_windowless_python,
)

EXAMPLE_PYTHON = r"C:\Python\pythonw.exe"
EXAMPLE_ENTRY_POINT = Path(r"C:\projects\bridge\run_bot.py")


class BuildRegistrationScriptTest(unittest.TestCase):
    def setUp(self) -> None:
        self.script = build_registration_script(EXAMPLE_PYTHON, EXAMPLE_ENTRY_POINT)

    def test_registers_the_named_task(self) -> None:
        self.assertIn(f"-TaskName '{TASK_NAME}'", self.script)

    def test_runs_the_windowless_interpreter(self) -> None:
        self.assertIn("pythonw.exe", self.script)

    def test_quotes_the_entry_point_argument(self) -> None:
        self.assertIn('-Argument \'"C:\\projects\\bridge\\run_bot.py"\'', self.script)

    def test_does_not_double_up_path_separators(self) -> None:
        # A doubled separator would break the task command line.
        self.assertNotIn("\\\\", self.script)

    def test_triggers_at_logon(self) -> None:
        self.assertIn("New-ScheduledTaskTrigger -AtLogOn", self.script)

    def test_requires_an_interactive_logon(self) -> None:
        self.assertIn("-LogonType Interactive", self.script)

    def test_enables_restart_on_failure(self) -> None:
        self.assertIn("-RestartCount", self.script)

    def test_has_no_execution_time_limit(self) -> None:
        self.assertIn("-ExecutionTimeLimit ([TimeSpan]::Zero)", self.script)

    def test_bypasses_the_execution_policy(self) -> None:
        # The script is passed to `powershell -Command`, so the policy flag
        # lives in the caller, not here. Guard against it leaking in instead.
        self.assertNotIn("ExecutionPolicy", self.script)


class FindWindowlessPythonTest(unittest.TestCase):
    def test_returns_an_existing_file(self) -> None:
        self.assertTrue(Path(find_windowless_python()).exists())


if __name__ == "__main__":
    unittest.main()
