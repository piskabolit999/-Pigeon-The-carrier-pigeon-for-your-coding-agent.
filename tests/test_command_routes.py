"""Verify that /pair is actually wired to a handler.

`/pair` used to be unreachable: the prompt handler filters out commands, and
no CommandHandler was registered for it, so the pairing code could never
authorize a new chat.
"""

import unittest

from cline_bot.app import COMMAND_ROUTES


class PairCommandTest(unittest.TestCase):
    def test_pair_is_registered_as_a_command(self) -> None:
        # Without this the message falls through to no handler at all,
        # because the prompt handler explicitly excludes commands.
        self.assertIn("pair", COMMAND_ROUTES)

    def test_pair_points_at_the_pair_handler(self) -> None:
        self.assertEqual(COMMAND_ROUTES["pair"], "pair")

    def test_every_route_names_an_existing_handler(self) -> None:
        from cline_bot.handlers import BotHandlers

        for method_name in COMMAND_ROUTES.values():
            self.assertTrue(
                hasattr(BotHandlers, method_name),
                f"BotHandlers has no method {method_name!r}",
            )


if __name__ == "__main__":
    unittest.main()
