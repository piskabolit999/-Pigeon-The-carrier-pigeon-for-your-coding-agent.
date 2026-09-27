"""Unit tests for the Cline CLI command construction and history parsing."""

import unittest

from cline_bot.cline_client import ClineClient, ClineClientError

EXAMPLE_COMMAND = "clite"
EXAMPLE_TIMEOUT = 120
EXAMPLE_THINKING = "high"
EXAMPLE_DIRECTORY = "C:/projects/demo"


def build_client(command: str = EXAMPLE_COMMAND) -> ClineClient:
    return ClineClient(
        command=command,
        run_timeout_seconds=EXAMPLE_TIMEOUT,
        thinking_level=EXAMPLE_THINKING,
    )


class ResolveLauncherTest(unittest.TestCase):
    def test_wraps_windows_shims_in_the_command_interpreter(self) -> None:
        client = build_client()

        self.assertIn("/c", client.build_command("hi", EXAMPLE_DIRECTORY, "act", True))

    def test_reports_a_missing_executable(self) -> None:
        with self.assertRaises(ClineClientError):
            build_client("definitely-not-installed-command")


class BuildCommandTest(unittest.TestCase):
    def test_passes_the_prompt_and_working_directory(self) -> None:
        arguments = build_client().build_command("fix bug", EXAMPLE_DIRECTORY, "act", True)

        self.assertIn("fix bug", arguments)
        self.assertIn(EXAMPLE_DIRECTORY, arguments)

    def test_adds_plan_flag_only_in_plan_mode(self) -> None:
        plan_arguments = build_client().build_command("x", EXAMPLE_DIRECTORY, "plan", True)
        act_arguments = build_client().build_command("x", EXAMPLE_DIRECTORY, "act", True)

        self.assertIn("--plan", plan_arguments)
        self.assertNotIn("--plan", act_arguments)

    def test_passes_auto_approve_as_lowercase_flag(self) -> None:
        arguments = build_client().build_command("x", EXAMPLE_DIRECTORY, "act", False)

        self.assertEqual(arguments[arguments.index("--auto-approve") + 1], "false")

    def test_continues_an_existing_session(self) -> None:
        arguments = build_client().build_command(
            "x", EXAMPLE_DIRECTORY, "act", True, "session-1"
        )

        self.assertEqual(arguments[arguments.index("--id") + 1], "session-1")

    def test_omits_session_flag_for_a_new_session(self) -> None:
        arguments = build_client().build_command("x", EXAMPLE_DIRECTORY, "act", True)

        self.assertNotIn("--id", arguments)


class ParseHistoryTest(unittest.TestCase):
    def test_parses_a_json_array(self) -> None:
        sessions = ClineClient._parse_history('[{"sessionId": "a"}]')

        self.assertEqual(sessions, [{"sessionId": "a"}])

    def test_returns_empty_list_for_broken_json(self) -> None:
        self.assertEqual(ClineClient._parse_history("not json"), [])

    def test_returns_empty_list_for_empty_output(self) -> None:
        self.assertEqual(ClineClient._parse_history(""), [])


if __name__ == "__main__":
    unittest.main()
