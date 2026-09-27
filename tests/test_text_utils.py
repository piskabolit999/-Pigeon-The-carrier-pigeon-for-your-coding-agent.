"""Unit tests for the pure text helpers."""

import unittest

from cline_bot.text_utils import split_into_chunks, strip_ansi_codes

SAMPLE_LIMIT = 10


class StripAnsiCodesTest(unittest.TestCase):
    def test_removes_color_sequences(self) -> None:
        self.assertEqual(strip_ansi_codes("\x1b[32mgreen\x1b[0m"), "green")

    def test_removes_carriage_returns(self) -> None:
        self.assertEqual(strip_ansi_codes("progress\r"), "progress")

    def test_keeps_plain_text_untouched(self) -> None:
        self.assertEqual(strip_ansi_codes("plain text"), "plain text")


class SplitIntoChunksTest(unittest.TestCase):
    def test_returns_single_chunk_when_text_fits(self) -> None:
        self.assertEqual(split_into_chunks("short", SAMPLE_LIMIT), ["short"])

    def test_splits_on_line_boundaries(self) -> None:
        chunks = split_into_chunks("aaaa\nbbbb\ncccc", SAMPLE_LIMIT)

        self.assertEqual(chunks, ["aaaa\nbbbb\n", "cccc"])

    def test_slices_lines_longer_than_the_limit(self) -> None:
        chunks = split_into_chunks("x" * 25, SAMPLE_LIMIT)

        self.assertEqual(chunks, ["x" * 10, "x" * 10, "x" * 5])

    def test_every_chunk_respects_the_limit(self) -> None:
        chunks = split_into_chunks("y" * 95, SAMPLE_LIMIT)

        self.assertTrue(all(len(chunk) <= SAMPLE_LIMIT for chunk in chunks))

    def test_returns_no_chunks_for_empty_text(self) -> None:
        self.assertEqual(split_into_chunks("", SAMPLE_LIMIT), [])


if __name__ == "__main__":
    unittest.main()
