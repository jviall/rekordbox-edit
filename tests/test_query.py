#!/usr/bin/env python3
"""Tests for the CollectionQuery class."""

import os
import platform
import subprocess
from contextlib import contextmanager
from pathlib import Path, PureWindowsPath
from unittest.mock import MagicMock

import pytest
from sqlalchemy import ColumnElement

from rekordbox_edit.models import FilterArgs
from rekordbox_edit.query import (
    CollectionQuery,
    find_content_by_ids,
    find_content_by_key,
    find_playlists_by_name,
    get_filtered_content,
    normalize_path,
    _restore_drive_letter,
)


def _compile(condition: ColumnElement[bool]) -> str:
    return str(condition.compile(compile_kwargs={"literal_binds": True}))


@contextmanager
def _subst_drive(target: Path):
    """Map the first free drive letter to `target` for the duration of the
    block. subst is a per-session mapping: it creates no files and leaves
    nothing behind once detached."""
    drive = next(
        (f"{letter}:" for letter in "ZYXWV" if not os.path.exists(f"{letter}:/")),
        None,
    )
    if drive is None:
        pytest.skip("no free drive letter to map")
    subprocess.run(["subst", drive, str(target)], check=True)
    try:
        yield drive
    finally:
        subprocess.run(["subst", drive, "/D"], check=True)


