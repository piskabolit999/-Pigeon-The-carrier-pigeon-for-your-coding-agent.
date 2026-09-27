"""Unit tests for the Cline desktop application helpers."""

import unittest
from unittest import mock

from cline_bot import cline_app

TASKLIST_CSV = (
    '"cline-app.exe","5308","Console","1","38.940 K"\n'
    'INFO: No tasks are running\n'
)


class FindWindowProcessIdTest(unittest.TestCase):
    def test_reads_the_pid_from_csv_output(self) -> None:
        # The column layout is padded with spaces that depend on the process
        # name, so CSV is parsed instead.
        with mock.patch.object(
            cline_app, "find_running_process",
            return_value=mock.Mock(stdout=TASKLIST_CSV),
        ):
            self.assertEqual(cline_app.find_window_process_id(), 5308)

    def test_returns_none_when_nothing_is_running(self) -> None:
        with mock.patch.object(
            cline_app, "find_running_process",
            return_value=mock.Mock(stdout="INFO: No tasks are running\n"),
        ):
            self.assertIsNone(cline_app.find_window_process_id())

    def test_reports_running_only_with_a_pid(self) -> None:
        with mock.patch.object(cline_app, "find_window_process_id", return_value=None):
            self.assertFalse(cline_app.is_running())
        with mock.patch.object(cline_app, "find_window_process_id", return_value=1):
            self.assertTrue(cline_app.is_running())


class FocusTest(unittest.TestCase):
    def test_raises_when_the_window_is_gone(self) -> None:
        failed = mock.Mock(returncode=1, stderr="the Cline window is gone", stdout="")
        with mock.patch.object(cline_app.subprocess, "run", return_value=failed):
            with self.assertRaises(cline_app.ClineAppError):
                cline_app.focus(999)

    def test_passes_the_process_id_to_powershell(self) -> None:
        captured = {}

        def fake_run(arguments, **kwargs):
            captured["env"] = kwargs["env"]
            return mock.Mock(returncode=0, stderr="", stdout="focused")

        with mock.patch.object(cline_app.subprocess, "run", side_effect=fake_run):
            cline_app.focus(4242)

        self.assertEqual(captured["env"]["PIGEON_PID"], "4242")


class CommandRouteTest(unittest.TestCase):
    def test_registers_the_cline_command(self) -> None:
        from cline_bot.app import COMMAND_ROUTES

        self.assertIn("cline", COMMAND_ROUTES)


if __name__ == "__main__":
    unittest.main()
