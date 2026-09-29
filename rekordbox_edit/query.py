import logging
import os
from pathlib import Path, PurePath, PureWindowsPath
from collections.abc import Collection
from typing import List, Literal, Tuple, Union

from pyrekordbox import Rekordbox6Database
from pyrekordbox.db6.tables import (
    DjmdAlbum,
    DjmdArtist,
    DjmdContent,
    DjmdPlaylist,
    DjmdSongPlaylist,
)
from sqlalchemy import ColumnElement, Result, and_, func, or_, select
from sqlalchemy.orm import Session, aliased

from rekordbox_edit.errors import DatabaseNotConnectedError
from rekordbox_edit.models import FilterArgs

_logger = logging.getLogger(__name__)

MatchMode = Literal["grouped", "all", "any"]


def require_session(db: Rekordbox6Database) -> Session:
    """The database's open session, narrowed from `Session | None`."""
    if not db.session:
        raise DatabaseNotConnectedError(
            "Failed to connect to Rekordbox Database: No Session."
        )
    return db.session


class CollectionQuery:
    def __init__(self, mode: MatchMode = "grouped"):
        self._stmt = select(DjmdContent)
        self._conditions: dict[str, list[ColumnElement[bool]]] = {}
        self._limit_count = None
        self._last_count = None
        self._mode: MatchMode = mode

    @property
    def _flat_conditions(self) -> list[ColumnElement[bool]]:
        """Every condition across every filter-kind bucket, as one flat list."""
        return [c for conditions in self._conditions.values() for c in conditions]

    def _copy(self) -> "CollectionQuery":
        """Create a copy of this query in its current state."""
        new_inst = CollectionQuery.__new__(CollectionQuery)
        new_inst._stmt = self._stmt._clone()
        new_inst._conditions = {
            group: conditions.copy() for group, conditions in self._conditions.items()
        }
        new_inst._limit_count = self._limit_count
        new_inst._last_count = self._last_count
        new_inst._mode = self._mode
        return new_inst

    def _append_condition(self, group: str, condition: ColumnElement[bool]) -> None:
        self._conditions.setdefault(group, []).append(condition)

    def match_any(self) -> "CollectionQuery":
        """Flatten every condition, across every filter kind, into one OR."""
        new_inst = self._copy()
        new_inst._mode = "any"
        return new_inst

    def match_all(self) -> "CollectionQuery":
        """Flatten every condition, across every filter kind, into one AND."""
        new_inst = self._copy()
        new_inst._mode = "all"
        return new_inst

    def by_track_ids(self, track_ids: Union[str, List[str]]) -> "CollectionQuery":
        """Filter by specific track ID(s)."""
        new_inst = self._copy()
        if isinstance(track_ids, str):
            track_ids = [track_ids]
        new_inst._append_condition("track_id", DjmdContent.ID.in_(track_ids))
        return new_inst

    def by_artist(self, artist_name: str, exact: bool = False) -> "CollectionQuery":
        """Filter by artist name."""

        new_inst = self._copy()
        ArtistAlias = aliased(DjmdArtist)
        new_inst._stmt = new_inst._stmt.outerjoin(
            ArtistAlias, DjmdContent.ArtistID == ArtistAlias.ID
        )

        if not artist_name:
            condition = ArtistAlias.Name.is_(None)
        elif exact:
            condition = ArtistAlias.Name == artist_name
        else:
            condition = ArtistAlias.Name.ilike(f"%{artist_name}%")

        new_inst._append_condition("artist", condition)
        return new_inst

    def by_title(self, title: str, exact: bool = False) -> "CollectionQuery":
        """Filter by track name."""

        new_inst = self._copy()

        if not title:
            condition = DjmdContent.Title.is_(None)
        elif exact:
            condition = DjmdContent.Title == title
        else:
            condition = DjmdContent.Title.ilike(f"%{title}%")

        new_inst._append_condition("title", condition)
        return new_inst

    def by_album(self, album_name: str, exact: bool = False) -> "CollectionQuery":
        """Filter by album name."""

        new_inst = self._copy()
        AlbumAlias = aliased(DjmdAlbum)
        new_inst._stmt = new_inst._stmt.outerjoin(
            AlbumAlias, DjmdContent.AlbumID == AlbumAlias.ID
        )

        if not album_name:
            condition = DjmdContent.AlbumID.is_(None)
        elif exact:
            condition = AlbumAlias.Name == album_name
        else:
            condition = AlbumAlias.Name.ilike(f"%{album_name}%")

        new_inst._append_condition("album", condition)
        return new_inst

    def by_playlist(self, playlist_name: str, exact: bool = False) -> "CollectionQuery":
        """Filter by playlist name."""

        new_inst = self._copy()
        PlaylistAlias = aliased(DjmdPlaylist)
        SongPlaylistAlias = aliased(DjmdSongPlaylist)

        new_inst._stmt = new_inst._stmt.outerjoin(
            SongPlaylistAlias, DjmdContent.ID == SongPlaylistAlias.ContentID
        ).outerjoin(PlaylistAlias, SongPlaylistAlias.PlaylistID == PlaylistAlias.ID)

        if not playlist_name:
            condition = SongPlaylistAlias.ContentID.is_(None)
        elif exact:
            condition = PlaylistAlias.Name == playlist_name
        else:
            condition = PlaylistAlias.Name.ilike(f"%{playlist_name}%")

        new_inst._append_condition("playlist", condition)
        return new_inst

    def by_format(self, format_name: str) -> "CollectionQuery":
        """Filter by file format."""
        from rekordbox_edit.utils import get_file_type_codes_for_format

        if not format_name:
            _logger.warning("Empty format filter has no effect")
            return self

        new_inst = self._copy()

        try:
            file_type_codes = get_file_type_codes_for_format(format_name)
            condition = DjmdContent.FileType.in_(file_type_codes)
            new_inst._append_condition("format", condition)
        except ValueError:
            _logger.warning(f"Invalid format: {format_name}")
        return new_inst

    def by_path(self, path_str: str, resolved: bool = False) -> "CollectionQuery":
        """Filter by case-insensitive substring of the track's file path.
        FolderPath holds the full path to the file, including its name and
        extension.

        Separators get normalized to posix format, and a trailing '/' is kept
        so the substring only matches directory components.
        --path args match as given.
        --resolved-path args are made absolute against the working directory
        by pure string math (no filesystem access), so casing stays as typed
        and symlinks are never followed.
        """
        if not path_str:
            return self

        new_inst = self._copy()
        has_trailing_sep = path_str.endswith(("/", "\\"))

        if resolved:
            pattern = Path(os.path.abspath(path_str)).as_posix()
            if has_trailing_sep and not pattern.endswith("/"):
                pattern += "/"
        else:
            pattern = path_str.replace("\\", "/")

        new_inst._append_condition("path", DjmdContent.FolderPath.ilike(f"%{pattern}%"))
        return new_inst

    def limit(self, count: int) -> "CollectionQuery":
        """Limit query results to the first {count} items."""
        new_inst = self._copy()
        new_inst._limit_count = count
        return new_inst

    def last(self, count: int) -> "CollectionQuery":
        """Limit query results to the last {count} items, kept in canonical order."""
        new_inst = self._copy()
        new_inst._last_count = count
        return new_inst

    def count(self, db: Rekordbox6Database) -> int:
        """Get a count of the query's results on the given database instance."""
        session = require_session(db)
        stmt = self._get_full_statement()
        count_stmt = select(func.count()).select_from(stmt.subquery())
        return session.execute(count_stmt).scalar_one()

    def execute(
        self,
        db: Rekordbox6Database,
    ) -> Result[Tuple[DjmdContent]]:
        """Execute the query on the given database instance and return results."""
        session = require_session(db)
        stmt = self._get_full_statement()
        _logger.debug(f"Executing Query:\n{str(stmt)}")
        return session.execute(stmt)

    def _get_full_statement(self):
        """Return the final statement with all expressions applied."""
        stmt = self._stmt

        if self._conditions:
            if self._mode == "all":
                _logger.debug(
                    f"Building query with {len(self._flat_conditions)} condition(s) using flat AND logic"
                )
                combined_condition = and_(*self._flat_conditions)
            elif self._mode == "any":
                _logger.debug(
                    f"Building query with {len(self._flat_conditions)} condition(s) using flat OR logic"
                )
                combined_condition = or_(*self._flat_conditions)
            else:
                _logger.debug(
                    f"Building query with {len(self._conditions)} filter group(s) using grouped AND-of-OR logic"
                )
                group_conditions = [
                    or_(*conditions) for conditions in self._conditions.values()
                ]
                combined_condition = and_(*group_conditions)
            stmt = stmt.where(combined_condition)

        if self._last_count is not None:
            _logger.debug(f"Query last: {self._last_count}")
            tail = (
                stmt.order_by(DjmdContent.FolderPath.desc(), DjmdContent.ID.desc())
                .limit(self._last_count)
                .subquery()
            )
            tail_content = aliased(DjmdContent, tail)
            return select(tail_content).order_by(
                tail_content.FolderPath.asc(), tail_content.ID.asc()
            )

        stmt = stmt.order_by(DjmdContent.FolderPath.asc(), DjmdContent.ID.asc())

        if self._limit_count is not None:
            _logger.debug(f"Query limit: {self._limit_count}")
            stmt = stmt.limit(self._limit_count)

        return stmt


