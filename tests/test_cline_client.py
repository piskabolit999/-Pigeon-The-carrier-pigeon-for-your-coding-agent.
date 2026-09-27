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
    def test_uses_the_node_entry_point_instead_of_a_shim(self) -> None:
        # The .cmd shim re-encodes arguments through cmd.exe, which breaks
        # emoji and non-Latin text, so the Node entry point is used directly.
        launcher = ClineClient._resolve_launcher(EXAMPLE_COMMAND)

        self.assertNotIn("/c", launcher)
        self.assertTrue(launcher[0].lower().endswith("node.exe") or launcher[0] == "node")

    def test_reports_a_missing_executable(self) -> None:
        with self.assertRaises(ClineClientError):
            build_client("definitely-not-installed-command")


class BuildCommandTest(unittest.TestCase):
    def test_passes_the_prompt_and_working_directory(self) -> None:
        arguments = build_client().build_command("fix bug", EXAMPLE_DIRECTORY, "act", True)

        self.assertIn("fix bug", arguments)
        self.assertIn(EXAMPLE_DIRECTORY, arguments)

    def test_never_resumes_a_session(self) -> None:
        # Resuming switches the CLI to its TUI, which needs a TTY.
        arguments = build_client().build_command("x", EXAMPLE_DIRECTORY, "act", True)

        self.assertNotIn("--id", arguments)

    def test_omits_thinking_when_disabled(self) -> None:
        # Reasoning models reject `--thinking none`.
        client = ClineClient(
            command=EXAMPLE_COMMAND,
            run_timeout_seconds=EXAMPLE_TIMEOUT,
            thinking_level="none",
        )

        arguments = client.build_command("x", EXAMPLE_DIRECTORY, "act", True)

        self.assertNotIn("--thinking", arguments)

    def test_keeps_an_enabled_thinking_level(self) -> None:
        arguments = build_client().build_command("x", EXAMPLE_DIRECTORY, "act", True)

        self.assertEqual(arguments[arguments.index("--thinking") + 1], EXAMPLE_THINKING)


    def test_adds_plan_flag_only_in_plan_mode(self) -> None:
        plan_arguments = build_client().build_command("x", EXAMPLE_DIRECTORY, "plan", True)
        act_arguments = build_client().build_command("x", EXAMPLE_DIRECTORY, "act", True)

        self.assertIn("--plan", plan_arguments)
        self.assertNotIn("--plan", act_arguments)

    def test_passes_auto_approve_as_lowercase_flag(self) -> None:
        arguments = build_client().build_command("x", EXAMPLE_DIRECTORY, "act", False)

        self.assertEqual(arguments[arguments.index("--auto-approve") + 1], "false")

    def test_passes_the_requested_model(self) -> None:
        arguments = build_client().build_command(
            "x", EXAMPLE_DIRECTORY, "act", True, "anthropic/claude-sonnet-4"
        )

        self.assertEqual(
            arguments[arguments.index("--model") + 1], "anthropic/claude-sonnet-4"
        )

    def test_omits_model_flag_for_the_provider_default(self) -> None:
        # The bot must not override a model the user set in the CLI.
        arguments = build_client().build_command(
            "x", EXAMPLE_DIRECTORY, "act", True
        )

        self.assertNotIn("--model", arguments)


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
