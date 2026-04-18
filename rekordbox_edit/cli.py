#!/usr/bin/env python3
"""Command line interface for rekordbox-edit."""

import logging
import sys

import click

from rekordbox_edit.commands.convert import convert_command
from rekordbox_edit.commands.search import search_command
from rekordbox_edit.logger import get_debug_file_path, setup_logging

logger = logging.getLogger(__name__)


@click.group(
    epilog=f"Debug logs for each run can be found at:\n{get_debug_file_path().parent}"
)
@click.version_option()
def cli():
    """RekordBox Bulk Edit - Tools for bulk editing RekordBox database records."""
    pass


cli.add_command(search_command)
cli.add_command(
    convert_command,
)


def main():
    """Entry point for the CLI."""
    try:
        setup_logging()
        logger.debug(f"Running with input: {' '.join(sys.argv)}")
        cli()
    except KeyboardInterrupt:
        logger.debug("User killed the process.")
    except Exception as e:
        logger.critical("Unhandled exception occured:", exc_info=e)
        logger.info(
            f"Please report this issue to https://github.com/jviall/rekordbox-edit/issues with the debug file for this run: {get_debug_file_path().absolute().as_uri()}",
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
