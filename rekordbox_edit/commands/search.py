"""Search command for rekordbox-edit."""

import logging
import sys
from typing import List

import click
from pyrekordbox import Rekordbox6Database

from rekordbox_edit._click import (
    PrintChoice,
    add_click_options,
    global_click_filters,
    print_option,
    track_ids_argument,
)
from rekordbox_edit.logger import get_debug_file_path, set_level
from rekordbox_edit.query import get_filtered_content
from rekordbox_edit.utils import (
    print_track_info,
)

logger = logging.getLogger(__name__)


@click.command(
    epilog=f"Debug logs for each run can be found at:\n{get_debug_file_path().parent}"
)
@add_click_options([*global_click_filters, print_option, track_ids_argument])
def search_command(
    track_id: List[str] | None,
    track_ids: List[str] | None,
    playlist: List[str] | None,
    exact_playlist: List[str] | None,
    album: List[str] | None,
    exact_album: List[str] | None,
    artist: List[str] | None,
    exact_artist: List[str] | None,
    title: List[str] | None,
    exact_title: List[str] | None,
    format: List[str] | None,
    match_all: bool,
    print_opt: PrintChoice | None,
):
    """Search the RekordBox database."""

    set_level(print_opt)

    if not sys.stdin.isatty():
        stdin_data = sys.stdin.read().strip()
        if stdin_data:
            track_ids = list(track_ids or []) + stdin_data.split()

    logger.debug("Connecting to RekordBox database...")

    # Log search parameters for troubleshooting
    filters = []
    if track_ids:
        filters.append(f"track_ids={track_ids}")
    if track_id:
        filters.append(f"track_id={track_id}")
    if artist:
        filters.append(f"artist={artist}")
    if exact_artist:
        filters.append(f"exact_artist={exact_artist}")
    if title:
        filters.append(f"title={title}")
    if exact_title:
        filters.append(f"exact_title={exact_title}")
    if album:
        filters.append(f"album={album}")
    if exact_album:
        filters.append(f"exact_album={exact_album}")
    if playlist:
        filters.append(f"playlist={playlist}")
    if exact_playlist:
        filters.append(f"exact_playlist={exact_playlist}")
    if format:
        filters.append(f"format={format}")
    if match_all:
        filters.append("match_all=True")
    logger.debug(f"Search filters: {', '.join(filters) if filters else 'none'}")

    db = Rekordbox6Database()
    if not db.session:
        raise RuntimeError("Failed to connect to Rekordbox Database: No Session.")

    filtered_result = get_filtered_content(
        db,
        track_id_args=track_ids,
        track_ids=track_id,
        playlists=playlist,
        exact_playlists=exact_playlist,
        artists=artist,
        exact_artists=exact_artist,
        albums=album,
        exact_albums=exact_album,
        titles=title,
        exact_titles=exact_title,
        formats=format,
        match_all=match_all,
    )

    if print_opt is PrintChoice.SILENT:
        pass
    elif print_opt is PrintChoice.IDS:
        print(" ".join(content.ID for content in filtered_result.scalars().all()))
    else:
        print_track_info(filtered_result.scalars().all())