def get_filtered_content(
    db: Rekordbox6Database,
    filters: FilterArgs,
) -> Result[Tuple[DjmdContent]]:
    """Query the Rekordbox database with the provided filters."""
    db = db if db is not None else Rekordbox6Database()
    require_session(db)

    query = CollectionQuery()

    if filters.track_ids:
        _logger.debug(f"Filtering by {len(filters.track_ids)} track ID argument(s)")
        query = query.by_track_ids(track_ids=filters.track_ids)

    for tid in filters.track_id:
        query = query.by_track_ids(tid)

    for fmt in filters.format:
        query = query.by_format(fmt)

    for playlist in filters.playlist:
        query = query.by_playlist(playlist)

    for exact_playlist in filters.exact_playlist:
        query = query.by_playlist(exact_playlist, exact=True)

    for artist in filters.artist:
        query = query.by_artist(artist)

    for exact_artist in filters.exact_artist:
        query = query.by_artist(exact_artist, exact=True)

    for album in filters.album:
        query = query.by_album(album)

    for exact_album in filters.exact_album:
        query = query.by_album(exact_album, exact=True)

    for title in filters.title:
        query = query.by_title(title)

    for title in filters.exact_title:
        query = query.by_title(title, exact=True)

    for path in filters.path:
        query = query.by_path(path)

    for resolved_path in filters.resolved_path:
        query = query.by_path(resolved_path, resolved=True)

    if filters.match_all:
        query = query.match_all()
    elif filters.match_any:
        query = query.match_any()

    if filters.first is not None:
        query = query.limit(filters.first)

    if filters.last is not None:
        query = query.last(filters.last)

    return query.execute(db)