class TestCollectionQuery:
    """Test the CollectionQuery class."""

    def test_init(self):
        """Test that new instances select the DjmdContent table and initialize fields."""
        query = CollectionQuery()

        # Check that the statement selects from DjmdContent
        assert str(query._stmt).lower().find("djmdcontent") != -1

        # Check initial state
        assert query._conditions == {}
        assert query._limit_count is None
        assert query._mode == "grouped"

        # Test with an explicit mode
        query_all = CollectionQuery(mode="all")
        assert query_all._mode == "all"

    def test_match_any(self):
        """Test that match_any() sets the flat OR mode."""
        query = CollectionQuery(mode="all")

        new_query = query.match_any()

        # Should return a new instance
        assert new_query is not query
        assert new_query._mode == "any"
        # Original should be unchanged
        assert query._mode == "all"

    def test_match_all(self):
        """Test that match_all() sets the flat AND mode."""
        query = CollectionQuery()

        new_query = query.match_all()

        # Should return a new instance
        assert new_query is not query
        assert new_query._mode == "all"
        # Original should be unchanged
        assert query._mode == "grouped"

    def test_by_title_and_exact_title_share_a_bucket(self):
        """Plain and exact variants of the same filter land in the same
        group, so they OR together under the default grouped mode."""
        query = CollectionQuery().by_title("A").by_title("B", exact=True)
        assert len(query._conditions["title"]) == 2
        assert len(query._conditions) == 1

    def test_different_filter_kinds_use_separate_buckets(self):
        """Different filter kinds land in separate groups."""
        query = CollectionQuery().by_title("A").by_format("flac")
        assert set(query._conditions.keys()) == {"title", "format"}

    def test_by_artist(self):
        """Test that the by_artist method outer-joins with the DjmdArtist table and
        adds an ilike condition on the DjmdArtist.Name field."""
        query = CollectionQuery()
        artist_name = "Test Artist"

        new_query = query.by_artist(artist_name)

        # Should return a new instance
        assert new_query is not query

        # Check that a condition was added
        assert len(new_query._flat_conditions) == 1

        # Check that the statement includes a join
        stmt_str = str(new_query._stmt).lower()
        assert "left outer join" in stmt_str or "outer join" in stmt_str
        assert "djmdartist" in stmt_str

        # Check that the condition is an ilike operation
        condition_str = str(new_query._flat_conditions[0]).lower()
        print(condition_str)
        assert "like lower" in condition_str
        assert '."name"' in condition_str.lower()

    def test_by_exact_artist(self):
        """Test that the by_artist method outer-joins with the DjmdArtist table and
        adds an == condition on the DjmdArtist.Name field when exact is True."""
        query = CollectionQuery()
        artist_name = "Exact Artist"

        new_query = query.by_artist(artist_name, exact=True)

        # Should return a new instance
        assert new_query is not query

        # Check that a condition was added
        assert len(new_query._flat_conditions) == 1

        # Check that the statement includes a join
        stmt_str = str(new_query._stmt).lower()
        assert "left outer join" in stmt_str or "outer join" in stmt_str
        assert "djmdartist" in stmt_str

        # Check that the condition is an equality operation (not ilike)
        condition_str = str(new_query._flat_conditions[0]).lower()
        assert "like lower" not in condition_str
        assert "=" in condition_str

    def test_by_title(self):
        """Test that the by_title method does not modify the statement and
        adds an ilike condition on the Title field."""
        query = CollectionQuery()
        title = "Test Title"

        original_stmt_str = str(query._stmt)
        new_query = query.by_title(title)

        # Should return a new instance
        assert new_query is not query

        # Check that a condition was added
        assert len(new_query._flat_conditions) == 1

        # Statement should not have additional joins (only the original select)
        new_stmt_str = str(new_query._stmt)
        assert new_stmt_str == original_stmt_str

        # Check that the condition is an ilike operation on Title
        condition_str = str(new_query._flat_conditions[0]).lower()
        assert "like lower" in condition_str
        assert "title" in condition_str

    def test_by_exact_title(self):
        """Test that the by_title method does not modify the statement and
        adds an == condition on the Title field when exact is True."""
        query = CollectionQuery()
        title = "Exact Title"

        original_stmt_str = str(query._stmt)
        new_query = query.by_title(title, exact=True)

        # Should return a new instance
        assert new_query is not query

        # Check that a condition was added
        assert len(new_query._flat_conditions) == 1

        # Statement should not have additional joins
        new_stmt_str = str(new_query._stmt)
        assert new_stmt_str == original_stmt_str

        # Check that the condition is an equality operation (not ilike)
        condition_str = str(new_query._flat_conditions[0]).lower()
        assert "like lower" not in condition_str
        assert "=" in condition_str
        assert "title" in condition_str

    def test_by_album(self):
        """Test that the by_album method outer-joins with the DjmdAlbum table and
        adds an ilike condition on the DjmdAlbum.Name field."""
        query = CollectionQuery()
        album_name = "Test Album"

        new_query = query.by_album(album_name)

        # Should return a new instance
        assert new_query is not query

        # Check that a condition was added
        assert len(new_query._flat_conditions) == 1

        # Check that the statement includes an outer join
        stmt_str = str(new_query._stmt).lower()
        assert "left outer join" in stmt_str or "outer join" in stmt_str
        assert "djmdalbum" in stmt_str

        # Check that the condition is an ilike operation
        condition_str = str(new_query._flat_conditions[0]).lower()
        assert "like lower" in condition_str

    def test_by_exact_album(self):
        """Test that the by_album method outer-joins with the DjmdAlbum table and
        adds an == condition on the DjmdAlbum.Name field when exact is True."""
        query = CollectionQuery()
        album_name = "Exact Album"

        new_query = query.by_album(album_name, exact=True)

        # Should return a new instance
        assert new_query is not query

        # Check that a condition was added
        assert len(new_query._flat_conditions) == 1

        # Check that the statement includes an outer join
        stmt_str = str(new_query._stmt).lower()
        assert "left outer join" in stmt_str or "outer join" in stmt_str
        assert "djmdalbum" in stmt_str

        # Check that the condition is an equality operation (not ilike)
        condition_str = str(new_query._flat_conditions[0]).lower()
        assert "like lower" not in condition_str
        assert "=" in condition_str

    def test_by_playlist(self):
        """Test that the by_playlist method outer-joins with the DjmdPlaylist and DjmdSongPlaylist
        tables and adds an ilike condition on the DjmdPlaylist.Name field."""
        query = CollectionQuery()
        playlist_name = "Test Playlist"

        new_query = query.by_playlist(playlist_name)

        # Should return a new instance
        assert new_query is not query

        # Check that a condition was added
        assert len(new_query._flat_conditions) == 1

        # Check that the statement includes outer joins with both tables
        stmt_str = str(new_query._stmt).lower()
        assert "left outer join" in stmt_str or "outer join" in stmt_str
        assert "djmdsongplaylist" in stmt_str
        assert "djmdplaylist" in stmt_str

        # Check that the condition is an ilike operation
        condition_str = str(new_query._flat_conditions[0]).lower()
        assert "like lower" in condition_str

    def test_by_exact_playlist(self):
        """Test that the by_playlist method outer-joins with the DjmdPlaylist table and
        adds an == condition on the DjmdPlaylist.Name field when exact is True."""
        query = CollectionQuery()
        playlist_name = "Exact Playlist"

        new_query = query.by_playlist(playlist_name, exact=True)

        # Should return a new instance
        assert new_query is not query

        # Check that a condition was added
        assert len(new_query._flat_conditions) == 1

        # Check that the statement includes outer joins with both tables
        stmt_str = str(new_query._stmt).lower()
        assert "left outer join" in stmt_str or "outer join" in stmt_str
        assert "djmdsongplaylist" in stmt_str
        assert "djmdplaylist" in stmt_str

        # Check that the condition is an equality operation (not ilike)
        condition_str = str(new_query._flat_conditions[0]).lower()
        assert "like lower" not in condition_str
        assert "=" in condition_str

    def test_by_format(self, mocker):
        """Test that the by_format method does not modify the statement and
        adds an IN condition on the DjmdContent.FileType field."""
        mock_get_codes = mocker.patch(
            "rekordbox_edit.utils.get_file_type_codes_for_format"
        )
        mock_get_codes.return_value = {5}

        query = CollectionQuery()
        format_name = "FLAC"

        original_stmt_str = str(query._stmt)
        new_query = query.by_format(format_name)

        # Should return a new instance
        assert new_query is not query

        # Check that a condition was added
        assert len(new_query._flat_conditions) == 1

        # Statement should not have additional joins
        new_stmt_str = str(new_query._stmt)
        assert new_stmt_str == original_stmt_str

        # Check that the condition is an IN over FileType
        condition_str = str(new_query._flat_conditions[0]).lower()
        assert "filetype" in condition_str
        assert "in" in condition_str

        # Verify the helper function was called
        mock_get_codes.assert_called_once_with(format_name)

    def test_copy(self):
        """ """
        query = CollectionQuery()
        query_copy = query._copy()

        assert query_copy._mode == query._mode
        assert query_copy._conditions == query._conditions
        assert query_copy._limit_count == query._limit_count
        assert str(query_copy._stmt) == str(query._stmt)
        assert str(query_copy._get_full_statement()) == str(query._get_full_statement())

    def test_copy_with_filters(self):
        """ """
        query = CollectionQuery()
        query.by_album("Discovery").by_format("flac").by_format("aiff").by_title("")
        query_copy = query._copy()

        assert query_copy._mode == query._mode
        assert query_copy._conditions == query._conditions
        assert query_copy._limit_count == query._limit_count
        assert str(query_copy._stmt) == str(query._stmt)
        assert str(query_copy._get_full_statement()) == str(query._get_full_statement())

    def test_by_track_ids_single_string(self):
        """A single string ID is accepted and results in an IN condition."""
        query = CollectionQuery()
        new_query = query.by_track_ids("123")

        assert new_query is not query
        assert len(new_query._flat_conditions) == 1
        condition_str = str(new_query._flat_conditions[0]).lower()
        assert "in" in condition_str

    def test_by_track_ids_list(self):
        """A list of IDs results in a single IN condition."""
        query = CollectionQuery()
        new_query = query.by_track_ids(["123", "456", "789"])

        assert new_query is not query
        assert len(new_query._flat_conditions) == 1
        condition_str = str(new_query._flat_conditions[0]).lower()
        assert "in" in condition_str

    def test_by_artist_empty_string(self):
        """Empty artist name adds an IS NULL condition."""
        query = CollectionQuery()
        new_query = query.by_artist("")

        assert len(new_query._flat_conditions) == 1
        condition_str = str(new_query._flat_conditions[0]).lower()
        assert "null" in condition_str

    def test_by_title_empty_string(self):
        """Empty title adds an IS NULL condition."""
        query = CollectionQuery()
        new_query = query.by_title("")

        assert len(new_query._flat_conditions) == 1
        condition_str = str(new_query._flat_conditions[0]).lower()
        assert "null" in condition_str

    def test_by_album_empty_string(self):
        """Empty album name adds an IS NULL condition."""
        query = CollectionQuery()
        new_query = query.by_album("")

        assert len(new_query._flat_conditions) == 1
        condition_str = str(new_query._flat_conditions[0]).lower()
        assert "null" in condition_str

    def test_by_playlist_empty_string(self):
        """Empty playlist name adds an IS NULL condition for tracks not in any playlist."""
        query = CollectionQuery()
        new_query = query.by_playlist("")

        assert len(new_query._flat_conditions) == 1
        condition_str = str(new_query._flat_conditions[0]).lower()
        assert "null" in condition_str

    def test_by_format_empty_string(self, mocker):
        """Empty format string logs a warning and returns self unchanged."""
        mock_warn = mocker.patch("rekordbox_edit.query._logger")
        query = CollectionQuery()
        result = query.by_format("")

        assert result is query
        assert len(result._flat_conditions) == 0
        mock_warn.warning.assert_called_once()

    def test_by_format_invalid(self, mocker):
        """Invalid format logs a warning and returns a copy without adding a condition."""
        mocker.patch(
            "rekordbox_edit.utils.get_file_type_codes_for_format",
            side_effect=ValueError("unknown format"),
        )
        mock_warn = mocker.patch("rekordbox_edit.query._logger")
        query = CollectionQuery()
        new_query = query.by_format("xyz")

        assert new_query is not query
        assert len(new_query._flat_conditions) == 0
        mock_warn.warning.assert_called_once()

    def test_limit(self):
        """limit() sets _limit_count and returns a new instance."""
        query = CollectionQuery()
        new_query = query.limit(10)

        assert new_query is not query
        assert new_query._limit_count == 10
        assert query._limit_count is None

    def test_limit_in_sql(self):
        """limit() results in a LIMIT clause in the final statement."""
        query = CollectionQuery().limit(5)
        stmt_str = str(query._get_full_statement()).lower()
        assert "limit" in stmt_str

    def test_last(self):
        """last() sets _last_count and returns a new instance."""
        query = CollectionQuery()
        new_query = query.last(10)

        assert new_query is not query
        assert new_query._last_count == 10
        assert query._last_count is None

    def test_copy_preserves_last(self):
        query = CollectionQuery().last(4)
        assert query._copy()._last_count == 4

    def test_last_in_sql(self):
        """last() wraps the statement in a desc-ordered LIMIT subquery and
        re-orders the outer select ascending, so the tail N rows come back in
        canonical FolderPath/ID order."""
        stmt_str = str(CollectionQuery().last(5)._get_full_statement()).lower()
        assert "limit" in stmt_str
        assert "desc" in stmt_str
        # Outer select re-orders the subquery rows ascending.
        assert stmt_str.rindex(" asc") > stmt_str.rindex("desc")

    def test_last_keeps_conditions(self):
        """Filter conditions apply inside the tail subquery."""
        stmt_str = str(
            CollectionQuery().by_title("A").last(5)._get_full_statement()
        ).lower()
        assert "where" in stmt_str
        assert "desc" in stmt_str

    def test_get_full_statement_no_conditions(self):
        """No conditions produces a statement with no WHERE clause."""
        query = CollectionQuery()
        stmt_str = str(query._get_full_statement()).lower()
        assert "where" not in stmt_str

    def test_get_full_statement_orders_by_folder_then_id(self):
        """Every statement orders by FolderPath then ID ascending. FolderPath
        groups tracks by directory for readable search output; ID is the
        tiebreaker that keeps results deterministic (snapshot/pipe contracts
        depend on this)."""
        unfiltered = str(CollectionQuery()._get_full_statement()).lower()
        filtered = str(CollectionQuery().by_title("A")._get_full_statement()).lower()
        for stmt_str in (unfiltered, filtered):
            assert "order by" in stmt_str
            assert '"djmdcontent"."folderpath" asc' in stmt_str
            assert '"djmdcontent"."id" asc' in stmt_str
            assert stmt_str.index('"folderpath"') < stmt_str.rindex('"id" asc')

    def test_get_full_statement_or_logic(self):
        """Repeated values of the same filter OR together by default."""
        query = CollectionQuery().by_title("A").by_title("B")
        stmt_str = str(query._get_full_statement()).lower()
        assert " or " in stmt_str
        assert " and " not in stmt_str

    def test_get_full_statement_and_logic(self):
        """match_all() flattens everything, including repeats, into one AND."""
        query = CollectionQuery().by_title("A").by_title("B").match_all()
        stmt_str = str(query._get_full_statement()).lower()
        assert " and " in stmt_str
        assert " or " not in stmt_str

    def test_get_full_statement_grouped_ands_across_filter_kinds(self):
        """Default grouped mode ORs same-kind values, then ANDs across kinds."""
        query = CollectionQuery().by_title("A").by_title("B").by_format("flac")
        stmt_str = str(query._get_full_statement()).lower()
        assert " and " in stmt_str
        assert " or " in stmt_str

    def test_get_full_statement_match_any_flattens_across_kinds(self):
        """match_any() flattens every condition, ignoring grouping, into one OR."""
        query = CollectionQuery().by_title("A").by_format("flac").match_any()
        stmt_str = str(query._get_full_statement()).lower()
        assert " or " in stmt_str
        assert " and " not in stmt_str

    def test_by_path_substring_against_folderpath_only(self):
        """A --path arg adds a single case-insensitive substring condition on
        FolderPath, which holds the full file path. FileNameL is never queried."""
        query = CollectionQuery()
        new_query = query.by_path("Daft Punk")

        assert new_query is not query
        assert len(new_query._flat_conditions) == 1
        condition_str = str(new_query._flat_conditions[0])
        assert "FolderPath" in condition_str
        assert "FileNameL" not in condition_str
        assert "LIKE lower" in condition_str

    def test_by_path_wraps_with_wildcards(self):
        """The substring pattern is wrapped in % wildcards."""
        query = CollectionQuery()
        new_query = query.by_path("track.mp3")

        condition_str = _compile(new_query._flat_conditions[0])
        assert "%track.mp3%" in condition_str

    def test_by_path_preserves_trailing_slash(self):
        """A trailing slash stays in the pattern so it only matches directory
        components, not filename prefixes."""
        query = CollectionQuery()
        new_query = query.by_path("Daft Punk/")

        condition_str = _compile(new_query._flat_conditions[0])
        assert "%Daft Punk/%" in condition_str

    def test_by_path_backslash_normalised_to_forward_slash(self):
        """Backslash separators in --path input are normalised to forward slashes."""
        query = CollectionQuery()
        new_query = query.by_path("Music\\Artist\\")

        condition_str = _compile(new_query._flat_conditions[0])
        assert "\\" not in condition_str
        assert "%Music/Artist/%" in condition_str

    def test_by_path_no_resolve(self):
        """by_path does NOT resolve the path."""
        query = CollectionQuery()
        new_query = query.by_path("../some/relative/track.mp3")

        condition_str = _compile(new_query._flat_conditions[0])
        # The raw string (or parts of it) must appear, not a resolved absolute path
        assert ".." in condition_str and "relative" in condition_str

    def test_by_path_empty_arg_adds_no_condition(self):
        """An empty --path arg is a no-op rather than matching everything."""
        query = CollectionQuery()
        new_query = query.by_path("")

        assert new_query._conditions == {}

    # --- by_path resolved mode ---

    def test_by_resolved_path_resolves_relative_path(self):
        """Resolved mode makes relative paths absolute against the cwd before querying."""
        cwd = Path(os.getcwd()).as_posix()
        query = CollectionQuery()
        new_query = query.by_path("Album/track.mp3", resolved=True)

        condition_str = _compile(new_query._flat_conditions[0])
        assert f"%{cwd}/Album/track.mp3%" in condition_str

    def test_by_resolved_path_substring_case_insensitive(self):
        """Resolved mode is a case-insensitive substring check on FolderPath,
        same as fuzzy mode, so a resolved folder path matches every track under it."""
        query = CollectionQuery()
        new_query = query.by_path("/Test/Artist/file.mp3", resolved=True)

        assert len(new_query._flat_conditions) == 1
        condition_str = str(new_query._flat_conditions[0])
        assert "FolderPath" in condition_str
        assert "FileNameL" not in condition_str
        assert "LIKE lower" in condition_str

    def test_by_resolved_path_is_lexical_and_preserves_casing(self):
        """Resolution is pure string math: even for a directory that exists on
        disk, the casing stays as typed instead of being rewritten to the
        on-disk casing (Path.resolve would rewrite it on Windows)."""
        miscased_cwd = Path(os.getcwd()).as_posix().swapcase()
        query = CollectionQuery()
        new_query = query.by_path(f"{miscased_cwd}/track.mp3", resolved=True)

        condition_str = _compile(new_query._flat_conditions[0])
        assert f"{miscased_cwd}/track.mp3" in condition_str

    def test_by_resolved_path_preserves_trailing_slash(self):
        """A trailing slash survives resolution so the pattern only matches
        directory components."""
        query = CollectionQuery()
        new_query = query.by_path("Album/", resolved=True)

        condition_str = _compile(new_query._flat_conditions[0])
        assert f"{Path(os.getcwd()).as_posix()}/Album/" in condition_str

    @pytest.mark.skipif(
        platform.system() != "Windows", reason="backslash path parsing is Windows-only"
    )
    def test_by_resolved_path_backslash_normalised_to_forward_slash(self):
        """Backslash separators in --resolved-path input are normalised via as_posix()."""
        query = CollectionQuery()
        # Pass a Windows-style absolute path; as_posix() must produce forward slashes
        new_query = query.by_path(
            "C:\\Users\\foo\\music\\Artist\\track.mp3", resolved=True
        )

        condition_str = _compile(new_query._flat_conditions[0])
        assert "\\" not in condition_str
        assert "C:/Users/foo/music/Artist/track.mp3" in condition_str

    def test_by_resolved_path_empty_arg_adds_no_condition(self):
        """An empty --resolved-path arg is a no-op rather than matching everything."""
        query = CollectionQuery()
        new_query = query.by_path("", resolved=True)

        assert new_query._conditions == {}

    def test_by_path_returns_new_instance(self):
        """by_path always returns a new CollectionQuery instance."""
        query = CollectionQuery()
        assert query.by_path("track.mp3") is not query
        assert query.by_path("track.mp3", resolved=True) is not query


