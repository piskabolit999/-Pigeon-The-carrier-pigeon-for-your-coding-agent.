"""Unit tests for the durable conversation log and the chat session state."""

import tempfile
import unittest
from pathlib import Path

from cline_bot.config import AppConfig
from cline_bot.conversation_log import (
    MAX_TURN_ANSWER_CHARACTERS,
    ConversationLog,
)
from cline_bot.session_registry import SessionRegistry

EXAMPLE_CHAT_ID = 100
OTHER_CHAT_ID = 200
EXAMPLE_TOKEN = "test-token"
SMALL_BUDGET = 120


def build_config() -> AppConfig:
    return AppConfig(
        telegram_bot_token=EXAMPLE_TOKEN,
        default_working_directory=tempfile.gettempdir(),
    )


def build_registry() -> SessionRegistry:
    with tempfile.TemporaryDirectory() as directory:
        return SessionRegistry(build_config(), Path(directory))


def build_log(budget: int = 10_000) -> ConversationLog:
    with tempfile.TemporaryDirectory() as directory:
        return ConversationLog(Path(directory), EXAMPLE_CHAT_ID, budget)


class ConversationLogTest(unittest.TestCase):
    def test_starts_empty(self) -> None:
        self.assertEqual(build_log().render(), "")

    def test_renders_a_recorded_turn(self) -> None:
        log = build_log()
        log.append("add hints", "done")

        rendered = log.render()

        self.assertIn("add hints", rendered)
        self.assertIn("done", rendered)

    def test_trims_a_very_long_answer(self) -> None:
        log = build_log()
        log.append("q", "x" * (MAX_TURN_ANSWER_CHARACTERS * 2))

        answer = log.turns()[0][1]

        self.assertLessEqual(len(answer), MAX_TURN_ANSWER_CHARACTERS)

    def test_drops_the_oldest_turn_when_over_budget(self) -> None:
        log = build_log(SMALL_BUDGET)
        for index in range(20):
            log.append(f"request {index} " * 3, f"answer {index} " * 3)

        rendered = log.render()

        self.assertNotIn("request 0", rendered)
        self.assertIn("request 19", rendered)

    def test_survives_a_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ConversationLog(Path(directory), EXAMPLE_CHAT_ID).append("q", "a")
            reopened = ConversationLog(Path(directory), EXAMPLE_CHAT_ID)

            self.assertEqual(len(reopened.turns()), 1)

    def test_clear_removes_the_history(self) -> None:
        log = build_log()
        log.append("q", "a")
        log.clear()

        self.assertEqual(log.render(), "")

    def test_skips_a_damaged_line(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / f"conversation-{EXAMPLE_CHAT_ID}.jsonl"
            path.write_text("not json\n", encoding="utf-8")

            log = ConversationLog(Path(directory), EXAMPLE_CHAT_ID)

            self.assertEqual(log.turns(), [])


class ChatSessionTest(unittest.TestCase):
    def test_first_prompt_has_no_history(self) -> None:
        session = build_registry().get_or_create(EXAMPLE_CHAT_ID)

        self.assertEqual(session.build_prompt_with_context("hi"), "hi")

    def test_second_prompt_replays_the_first(self) -> None:
        session = build_registry().get_or_create(EXAMPLE_CHAT_ID)
        session.remember_turn("add hints", "done")

        prompt = session.build_prompt_with_context("now the tests")

        self.assertIn("add hints", prompt)
        self.assertIn("now the tests", prompt)

    def test_adopted_transcript_is_replayed(self) -> None:
        session = build_registry().get_or_create(EXAMPLE_CHAT_ID)
        session.adopt_session("abc", "TRANSCRIPT")

        self.assertIn("TRANSCRIPT", session.build_prompt_with_context("go on"))

    def test_forget_history_drops_everything(self) -> None:
        session = build_registry().get_or_create(EXAMPLE_CHAT_ID)
        session.remember_turn("q", "a")
        session.adopt_session("abc", "TRANSCRIPT")
        session.forget_history()

        self.assertEqual(session.build_prompt_with_context("fresh"), "fresh")

    def test_keeps_chats_isolated(self) -> None:
        registry = build_registry()
        first = registry.get_or_create(EXAMPLE_CHAT_ID)
        first.remember_turn("q", "a")

        self.assertEqual(registry.get_or_create(OTHER_CHAT_ID).conversation.turns(), [])


if __name__ == "__main__":
    unittest.main()
