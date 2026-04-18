#!/usr/bin/env python3
"""Logging configuration for rekordbox-edit."""

import atexit
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import click
from platformdirs import PlatformDirs

from rekordbox_edit._click import PrintChoice

LOG_FILE_NAME = f"debug_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"

_APP_DIR = Path(
    PlatformDirs(appname="rekordbox-edit", ensure_exists=True).user_data_dir
)

_console_handler: Optional["ConsoleLogHandler"] = None
_debug_file_path: Path = _APP_DIR / LOG_FILE_NAME


class ConsoleLogHandler(logging.Handler):
    """Custom logging handler that outputs to Click with styling."""

    def emit(self, record):
        try:
            msg = self.format(record)
            if record.levelno >= logging.CRITICAL:
                click.echo(click.style(msg, fg="red", bold=True))
            elif record.levelno >= logging.ERROR:
                click.echo(click.style(msg, fg="red"))
            elif record.levelno >= logging.WARNING:
                click.echo(click.style(msg, fg="yellow"))
            else:
                click.echo(msg)
        except Exception:
            self.handleError(record)


def get_debug_file_path() -> Path:
    return _debug_file_path


def set_level(level: PrintChoice | None) -> None:
    """Update the console handler log level."""
    global _console_handler

    if _console_handler is None:
        return
    if level in (PrintChoice.SILENT, PrintChoice.IDS):
        _console_handler.setLevel(logging.ERROR)
    elif level == PrintChoice.DEBUG:
        _console_handler.setLevel(logging.DEBUG)
    else:
        _console_handler.setLevel(logging.INFO)


def setup_logging(log_file: Optional[str] = None) -> None:
    """Configure the package logger with file and console handlers."""
    global _console_handler, _debug_file_path

    pkg_logger = logging.getLogger("rekordbox_edit")
    pkg_logger.setLevel(logging.DEBUG)
    pkg_logger.propagate = False

    for handler in pkg_logger.handlers[:]:
        handler.close()
        pkg_logger.removeHandler(handler)

    if log_file:
        _debug_file_path = Path(log_file)
    else:
        _debug_file_path = _APP_DIR / LOG_FILE_NAME
    _debug_file_path.parent.mkdir(parents=True, exist_ok=True)

    file_handler = logging.FileHandler(_debug_file_path, mode="a", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s - %(name)s:%(funcName)s:%(lineno)d - %(levelname)s: %(message)s"
        )
    )
    pkg_logger.addHandler(file_handler)

    # Add pyrekordbox loggers to debug log file:
    manager = logging.root.manager
    for name in manager.loggerDict:
        lgr = logging.getLogger(name)
        if name.startswith("pyrekordbox") and isinstance(lgr, logging.Logger):
            lgr.addHandler(file_handler)
    # silence the pyrekordbox logger that warns about RB being open--we do that when necessary ourselves
    pyrekordbox_logger = logging.getLogger("pyrekordbox.db6.database")
    pyrekordbox_logger.propagate = False

    _console_handler = ConsoleLogHandler()
    _console_handler.setLevel(logging.INFO)
    _console_handler.setFormatter(logging.Formatter("%(message)s"))
    pkg_logger.addHandler(_console_handler)


def _flush_handlers() -> None:
    for handler in logging.getLogger("rekordbox_edit").handlers:
        handler.flush()


atexit.register(_flush_handlers)