@pytest.fixture
def mock_query(mocker):
    instance = MagicMock(spec=CollectionQuery)
    for method in [
        "by_track_ids",
        "by_artist",
        "by_title",
        "by_album",
        "by_playlist",
        "by_format",
        "match_all",
        "match_any",
        "limit",
        "last",
    ]:
        getattr(instance, method).return_value = instance
    mocker.patch("rekordbox_edit.query.CollectionQuery", return_value=instance)
    return instance


class TestGetFilteredContent:
    """Tests for the get_filtered_content function."""

    def test_no_filters(self, mock_db, mock_query):
        get_filtered_content(mock_db, FilterArgs())
        mock_query.by_track_ids.assert_not_called()
        mock_query.by_artist.assert_not_called()
        mock_query.by_title.assert_not_called()
        mock_query.by_album.assert_not_called()
        mock_query.by_playlist.assert_not_called()
        mock_query.by_format.assert_not_called()
        mock_query.match_all.assert_not_called()
        mock_query.execute.assert_called_once_with(mock_db)

    def test_track_id_args(self, mock_db, mock_query):
        get_filtered_content(mock_db, FilterArgs(track_ids=["123", "456"]))
        mock_query.by_track_ids.assert_called_once_with(track_ids=["123", "456"])

    def test_track_ids(self, mock_db, mock_query):
        get_filtered_content(mock_db, FilterArgs(track_id=["123", "456"]))
        assert mock_query.by_track_ids.call_count == 2
        mock_query.by_track_ids.assert_any_call("123")
        mock_query.by_track_ids.assert_any_call("456")

    def test_artist(self, mock_db, mock_query):
        get_filtered_content(mock_db, FilterArgs(artist=["Daft Punk"]))
        mock_query.by_artist.assert_called_once_with("Daft Punk")

    def test_multiple_artists(self, mock_db, mock_query):
        get_filtered_content(mock_db, FilterArgs(artist=["Daft Punk", "Justice"]))
        assert mock_query.by_artist.call_count == 2
        mock_query.by_artist.assert_any_call("Daft Punk")
        mock_query.by_artist.assert_any_call("Justice")

    def test_exact_artist(self, mock_db, mock_query):
        get_filtered_content(mock_db, FilterArgs(exact_artist=["Daft Punk"]))
        mock_query.by_artist.assert_called_once_with("Daft Punk", exact=True)

    def test_title(self, mock_db, mock_query):
        get_filtered_content(mock_db, FilterArgs(title=["One More Time"]))
        mock_query.by_title.assert_called_once_with("One More Time")

    def test_exact_title(self, mock_db, mock_query):
        get_filtered_content(mock_db, FilterArgs(exact_title=["One More Time"]))
        mock_query.by_title.assert_called_once_with("One More Time", exact=True)

    def test_album(self, mock_db, mock_query):
        get_filtered_content(mock_db, FilterArgs(album=["Discovery"]))
        mock_query.by_album.assert_called_once_with("Discovery")

    def test_exact_album(self, mock_db, mock_query):
        get_filtered_content(mock_db, FilterArgs(exact_album=["Discovery"]))
        mock_query.by_album.assert_called_once_with("Discovery", exact=True)

    def test_playlist(self, mock_db, mock_query):
        get_filtered_content(mock_db, FilterArgs(playlist=["My Playlist"]))
        mock_query.by_playlist.assert_called_once_with("My Playlist")

    def test_exact_playlist(self, mock_db, mock_query):
        get_filtered_content(mock_db, FilterArgs(exact_playlist=["My Playlist"]))
        mock_query.by_playlist.assert_called_once_with("My Playlist", exact=True)

    def test_path(self, mock_db, mock_query):
        get_filtered_content(mock_db, FilterArgs(path=["Music/track.mp3"]))
        mock_query.by_path.assert_called_once_with("Music/track.mp3")

    def test_resolved_path(self, mock_db, mock_query):
        get_filtered_content(mock_db, FilterArgs(resolved_path=["/Music/track.wav"]))
        mock_query.by_path.assert_called_once_with("/Music/track.wav", resolved=True)

    def test_format(self, mock_db, mock_query):
        get_filtered_content(mock_db, FilterArgs(format=["flac"]))
        mock_query.by_format.assert_called_once_with("flac")

    def test_multiple_formats(self, mock_db, mock_query):
        get_filtered_content(mock_db, FilterArgs(format=["flac", "aiff"]))
        assert mock_query.by_format.call_count == 2
        mock_query.by_format.assert_any_call("flac")
        mock_query.by_format.assert_any_call("aiff")

    def test_match_all(self, mock_db, mock_query):
        get_filtered_content(mock_db, FilterArgs(artist=["Daft Punk"], match_all=True))
        mock_query.match_all.assert_called_once()

    def test_default_no_match_all(self, mock_db, mock_query):
        get_filtered_content(mock_db, FilterArgs(artist=["Daft Punk"]))
        mock_query.match_all.assert_not_called()

    def test_match_any(self, mock_db, mock_query):
        get_filtered_content(mock_db, FilterArgs(artist=["Daft Punk"], match_any=True))
        mock_query.match_any.assert_called_once()
        mock_query.match_all.assert_not_called()

    def test_default_no_match_any(self, mock_db, mock_query):
        get_filtered_content(mock_db, FilterArgs(artist=["Daft Punk"]))
        mock_query.match_any.assert_not_called()

    def test_track_id_args_combined_with_format(self, mock_db, mock_query):
        """Positional track IDs should combine with other filters, not override them."""
        get_filtered_content(
            mock_db,
            FilterArgs(track_ids=["123"], format=["flac"], match_all=True),
        )
        mock_query.by_track_ids.assert_called_once_with(track_ids=["123"])
        mock_query.by_format.assert_called_once_with("flac")
        mock_query.match_all.assert_called_once()

    def test_track_id_args_combined_with_artist(self, mock_db, mock_query):
        """Piped IDs + artist filter with match_all narrows to artist within that ID set."""
        get_filtered_content(
            mock_db,
            FilterArgs(track_ids=["123", "456"], artist=["Justice"], match_all=True),
        )
        mock_query.by_track_ids.assert_called_once_with(track_ids=["123", "456"])
        mock_query.by_artist.assert_called_once_with("Justice")
        mock_query.match_all.assert_called_once()

    def test_track_id_args_and_with_artist_by_default(self, mock_db, mock_query):
        """Piped IDs AND artist filter narrow to their intersection by
        default, since track ID and artist are different filter kinds."""
        get_filtered_content(mock_db, FilterArgs(track_ids=["123"], artist=["Justice"]))
        mock_query.by_track_ids.assert_called_once_with(track_ids=["123"])
        mock_query.by_artist.assert_called_once_with("Justice")
        mock_query.match_all.assert_not_called()

    def test_first(self, mock_db, mock_query):
        get_filtered_content(mock_db, FilterArgs(first=5))
        mock_query.limit.assert_called_once_with(5)

    def test_no_first_skips_limit(self, mock_db, mock_query):
        get_filtered_content(mock_db, FilterArgs())
        mock_query.limit.assert_not_called()

    def test_last(self, mock_db, mock_query):
        get_filtered_content(mock_db, FilterArgs(last=3))
        mock_query.last.assert_called_once_with(3)

    def test_no_last_skips_last(self, mock_db, mock_query):
        get_filtered_content(mock_db, FilterArgs())
        mock_query.last.assert_not_called()

    def test_no_session_raises(self, mock_db):
        """get_filtered_content raises RuntimeError when db has no session."""
        mock_db.session = None

        with pytest.raises(RuntimeError, match="No Session"):
            get_filtered_content(mock_db, FilterArgs())


