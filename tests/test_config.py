"""Unit tests for configuration loading and validation."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cline_bot.config import (
    TOKEN_ENVIRONMENT_VARIABLE,
    AppConfig,
    ConfigurationError,
    load_config,
)

MINIMAL_VALID_CONFIG = {"telegram_bot_token": "file-token"}


class AppConfigValidationTest(unittest.TestCase):
    def test_rejects_an_empty_token(self) -> None:
        with self.assertRaises(ConfigurationError):
            AppConfig(telegram_bot_token="")

    def test_rejects_an_unknown_agent_mode(self) -> None:
        with self.assertRaises(ConfigurationError):
            AppConfig(telegram_bot_token="token", default_agent_mode="turbo")

    def test_rejects_an_unknown_thinking_level(self) -> None:
        with self.assertRaises(ConfigurationError):
            AppConfig(telegram_bot_token="token", thinking_level="extreme")


class LoadConfigTest(unittest.TestCase):
    def test_reads_values_from_the_config_file(self) -> None:
        raw_config = dict(MINIMAL_VALID_CONFIG, default_cwd="C:/projects/demo")

        with mock.patch("cline_bot.config._read_raw_config", return_value=raw_config):
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop(TOKEN_ENVIRONMENT_VARIABLE, None)
                config = load_config()

        self.assertEqual(config.default_working_directory, "C:/projects/demo")

    def test_environment_token_wins_over_the_file(self) -> None:
        with mock.patch("cline_bot.config._read_raw_config", return_value=MINIMAL_VALID_CONFIG):
            with mock.patch.dict(
                os.environ, {TOKEN_ENVIRONMENT_VARIABLE: "env-token"}
            ):
                config = load_config()

        self.assertEqual(config.telegram_bot_token, "env-token")

    def test_uses_defaults_when_the_file_is_missing(self) -> None:
        with mock.patch("cline_bot.config._read_raw_config", return_value={}):
            with mock.patch.dict(os.environ, {TOKEN_ENVIRONMENT_VARIABLE: "env-token"}):
                config = load_config()

        self.assertEqual(config.clite_command, "clite")
        self.assertEqual(config.default_agent_mode, "act")
        self.assertTrue(config.auto_approve_tools)


class ReadRawConfigTest(unittest.TestCase):
    def test_returns_empty_dict_when_the_file_is_missing(self) -> None:
        with mock.patch("cline_bot.config.CONFIG_FILE_PATH", Path("C:/nowhere.json")):
            with mock.patch("pathlib.Path.exists", return_value=False):
                from cline_bot.config import _read_raw_config

                self.assertEqual(_read_raw_config(), {})

    def test_reports_the_file_name_on_a_parse_error(self) -> None:
        broken = Path(tempfile.mkstemp(suffix=".json")[1])
        broken.write_text('{"allowed_chat_ids": [allowed_chat_ids]}', encoding="utf-8")

        with mock.patch("cline_bot.config.CONFIG_FILE_PATH", broken):
            with self.assertRaises(ConfigurationError) as raised:
                from cline_bot.config import _read_raw_config

                _read_raw_config()

        self.assertIn(broken.name, str(raised.exception))
        self.assertIn("not valid JSON", str(raised.exception))

    def test_rejects_a_json_array_at_the_top_level(self) -> None:
        wrong_shape = Path(tempfile.mkstemp(suffix=".json")[1])
        wrong_shape.write_text("[1, 2, 3]", encoding="utf-8")

        with mock.patch("cline_bot.config.CONFIG_FILE_PATH", wrong_shape):
            with self.assertRaises(ConfigurationError):
                from cline_bot.config import _read_raw_config

                _read_raw_config()


class LogFileLocationTest(unittest.TestCase):
    def test_log_path_stays_inside_the_project(self) -> None:
        config = AppConfig(telegram_bot_token="token")

        self.assertTrue(config.log_file_path.is_absolute())


if __name__ == "__main__":
    unittest.main()
