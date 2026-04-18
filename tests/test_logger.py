#!/usr/bin/env python3
"""Tests for logging configuration."""

import logging
from pathlib import Path

import pytest
from platformdirs import PlatformDirs

import rekordbox_edit.logger as rbe_logger
from rekordbox_edit._click import PrintChoice
from rekordbox_edit.logger import get_debug_file_path, set_level, setup_logging


@pytest.fixture(autouse=True)
def reset_logging():
    yield
    setup_logging()


@pytest.fixture
def custom_log_file(tmp_path):
    """Configure logging to write to a file in a temporary directory."""
    log_file = tmp_path / "test.log"
    setup_logging(log_file=str(log_file))
    yield log_file


class TestSetupLogging:
    def test_creates_log_file_in_default_path(self):
        """setup_logging() creates a log file in the default platform data dir."""
        expected_dir = Path(PlatformDirs("rekordbox-edit").user_data_dir)
        assert get_debug_file_path().parent == expected_dir

    def test_creates_log_file_at_given_path(self, custom_log_file):
        """setup_logging(log_file=...) uses the provided path."""
        assert get_debug_file_path() == custom_log_file

    def test_file_handler_captures_all_levels(self, custom_log_file):
        """File handler records DEBUG, INFO, WARNING, ERROR, and CRITICAL messages."""
        pkg_logger = logging.getLogger("rekordbox_edit")
        pkg_logger.debug("debug msg")
        pkg_logger.info("info msg")
        pkg_logger.warning("warning msg")
        pkg_logger.error("error msg")
        pkg_logger.critical("critical msg")
        for handler in pkg_logger.handlers:
            handler.flush()

        content = custom_log_file.read_text(encoding="utf-8")
        assert "DEBUG: debug msg" in content
        assert "INFO: info msg" in content
        assert "WARNING: warning msg" in content
        assert "ERROR: error msg" in content
        assert "CRITICAL: critical msg" in content

    def test_calling_setup_logging_twice_replaces_handlers(self, tmp_path):
        """setup_logging() is idempotent — calling it again replaces handlers."""
        setup_logging(log_file=str(tmp_path / "first.log"))
        setup_logging(log_file=str(tmp_path / "second.log"))
        pkg_logger = logging.getLogger("rekordbox_edit")
        # Should have exactly 2 handlers (file + console), not 4
        assert len(pkg_logger.handlers) == 2

    def test_module_loggers_propagate_to_package_logger(self, custom_log_file):
        """Loggers from child modules propagate to the package logger's file handler."""
        child_logger = logging.getLogger("rekordbox_edit.commands.search")
        child_logger.info("from child")
        for handler in logging.getLogger("rekordbox_edit").handlers:
            handler.flush()

        content = custom_log_file.read_text(encoding="utf-8")
        assert "from child" in content


class TestSetLevel:
    def test_default_console_level_is_info(self):
        """Console handler starts at INFO level."""
        assert rbe_logger._console_handler is not None
        assert rbe_logger._console_handler.level == logging.INFO

    def test_set_level_none_sets_info(self):
        set_level(None)
        assert rbe_logger._console_handler is not None
        assert rbe_logger._console_handler.level == logging.INFO

    def test_set_level_info_sets_info(self):
        set_level(PrintChoice.INFO)
        assert rbe_logger._console_handler is not None
        assert rbe_logger._console_handler.level == logging.INFO

    def test_set_level_ids_sets_error(self):
        set_level(PrintChoice.IDS)
        assert rbe_logger._console_handler is not None
        assert rbe_logger._console_handler.level == logging.ERROR

    def test_set_level_silent_sets_error(self):
        set_level(PrintChoice.SILENT)
        assert rbe_logger._console_handler is not None
        assert rbe_logger._console_handler.level == logging.ERROR

    def test_set_level_debug_sets_debug(self):
        set_level(PrintChoice.DEBUG)
        assert rbe_logger._console_handler is not None
        assert rbe_logger._console_handler.level == logging.DEBUG

    def test_set_level_affects_all_module_loggers(self, tmp_path, capsys):
        """set_level() on the shared handler affects output from all module loggers."""
        setup_logging(log_file=str(tmp_path / "test.log"))
        set_level(PrintChoice.IDS)

        logging.getLogger("rekordbox_edit.query").info("should be suppressed")
        logging.getLogger("rekordbox_edit.utils").info("also suppressed")

        captured = capsys.readouterr()
        assert "should be suppressed" not in captured.out
        assert "also suppressed" not in captured.out