class TestCollectionQueryExecution:
    """Tests for the count() and execute() methods on CollectionQuery."""

    def test_count_returns_scalar(self):
        """count() executes a COUNT query and returns the scalar result."""
        mock_db = MagicMock()
        mock_db.session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 42
        mock_db.session.execute.return_value = mock_result

        count = CollectionQuery().count(mock_db)

        assert count == 42
        mock_db.session.execute.assert_called_once()

    def test_count_with_conditions(self):
        """count() works correctly when the query has filter conditions."""
        mock_db = MagicMock()
        mock_db.session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 7
        mock_db.session.execute.return_value = mock_result

        count = CollectionQuery().by_title("One More Time").count(mock_db)

        assert count == 7

    def test_count_no_session_raises(self):
        """count() raises RuntimeError when db has no session."""
        mock_db = MagicMock()
        mock_db.session = None

        with pytest.raises(RuntimeError, match="No Session"):
            CollectionQuery().count(mock_db)

    def test_execute_returns_the_sessions_result(self):
        """execute() hands the built statement to the session and returns its
        result unchanged, so callers see the rows the session produced."""
        mock_db = MagicMock()
        mock_db.session = MagicMock()
        rows = MagicMock()
        mock_db.session.execute.return_value = rows

        result = CollectionQuery().execute(mock_db)

        assert result is rows
        mock_db.session.execute.assert_called_once()

    def test_execute_runs_the_statement_the_query_built(self):
        """The statement execute() runs carries the filters added to the query,
        rather than the bare select() the query started from."""
        mock_db = MagicMock()
        mock_db.session = MagicMock()

        CollectionQuery().by_title("One More Time").execute(mock_db)

        stmt = str(mock_db.session.execute.call_args.args[0])
        assert "WHERE" in stmt
        assert "ORDER BY" in stmt

    def test_execute_no_session_raises(self):
        """execute() raises RuntimeError when db has no session."""
        mock_db = MagicMock()
        mock_db.session = None

        with pytest.raises(RuntimeError, match="No Session"):
            CollectionQuery().execute(mock_db)


