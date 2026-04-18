from enum import Enum

import click


class PrintChoice(Enum):
    SILENT = 0
    IDS = 1
    INFO = 2
    DEBUG = 3


print_option = click.option(
    "--print",
    "print_opt",  # avoid shadowing the print() function
    default="info",
    type=click.Choice(PrintChoice, case_sensitive=False),
    help="Configures the kind of console output you want from the command, if any. The 'ids' option can be used to pipe a list of resulting content IDs into to another command.",
)

track_ids_argument = click.argument("track-ids", type=str, required=False, nargs=-1)

global_click_filters = [
    click.option(
        "--track-id",
        type=str,
        multiple=True,
        help="Filter by the given Database Track ID",
    ),
    click.option(
        "--title",
        type=str,
        multiple=True,
        help="Find track names that include this value",
    ),
    click.option(
        "--exact-title",
        type=str,
        multiple=True,
        help="Find track names that are exactly this value",
    ),
    click.option(
        "--playlist",
        type=str,
        multiple=True,
        help="Find tracks in playlists whose names include this value",
    ),
    click.option(
        "--exact-playlist",
        type=str,
        multiple=True,
        help="Find tracks in the plalist whose name is exactly this value",
    ),
    click.option(
        "--artist",
        type=str,
        multiple=True,
        help="Find tracks whose Artist names include this value",
    ),
    click.option(
        "--exact-artist",
        type=str,
        multiple=True,
        help="Find tracks whose Artists names are exactly this value",
    ),
    click.option(
        "--album",
        type=str,
        multiple=True,
        help="Find tracks whose Album names include this value",
    ),
    click.option(
        "--exact-album",
        type=str,
        multiple=True,
        help="Find tracks whose Album names are exactly this value",
    ),
    click.option(
        "--format",
        type=click.Choice(["mp3", "flac", "aiff", "wav", "m4a"], case_sensitive=False),
        multiple=True,
        help="Find tracks of this format",
    ),
    click.option(
        "--match-all",
        type=bool,
        is_flag=True,
        help="Results must match all given filters",
    ),
]


def add_click_options(options):
    def _add_options(func):
        for option in reversed(options):
            func = option(func)
        return func

    return _add_options
