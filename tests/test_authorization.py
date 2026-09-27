"""Unit tests for the whitelist and pairing rules."""

import unittest
from typing import List, Optional

from cline_bot.authorization import AuthorizationPolicy

EXAMPLE_CHAT_ID = 42
OTHER_CHAT_ID = 43
EXAMPLE_PAIRING_CODE = "s3cret"


class FakeConfig:
    """Minimal config stub so the policy can be tested in isolation."""

    def __init__(self, allowed_chat_ids: List[int], pairing_code: Optional[str]) -> None:
        self.allowed_chat_ids = allowed_chat_ids
        self.pairing_code = pairing_code
        self.save_count = 0

    def save_allowed_chat_ids(self) -> None:
        self.save_count += 1


class AuthorizationPolicyTest(unittest.TestCase):
    def test_allows_chat_from_whitelist(self) -> None:
        policy = AuthorizationPolicy(FakeConfig([EXAMPLE_CHAT_ID], None))

        is_authorized, _ = policy.check(EXAMPLE_CHAT_ID, "run tests")

        self.assertTrue(is_authorized)

    def test_rejects_unknown_chat(self) -> None:
        policy = AuthorizationPolicy(FakeConfig([], None))

        is_authorized, _ = policy.check(EXAMPLE_CHAT_ID, "run tests")

        self.assertFalse(is_authorized)

    def test_registers_chat_on_valid_pairing_code(self) -> None:
        config = FakeConfig([], EXAMPLE_PAIRING_CODE)
        policy = AuthorizationPolicy(config)

        is_authorized, is_pairing = policy.check(
            OTHER_CHAT_ID, f"/pair {EXAMPLE_PAIRING_CODE}"
        )

        self.assertTrue(is_authorized)
        self.assertTrue(is_pairing)
        self.assertIn(OTHER_CHAT_ID, config.allowed_chat_ids)
        self.assertEqual(config.save_count, 1)

    def test_rejects_wrong_pairing_code(self) -> None:
        config = FakeConfig([], EXAMPLE_PAIRING_CODE)
        policy = AuthorizationPolicy(config)

        is_authorized, is_pairing = policy.check(OTHER_CHAT_ID, "/pair wrong")

        self.assertFalse(is_authorized)
        self.assertTrue(is_pairing)
        self.assertEqual(config.allowed_chat_ids, [])

    def test_does_not_register_same_chat_twice(self) -> None:
        config = FakeConfig([EXAMPLE_CHAT_ID], EXAMPLE_PAIRING_CODE)
        policy = AuthorizationPolicy(config)

        policy.register_chat(EXAMPLE_CHAT_ID)

        self.assertEqual(config.save_count, 0)


if __name__ == "__main__":
    unittest.main()