def normalize_path(path: str) -> str:
    """A path in the form Rekordbox stores: absolute, symlinks resolved,
    forward-slashed. Rekordbox records the resolved form, so /tmp becomes
    /private/tmp on macOS. A Windows drive letter survives resolution, since
    Rekordbox cannot open the UNC share behind a mapped network drive.
    """
    resolved = Path(path).resolve()
    # splitdrive over abspath, not over `resolved`: abspath makes a relative
    # path absolute without following the mapping, so the drive letter the
    # caller meant is still there to compare against. It is always "" off
    # Windows, which short-circuits everything below.
    drive = os.path.splitdrive(os.path.abspath(path))[0]
    if not drive or drive == resolved.drive or drive.startswith("\\\\"):
        return resolved.as_posix()
    try:
        target = Path(drive + os.sep).resolve()
    except OSError as e:
        _logger.debug(f"could not resolve what drive {drive} points at: {e}")
        return resolved.as_posix()
    return _restore_drive_letter(resolved, drive, target)


def _restore_drive_letter(resolved: PurePath, drive: str, target: PurePath) -> str:
    """`resolved` moved back onto `drive`, which is mapped to `target`.

    Path.resolve() follows a mapped network drive (M: -> //host/share) and a
    subst drive the way it follows a symlink. Rekordbox stores and plays the
    drive-letter form and cannot open the UNC share, so only the mapping is
    undone; a symlink resolved deeper in the path stays resolved.
    """
    try:
        tail = resolved.relative_to(target)
    except ValueError:
        _logger.debug(f"{resolved} does not sit under {target}, the target of {drive}")
        return resolved.as_posix()
    return PureWindowsPath(drive + "\\", tail).as_posix()


def find_content_by_key(
    db: Rekordbox6Database, keys: Collection[str]
) -> dict[str, DjmdContent]:
    """Existing rows for any of `keys`, where a key is a case-folded
    normalize_path() result.

    Case folding is what lets a lookup match a row Rekordbox stored under a
    different case than the live filesystem reports, since Path.resolve()
    does not correct case on macOS. The comparison runs in Python rather than
    SQL because SQLite's LOWER() is ASCII-only.
    """
    session = require_session(db)
    if not keys:
        return {}
    wanted = set(keys)
    found: dict[str, DjmdContent] = {}
    for content in session.execute(select(DjmdContent)).scalars():
        key = (content.FolderPath or "").replace("\\", "/").casefold()
        if key in wanted:
            found[key] = content
    _logger.debug(f"path lookup matched {len(found)} of {len(wanted)} candidate(s)")
    return found


def find_content_by_ids(
    db: Rekordbox6Database, ids: Collection[str]
) -> dict[str, DjmdContent]:
    """Rows for `ids`, keyed by ID as a string. IDs with no row are absent."""
    if not ids:
        return {}
    session = require_session(db)
    rows = session.execute(
        select(DjmdContent).where(DjmdContent.ID.in_(list(ids)))
    ).scalars()
    found = {str(row.ID): row for row in rows}
    _logger.debug(f"id lookup matched {len(found)} of {len(set(ids))} requested row(s)")
    return found


def find_playlists_by_name(db: Rekordbox6Database, name: str) -> list[DjmdPlaylist]:
    """Normal playlists whose name matches case-insensitively.

    Excludes folders and smart playlists (Attribute != 0): they cannot take
    add_to_playlist, and a folder sharing a name with a real playlist would
    otherwise report a spurious ambiguity.
    """
    session = require_session(db)
    target = name.casefold()
    return [
        p
        for p in session.execute(select(DjmdPlaylist)).scalars()
        if (p.Name or "").casefold() == target and p.Attribute == 0
    ]