class TestNormalizePath:
    def test_converts_backslashes_to_forward_slashes(self, tmp_path):
        assert "\\" not in normalize_path(str(tmp_path))

    @pytest.mark.skipif(
        platform.system() == "Windows",
        reason="symlink creation requires SeCreateSymbolicLinkPrivilege on Windows",
    )
    def test_resolves_symlinks(self, tmp_path):
        target = tmp_path / "real.flac"
        target.write_bytes(b"")
        link = tmp_path / "link.flac"
        link.symlink_to(target)
        assert normalize_path(str(link)).endswith("real.flac")

    def test_makes_relative_paths_absolute(self):
        assert os.path.isabs(normalize_path("song.flac"))

    @pytest.mark.skipif(
        platform.system() != "Windows", reason="drive letters are Windows-only"
    )
    def test_keeps_the_drive_letter_a_subst_drive_resolves_away(self, tmp_path):
        """A mapped drive is what this guards in the field; subst stands in for
        one, since Path.resolve() expands both the same way."""
        track = tmp_path / "song.flac"
        track.write_bytes(b"")
        with _subst_drive(tmp_path) as drive:
            assert normalize_path(f"{drive}/song.flac") == f"{drive}/song.flac"


class TestRestoreDriveLetter:
    """The drive-letter half of normalize_path, fed the paths Windows would
    produce so the assertions run on every platform."""

    UNC = PureWindowsPath("//192.168.68.10/music")

    def test_rewrites_a_unc_share_back_onto_the_drive(self):
        resolved = self.UNC / "DJ Music/song.flac"
        assert (
            _restore_drive_letter(resolved, "M:", self.UNC) == "M:/DJ Music/song.flac"
        )

    def test_rewrites_the_share_root_itself(self):
        assert _restore_drive_letter(self.UNC, "M:", self.UNC) == "M:/"

    def test_keeps_a_path_outside_the_drive_target(self):
        """A symlink deeper in the path can land outside the share; the
        resolved form is then the only one that points at the file."""
        resolved = PureWindowsPath("//other-host/backup/song.flac")
        assert (
            _restore_drive_letter(resolved, "M:", self.UNC)
            == "//other-host/backup/song.flac"
        )


