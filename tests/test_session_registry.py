"""Unit tests for the per-chat session state."""

import tempfile
import unittest
from pathlib import Path

from cline_bot.config import AppConfig
from cline_bot.session_registry import (
    MAX_REMEMBERED_ANSWER_CHARACTERS,
    MAX_REMEMBERED_TURNS,
    SessionRegistry,
)

EXAMPLE_CHAT_ID = 100
OTHER_CHAT_ID = 200
EXAMPLE_TOKEN = "test-token"


def build_config(default_directory: str) -> AppConfig:
    return AppConfig(
        telegram_bot_token=EXAMPLE_TOKEN,
        default_working_directory=default_directory,
        default_agent_mode="plan",
        auto_approve_tools=False,
    )


def build_session():
    return SessionRegistry(build_config(str(Path(tempfile.gettempdir())))).get_or_create(
        EXAMPLE_CHAT_ID
    )


class ConversationMemoryTest(unittest.TestCase):
    def test_first_prompt_has_no_history(self) -> None:
        session = build_session()

        self.assertEqual(session.build_prompt_with_context("now the tests"), "now the tests")

    def test_earlier_turns_are_replayed(self) -> None:
        session = build_session()
        session.remember_turn("add type hints", "done, 3 files")

        prompt = session.build_prompt_with_context("now the tests")

        self.assertIn("add type hints", prompt)
        self.assertIn("done, 3 files", prompt)
        self.assertIn("now the tests", prompt)

    def test_keeps_only_the_recent_turns(self) -> None:
        session = build_session()
        for index in range(MAX_REMEMBERED_TURNS + 3):
            session.remember_turn(f"request {index}", f"answer {index}")

        prompt = session.build_prompt_with_context("latest")

        self.assertNotIn("request 0", prompt)
        self.assertIn(f"request {MAX_REMEMBERED_TURNS + 2}", prompt)

    def test_very_long_answers_are_trimmed(self) -> None:
        session = build_session()
        session.remember_turn("q", "x" * (MAX_REMEMBERED_ANSWER_CHARACTERS * 2))

        prompt = session.build_prompt_with_context("next")

        self.assertLess(
            len(prompt), MAX_REMEMBERED_ANSWER_CHARACTERS + len("q") + 500
        )

    def test_forget_turns_clears_the_memory(self) -> None:
        session = build_session()
        session.remember_turn("old", "answer")
        session.forget_turns()

        self.assertEqual(session.build_prompt_with_context("fresh"), "fresh")


class SessionRegistryTest(unittest.TestCase):
    def test_creates_session_from_configuration_defaults(self) -> None:
        registry = SessionRegistry(build_config(str(Path(tempfile.gettempdir()))))

        session = registry.get_or_create(EXAMPLE_CHAT_ID)

        self.assertEqual(session.agent_mode, "plan")
        self.assertFalse(session.is_auto_approved)

    def test_returns_the_same_session_for_the_same_chat(self) -> None:
        registry = SessionRegistry(build_config(str(Path(tempfile.gettempdir()))))

        first = registry.get_or_create(EXAMPLE_CHAT_ID)
        second = registry.get_or_create(EXAMPLE_CHAT_ID)

        self.assertIs(first, second)

    def test_registers_the_model_command(self) -> None:
        # A model can only be switched from the chat, so the command has to
        # be reachable like every other one.
        from cline_bot.app import COMMAND_ROUTES

        self.assertIn("model", COMMAND_ROUTES)

    def test_session_starts_without_a_model(self) -> None:
        session = SessionRegistry(
            build_config(str(Path(tempfile.gettempdir())))
        ).get_or_create(EXAMPLE_CHAT_ID)

        # None means "let the provider decide", not a hard-coded model.
        self.assertIsNone(session.model_id)

    def test_keeps_chats_isolated(self) -> None:
        registry = SessionRegistry(build_config(str(Path(tempfile.gettempdir()))))

        registry.get_or_create(EXAMPLE_CHAT_ID).agent_mode = "act"

        self.assertEqual(registry.get_or_create(OTHER_CHAT_ID).agent_mode, "plan")

    def test_replaces_a_directory_that_no_longer_exists(self) -> None:
        fallback = tempfile.gettempdir()
        registry = SessionRegistry(build_config(fallback))
        session = registry.get_or_create(EXAMPLE_CHAT_ID)
        session.working_directory = str(Path(fallback) / "deleted-folder")

        resolved = registry.resolve_working_directory(session)

        self.assertTrue(Path(resolved).is_dir())


if __name__ == "__main__":
    unittest.main()
