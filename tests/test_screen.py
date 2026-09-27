"""Unit tests for the screen helpers."""

import unittest

from cline_bot.screen import (
    LEFT_BUTTON_DOWN,
    RIGHT_BUTTON_DOWN,
    ScreenError,
    build_key_sequence,
    escape_for_send_keys,
)


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


class BuildKeySequenceTest(unittest.TestCase):
    def test_wraps_the_key_in_braces(self) -> None:
        self.assertEqual(build_key_sequence("ENTER"), "{ENTER}")

    def test_accepts_a_lowercase_name(self) -> None:
        self.assertEqual(build_key_sequence("enter"), "{ENTER}")

    def test_allows_a_control_combination(self) -> None:
        self.assertEqual(build_key_sequence("ctrl+a"), "{CTRL+A}")

    def test_rejects_an_unsupported_key(self) -> None:
        with self.assertRaises(ScreenError):
            build_key_sequence("NUKE")

    def test_rejects_a_sendkeys_directive(self) -> None:
        # SendKeys has directives such as {LAUNCH} that run commands, so the
        # allowlist has to block anything that is not a plain key.
        with self.assertRaises(ScreenError):
            build_key_sequence("{LAUNCH calc}")


class MouseTest(unittest.TestCase):
    def test_registers_the_mouse_commands(self) -> None:
        from cline_bot.app import COMMAND_ROUTES

        for command in ("click", "move"):
            self.assertIn(command, COMMAND_ROUTES)

    def test_known_buttons_map_to_a_down_flag(self) -> None:
        from cline_bot.screen import MOUSE_BUTTONS

        self.assertEqual(MOUSE_BUTTONS["left"], LEFT_BUTTON_DOWN)
        self.assertEqual(MOUSE_BUTTONS["right"], RIGHT_BUTTON_DOWN)


class ClickArgumentTest(unittest.TestCase):
    def setUp(self) -> None:
        from cline_bot.handlers import BotHandlers

        self.parse = BotHandlers._parse_position

    def test_reads_a_bare_position(self) -> None:
        self.assertEqual(self.parse(["100", "200"]), (100, 200, "left", 1))

    def test_reads_a_button(self) -> None:
        self.assertEqual(self.parse(["10", "20", "right"]), (10, 20, "right", 1))

    def test_reads_a_click_count(self) -> None:
        self.assertEqual(self.parse(["10", "20", "left", "2"]), (10, 20, "left", 2))

    def test_lowercases_the_button(self) -> None:
        self.assertEqual(self.parse(["1", "2", "MIDDLE"]), (1, 2, "middle", 1))

    def test_rejects_missing_coordinates(self) -> None:
        self.assertIsNone(self.parse(["10"]))

    def test_rejects_non_numeric_coordinates(self) -> None:
        self.assertIsNone(self.parse(["left", "down"]))


class ScreenCommandTest(unittest.TestCase):
    def test_registers_the_screen_commands(self) -> None:
        from cline_bot.app import COMMAND_ROUTES

        for command in ("screen", "type", "key"):
            self.assertIn(command, COMMAND_ROUTES)


if __name__ == "__main__":
    unittest.main()
