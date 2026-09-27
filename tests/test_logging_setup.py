"""Unit tests for secret redaction in logs.

The HTTP client logs full request URLs, and every Telegram URL embeds the bot
token. Without redaction the log file becomes a credential store, and a user
published exactly that file by accident.
"""

import logging
import unittest

from cline_bot.logging_setup import REDACTED, SecretRedactingFilter

EXAMPLE_TOKEN = "123456789:AAExampleSecretTokenValue1234567890"
EXAMPLE_LOGGED_URL = (
    f"HTTP Request: POST https://api.telegram.org/bot{EXAMPLE_TOKEN}/getMe "
    '"HTTP/1.1 200 OK"'
)


def make_record(message: str) -> logging.LogRecord:
    return logging.LogRecord(
        name="httpx",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )


class SecretRedactingFilterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.record_filter = SecretRedactingFilter()

    def test_removes_the_token_from_a_url(self) -> None:
        record = make_record(EXAMPLE_LOGGED_URL)

        self.record_filter.filter(record)

        self.assertNotIn(EXAMPLE_TOKEN, record.msg)
        self.assertIn(REDACTED, record.msg)

    def test_keeps_the_path_after_the_token(self) -> None:
        record = make_record(EXAMPLE_LOGGED_URL)

        self.record_filter.filter(record)

        self.assertIn("/getMe", record.msg)

    def test_redacts_every_occurrence(self) -> None:
        record = make_record(f"{EXAMPLE_LOGGED_URL} and /bot{EXAMPLE_TOKEN}/x")

        self.record_filter.filter(record)

        self.assertNotIn(EXAMPLE_TOKEN, record.msg)

    def test_always_keeps_the_record(self) -> None:
        record = make_record(EXAMPLE_LOGGED_URL)

        self.assertTrue(self.record_filter.filter(record))

    def test_leaves_ordinary_messages_untouched(self) -> None:
        record = make_record("Bot started, polling for updates")

        self.record_filter.filter(record)

        self.assertEqual(record.msg, "Bot started, polling for updates")

    def test_redacts_a_token_passed_as_a_format_argument(self) -> None:
        # The HTTP client logs lazily, so the token arrives in the arguments.
        record = logging.LogRecord(
            name="httpx",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg='HTTP Request: %s %s "%s %d %s"',
            args=(
                "POST",
                f"https://api.telegram.org/bot{EXAMPLE_TOKEN}/getMe",
                "HTTP/1.1",
                200,
                "OK",
            ),
            exc_info=None,
        )

        self.record_filter.filter(record)

        self.assertNotIn(EXAMPLE_TOKEN, record.msg)
        self.assertIn(REDACTED, record.msg)

    def test_keeps_the_rest_of_a_lazily_formatted_message(self) -> None:
        record = logging.LogRecord(
            name="httpx",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="HTTP Request: %s %s",
            args=("POST", f"https://api.telegram.org/bot{EXAMPLE_TOKEN}/getMe"),
            exc_info=None,
        )

        self.record_filter.filter(record)

        # Placeholders must be rendered, not left in the log.
        self.assertNotIn("%s", record.msg)
        self.assertIn("POST", record.msg)
        self.assertIn("/getMe", record.msg)

    def test_clears_lazy_formatting_arguments(self) -> None:
        # A record with %-args would otherwise be formatted after filtering.
        record = logging.LogRecord(
            name="httpx",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="request to /bot%s/getMe",
            args=(EXAMPLE_TOKEN,),
            exc_info=None,
        )

        self.record_filter.filter(record)

        self.assertEqual(record.args, ())
        self.assertNotIn(EXAMPLE_TOKEN, str(record.msg))


if __name__ == "__main__":
    unittest.main()
