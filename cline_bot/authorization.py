"""Access control for the Telegram bot.

Only chats listed in `allowed_chat_ids` may drive Cline. When a pairing code is
configured, a new chat can add itself once by sending `/pair <code>`; the code
is then persisted together with the chat id.
"""

from typing import Optional, Tuple

PAIR_COMMAND = "/pair"


class AuthorizationPolicy:
    """Decides whether a chat may use the bot."""

    def __init__(self, config) -> None:
        self._config = config

    def is_allowed(self, chat_id: int) -> bool:
        return chat_id in self._config.allowed_chat_ids

    def is_pairing_request(self, text: str) -> bool:
        return text.strip().startswith(PAIR_COMMAND)

    def verify_pairing_code(self, text: str) -> bool:
        """Return True when the message contains the correct pairing code."""
        expected_code = self._config.pairing_code
        return bool(expected_code) and text.strip() == f"{PAIR_COMMAND} {expected_code}"

    def register_chat(self, chat_id: int) -> None:
        """Add a chat to the whitelist and persist it."""
        if self.is_allowed(chat_id):
            return
        self._config.allowed_chat_ids.append(chat_id)
        self._config.save_allowed_chat_ids()

    def check(self, chat_id: int, text: str) -> Tuple[bool, bool]:
        """Evaluate a single incoming message.

        Returns a pair of flags: (is_authorized, is_pairing_attempt).
        Pairing messages are always evaluated so the bot can confirm success
        or explain the failure instead of silently ignoring them.
        """
        if self.is_pairing_request(text):
            if self.verify_pairing_code(text):
                self.register_chat(chat_id)
                return True, True
            return False, True
        return self.is_allowed(chat_id), False

    def unauthorized_message(self) -> str:
        return (
            "Access denied. Ask the owner to add your chat id to "
            "'allowed_chat_ids' in config.json."
        )

    def pair_error_message(self) -> Optional[str]:
        if not self._config.pairing_code:
            return "Pairing is disabled on this instance."
        return "Wrong pairing code."