class TestFindContentByKey:
    @staticmethod
    def _db(*folder_paths):
        db = MagicMock()
        db.session = MagicMock()
        rows = [MagicMock(FolderPath=p) for p in folder_paths]
        db.session.execute.return_value.scalars.return_value = rows
        return db, rows

    def test_matches_a_stored_row_by_key(self, tmp_path):
        # A stored FolderPath is always absolute, so the fixture has to be too:
        # a bare "/music/a.flac" gains a drive letter when the key side
        # resolves it on Windows but not when the stored side is normalized.
        track = str(tmp_path / "a.flac")
        db, rows = self._db(track)

        found = find_content_by_key(db, [normalize_path(track).casefold()])

        assert found == {normalize_path(track).casefold(): rows[0]}

    def test_matches_a_backslashed_stored_path(self, tmp_path):
        # A row written by pyrekordbox directly holds Windows separators; it
        # still has to match the forward-slashed key the caller supplies.
        track = tmp_path / "a.flac"
        db, rows = self._db(str(track).replace("/", "\\"))

        found = find_content_by_key(db, [normalize_path(str(track)).casefold()])

        assert list(found.values()) == [rows[0]]

    def test_matches_case_insensitively(self, tmp_path):
        # Rekordbox's stored case can differ from the live filesystem's.
        track = tmp_path / "Track.flac"
        db, rows = self._db(str(track).upper())

        found = find_content_by_key(db, [normalize_path(str(track).lower()).casefold()])

        assert list(found.values()) == [rows[0]]

    def test_omits_rows_that_do_not_match(self, tmp_path):
        db, _ = self._db(str(tmp_path / "other.flac"))

        assert (
            find_content_by_key(
                db, [normalize_path(str(tmp_path / "a.flac")).casefold()]
            )
            == {}
        )

    def test_tolerates_a_null_folder_path(self, tmp_path):
        # FolderPath is nullable; a row holding NULL must not raise.
        db, _ = self._db(None)

        assert (
            find_content_by_key(
                db, [normalize_path(str(tmp_path / "a.flac")).casefold()]
            )
            == {}
        )

    def test_returns_empty_without_querying_when_no_keys_are_given(self, tmp_path):
        db, _ = self._db(str(tmp_path / "a.flac"))

        assert find_content_by_key(db, []) == {}
        db.session.execute.assert_not_called()

    def test_raises_without_a_session(self, tmp_path):
        db = MagicMock()
        db.session = None

        with pytest.raises(RuntimeError, match="No Session"):
            find_content_by_key(
                db, [normalize_path(str(tmp_path / "a.flac")).casefold()]
            )


