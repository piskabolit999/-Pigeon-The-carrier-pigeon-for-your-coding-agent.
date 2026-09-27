"""Unit tests for the screen helpers."""

import unittest

from cline_bot.screen import escape_for_send_keys


class EscapeForSendKeysTest(unittest.TestCase):
    def test_keeps_plain_text(self) -> None:
        self.assertEqual(escape_for_send_keys("hello world"), "hello world")

    def test_escapes_the_shift_modifier(self) -> None:
        self.assertEqual(escape_for_send_keys("a+b"), "a{+}b")

    def test_escapes_the_ctrl_modifier(self) -> None:
        self.assertEqual(escape_for_send_keys("a^b"), "a{^}b")

    def test_escapes_the_alt_modifier(self) -> None:
        self.assertEqual(escape_for_send_keys("100%"), "100{%}")

    def test_escapes_the_enter_modifier(self) -> None:
        self.assertEqual(escape_for_send_keys("a~b"), "a{~}b")

    def test_keeps_emoji_intact(self) -> None:
        self.assertEqual(escape_for_send_keys("\U0001F600"), "\U0001F600")


class ScreenCommandTest(unittest.TestCase):
    def test_registers_the_screen_commands(self) -> None:
        from cline_bot.app import COMMAND_ROUTES

        for command in ("screen", "type", "key"):
            self.assertIn(command, COMMAND_ROUTES)


if __name__ == "__main__":
    unittest.main()