class TestFindPlaylistsByName:
    def test_returns_a_normal_playlist(self):
        mock_db = MagicMock()
        mock_db.session = MagicMock()
        playlist = MagicMock(Name="Crate", Attribute=0)
        mock_db.session.execute.return_value.scalars.return_value = [playlist]

        assert find_playlists_by_name(mock_db, "Crate") == [playlist]

    def test_excludes_a_folder_with_a_matching_name(self):
        mock_db = MagicMock()
        mock_db.session = MagicMock()
        folder = MagicMock(Name="Crate", Attribute=1)
        mock_db.session.execute.return_value.scalars.return_value = [folder]

        assert find_playlists_by_name(mock_db, "Crate") == []

    def test_a_folder_sharing_a_name_does_not_cause_ambiguity(self):
        # A folder and a normal playlist can share a name; only the normal
        # playlist should resolve, not both.
        mock_db = MagicMock()
        mock_db.session = MagicMock()
        folder = MagicMock(Name="Crate", Attribute=1)
        playlist = MagicMock(Name="Crate", Attribute=0)
        mock_db.session.execute.return_value.scalars.return_value = [folder, playlist]

        assert find_playlists_by_name(mock_db, "Crate") == [playlist]

    def test_excludes_a_smart_playlist_with_a_matching_name(self):
        mock_db = MagicMock()
        mock_db.session = MagicMock()
        smart = MagicMock(Name="Crate", Attribute=4)
        mock_db.session.execute.return_value.scalars.return_value = [smart]

        assert find_playlists_by_name(mock_db, "Crate") == []

    def test_matches_case_insensitively(self):
        mock_db = MagicMock()
        mock_db.session = MagicMock()
        playlist = MagicMock(Name="Late Night", Attribute=0)
        mock_db.session.execute.return_value.scalars.return_value = [playlist]

        assert find_playlists_by_name(mock_db, "late NIGHT") == [playlist]

    def test_raises_without_a_session(self):
        mock_db = MagicMock()
        mock_db.session = None

        with pytest.raises(RuntimeError, match="No Session"):
            find_playlists_by_name(mock_db, "Crate")


class TestFindContentByIds:
    @staticmethod
    def _db(*ids):
        db = MagicMock()
        db.session = MagicMock()
        rows = [MagicMock(ID=i) for i in ids]
        db.session.execute.return_value.scalars.return_value = rows
        return db, rows

    def test_keys_rows_by_id_as_a_string(self):
        db, rows = self._db(1, 2)

        assert find_content_by_ids(db, ["1", "2"]) == {"1": rows[0], "2": rows[1]}

    def test_an_id_with_no_row_is_absent(self):
        db, rows = self._db("A")

        assert find_content_by_ids(db, ["A", "B"]) == {"A": rows[0]}

    def test_no_ids_queries_nothing(self):
        db, _ = self._db()

        assert find_content_by_ids(db, []) == {}
        db.session.execute.assert_not_called()
