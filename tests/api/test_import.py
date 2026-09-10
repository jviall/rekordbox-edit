import datetime
import os
import shutil
from pathlib import Path
import platform
from unittest.mock import MagicMock, patch

import mutagen
import pytest

from rekordbox_edit.api import _import as import_module
from rekordbox_edit.errors import DirectoryConfirmationRequired
from rekordbox_edit.api._import import (
    AUDIO_EXTENSIONS,
    IMPORT_DEFAULTS,
    UNMAPPED_EXTENSIONS,
    _build_content,
    _ImportCandidate,
    _classify_import,
    _expand_paths,
    _resolve_relations,
    import_tracks,
)
from sqlalchemy import text

from rekordbox_edit.errors import RekordboxRunningError
from rekordbox_edit.models import ImportOp, ImportRequest, SkippedTrack
from rekordbox_edit.query import require_session
from rekordbox_edit.query import normalize_path
from rekordbox_edit.tags import TrackTags, UnreadableFile


def _candidate(path: str, tags: "TrackTags | None" = None) -> _ImportCandidate:
    """A candidate as _expand_paths and _classify_import would leave it."""
    candidate = _ImportCandidate.of(path)
    candidate.tags = tags
    return candidate


class TestImportCandidate:
    """_ImportCandidate owns the match-key rule the lookup compares against."""

    def test_folds_case_so_a_differing_volume_case_still_matches(self):
        # Rekordbox recorded /Volumes/GIG MUSIC while the volume mounts as
        # /Volumes/Gig Music; an exact comparison would duplicate the row.
        assert (
            _ImportCandidate.of("/Volumes/GIG MUSIC/x.flac").key
            == _ImportCandidate.of("/Volumes/Gig Music/x.flac").key
        )

    def test_distinguishes_genuinely_different_paths(self):
        assert (
            _ImportCandidate.of("/music/a.flac").key
            != _ImportCandidate.of("/music/b.flac").key
        )

    def test_keeps_the_argument_spelling_alongside_the_resolved_form(self):
        # Messages quote the path the user typed; the row stores the resolved
        # one, so both have to survive on the candidate.
        candidate = _ImportCandidate.of("a.flac")
        assert candidate.path == "a.flac"
        assert candidate.stored == normalize_path("a.flac")


class TestExpandPaths:
    def test_returns_a_file_argument_unchanged(self, tmp_path):
        track = tmp_path / "a.flac"
        track.write_bytes(b"")
        candidates, dirs, rejected = _expand_paths([str(track)])
        assert [c.path for c in candidates] == [str(track)]
        assert dirs == []
        assert rejected == []

    def test_resolves_each_candidates_stored_form_and_key_once(self, tmp_path):
        track = tmp_path / "A.flac"
        track.write_bytes(b"")
        (candidate,), _, _ = _expand_paths([str(track)])
        assert candidate.stored == normalize_path(str(track))
        assert candidate.key == candidate.stored.casefold()
        assert candidate.tags is None

    def test_walks_a_directory_recursively(self, tmp_path):
        (tmp_path / "nested").mkdir()
        (tmp_path / "a.flac").write_bytes(b"")
        (tmp_path / "nested/b.mp3").write_bytes(b"")
        candidates, dirs, _ = _expand_paths([str(tmp_path)])
        assert {os.path.basename(c.path) for c in candidates} == {"a.flac", "b.mp3"}
        assert dirs == [str(tmp_path)]

    def test_ignores_files_with_unknown_extensions(self, tmp_path):
        (tmp_path / "a.flac").write_bytes(b"")
        (tmp_path / "cover.jpg").write_bytes(b"")
        (tmp_path / "notes.txt").write_bytes(b"")
        candidates, _, _ = _expand_paths([str(tmp_path)])
        assert [os.path.basename(c.path) for c in candidates] == ["a.flac"]

    def test_rejects_a_named_file_with_an_unknown_extension(self, tmp_path):
        # A named file is filtered the same as a walked one, but it is
        # reported rather than dropped, since the user asked for it by name.
        odd = tmp_path / "track.weird"
        odd.write_bytes(b"")
        candidates, _, rejected = _expand_paths([str(odd)])
        assert candidates == []
        assert rejected == [str(odd)]

    def test_matches_extensions_case_insensitively(self, tmp_path):
        loud = tmp_path / "A.FLAC"
        loud.write_bytes(b"")
        candidates, _, rejected = _expand_paths([str(loud)])
        assert [c.path for c in candidates] == [str(loud)]
        assert rejected == []

    def test_deduplicates_a_file_named_twice(self, tmp_path):
        track = tmp_path / "a.flac"
        track.write_bytes(b"")
        candidates, _, _ = _expand_paths([str(track), str(track)])
        assert len(candidates) == 1

    def test_deduplicates_two_spellings_of_one_file(self, tmp_path, monkeypatch):
        # A relative and an absolute spelling both survive a string-equality
        # pass; only the match key collapses them, and the second create
        # would otherwise raise inside db.add_content.
        track = tmp_path / "a.flac"
        track.write_bytes(b"")
        monkeypatch.chdir(tmp_path)
        candidates, _, _ = _expand_paths([str(track), "a.flac"])
        assert len(candidates) == 1

    def test_raises_for_a_missing_path(self, tmp_path):
        with pytest.raises(ValueError, match="does not exist"):
            _expand_paths([str(tmp_path / "absent.flac")])

    def test_returns_results_in_a_stable_order(self, tmp_path):
        for name in ("c.flac", "a.flac", "b.flac"):
            (tmp_path / name).write_bytes(b"")
        candidates, _, _ = _expand_paths([str(tmp_path)])
        paths = [c.path for c in candidates]
        assert paths == sorted(paths)


def test_audio_extensions_cover_the_importable_formats():
    assert {".mp3", ".flac", ".wav", ".aiff", ".aif", ".m4a"} <= AUDIO_EXTENSIONS


def test_audio_extensions_exclude_video():
    assert not {".avi", ".mov", ".m4v", ".mpg"} & AUDIO_EXTENSIONS


class TestUnmappedExtensions:
    """Derived from the real pyrekordbox FileType enum, not a mock, since the
    bug this guards against is that add_content's own getattr(FileType, ...)
    lookup raises AttributeError for a suffix with no matching member."""

    @pytest.mark.parametrize(
        "suffix", [".flac", ".mp3", ".wav", ".aiff", ".aif", ".m4a"]
    )
    def test_omits_every_suffix_add_content_can_type(self, suffix):
        assert suffix not in UNMAPPED_EXTENSIONS

    @pytest.mark.parametrize("suffix", [".mp4", ".aac"])
    def test_holds_a_collected_suffix_add_content_cannot_type(self, suffix):
        assert suffix in UNMAPPED_EXTENSIONS

    def test_is_a_subset_of_the_collected_extensions(self):
        assert UNMAPPED_EXTENSIONS <= AUDIO_EXTENSIONS


@pytest.fixture()
def tags() -> TrackTags:
    return {
        "title": "Wave Alpha",
        "artist": "Alpha",
        "album": "Lossless Vol 1",
        "genre": "House",
        "composer": "A Writer",
        "label": "A Label",
        "isrc": "USXX12345678",
        "key": "Am",
        "comment": "note",
        "track_no": 3,
        "disc_no": 1,
        "release_year": 2022,
        "length": 254,
        "file_type": 5,
        "sample_rate": 44100,
        "bit_depth": 16,
        "bitrate": 96,
    }


class TestImportDefaults:
    def test_uses_rekordbox_empty_values_not_null(self):
        # Rekordbox writes '' and 0 where add_content leaves NULL.
        assert IMPORT_DEFAULTS["FileNameS"] == ""
        assert IMPORT_DEFAULTS["ColorID"] == "0"
        assert IMPORT_DEFAULTS["ExtInfo"] == "null"

    def test_leaves_the_analysis_columns_at_zero(self):
        for column in ("BPM", "Analysed"):
            assert IMPORT_DEFAULTS[column] == 0
        assert IMPORT_DEFAULTS["AnalysisDataPath"] == ""

    def test_omits_the_columns_read_from_the_stream_header(self):
        # _build_content writes these from the file, so a default here would
        # be overwritten anyway and reads as though an import left them zero.
        for column in ("SampleRate", "BitRate", "BitDepth"):
            assert column not in IMPORT_DEFAULTS

    def test_omits_searchstr_so_it_stays_null(self):
        # NULL on all 924 content rows sampled; no observed value to imitate.
        assert "SearchStr" not in IMPORT_DEFAULTS

    def test_omits_hotcueautoload_so_add_content_supplies_it(self):
        # add_content passes HotCueAutoLoad="on" positionally into
        # DjmdContent.create() ahead of **kwargs; repeating it here would
        # raise "got multiple values for keyword argument".
        assert "HotCueAutoLoad" not in IMPORT_DEFAULTS


class TestResolveRelations:
    def test_reuses_existing_relational_rows(self, mock_db, tags):
        existing = MagicMock(ID="art-1")
        mock_db.session.query.return_value.filter_by.return_value.order_by.return_value.first.return_value = existing

        relations = _resolve_relations(mock_db, tags)

        assert relations["ArtistID"] == "art-1"
        mock_db.add_artist.assert_not_called()

    def test_creates_a_missing_relational_row(self, mock_db, tags):
        mock_db.session.query.return_value.filter_by.return_value.order_by.return_value.first.return_value = None
        mock_db.add_artist.return_value = MagicMock(ID="art-new")
        mock_db.add_album.return_value = MagicMock(ID="alb-new")
        mock_db.add_genre.return_value = MagicMock(ID="gen-new")
        mock_db.add_label.return_value = MagicMock(ID="lab-new")

        relations = _resolve_relations(mock_db, tags)

        assert relations["ArtistID"] == "art-new"
        assert relations["AlbumID"] == "alb-new"

    def test_looks_key_up_and_never_creates_one(self, mock_db, tags):
        # DjmdKey is a fixed 25-row table; pyrekordbox has no add_key.
        mock_db.session.query.return_value.filter_by.return_value.order_by.return_value.first.return_value = None
        relations = _resolve_relations(mock_db, tags)
        assert relations["KeyID"] == "0"
        assert not mock_db.add_key.called

    def test_falls_back_to_the_key_sentinel_when_the_file_has_no_key(
        self, mock_db, tags: TrackTags
    ):
        # An untagged key takes the same '0' sentinel as an unrecognized one,
        # without a DjmdKey lookup.
        relations = _resolve_relations(mock_db, {**tags, "key": None})

        assert relations["KeyID"] == "0"

    def test_raises_without_a_session(self, mock_db, tags: TrackTags):
        mock_db.session = None

        with pytest.raises(RuntimeError, match="No Session"):
            _resolve_relations(mock_db, tags)

    def test_omits_relations_for_absent_tags(self, mock_db, tags: TrackTags):
        blank: TrackTags = {**tags, "genre": None, "label": None, "composer": None}
        mock_db.session.query.return_value.filter_by.return_value.order_by.return_value.first.return_value = None
        mock_db.add_artist.return_value = MagicMock(ID="art-new")
        mock_db.add_album.return_value = MagicMock(ID="alb-new")

        relations = _resolve_relations(mock_db, blank)

        assert "GenreID" not in relations
        assert "LabelID" not in relations
        assert "ComposerID" not in relations


class TestBuildContent:
    """_resolve_relations has its own coverage above, so these stub it out and
    focus on _build_content's own contract: the IMPORT_DEFAULTS/HotCueAutoLoad
    call-site collision, the post-write FileType/DateCreated overrides, and
    path normalization."""

    @pytest.fixture(autouse=True)
    def _stub_relations(self, monkeypatch):
        monkeypatch.setattr(
            import_module,
            "_resolve_relations",
            lambda db, tags, created=None: {"ArtistID": "art-1"},
        )

    @pytest.fixture()
    def stale_content(self, mock_db):
        # FileType and DateCreated are seeded with values _build_content must
        # not keep, so the override assertions fail if the overrides are
        # dropped rather than passing vacuously.
        content = MagicMock(FileType=99, DateCreated="1999-01-01")
        mock_db.add_content.return_value = content
        return content

    def test_passes_import_defaults_and_tag_scalars_without_hotcueautoload(
        self, mock_db, tags, tmp_path, stale_content
    ):
        track = tmp_path / "a.flac"
        track.write_bytes(b"")

        _build_content(mock_db, _candidate(str(track), tags))

        _, kwargs = mock_db.add_content.call_args
        assert "HotCueAutoLoad" not in kwargs
        for key, value in IMPORT_DEFAULTS.items():
            assert kwargs[key] == value
        assert kwargs["ArtistID"] == "art-1"
        assert kwargs["Title"] == tags["title"]
        assert kwargs["Commnt"] == tags["comment"]
        assert kwargs["ISRC"] == tags["isrc"]
        assert kwargs["TrackNo"] == tags["track_no"]
        assert kwargs["DiscNo"] == tags["disc_no"]
        assert kwargs["ReleaseYear"] == tags["release_year"]
        assert kwargs["Length"] == tags["length"]

    def test_writes_the_audio_columns_from_the_stream_header(
        self, mock_db, tags, tmp_path, stale_content
    ):
        track = tmp_path / "a.flac"
        track.write_bytes(b"")

        content = _build_content(mock_db, _candidate(str(track), tags))

        assert content.SampleRate == tags["sample_rate"]
        assert content.BitDepth == tags["bit_depth"]
        # FLAC bitrate is stored as 0, the same convention edit applies.
        assert content.BitRate == 0

    def test_overrides_file_type_and_date_created_after_add_content(
        self, mock_db, tags, tmp_path, stale_content
    ):
        track = tmp_path / "a.flac"
        track.write_bytes(b"")

        content = _build_content(mock_db, _candidate(str(track), tags))

        # add_content types every .m4a as AAC and stamps today's date; the
        # tag-read codec and the file's own creation date must win instead.
        assert content is stale_content
        assert content.FileType == tags["file_type"]
        assert content.FileType != 99
        assert content.DateCreated == import_module._created_date(str(track))
        assert content.DateCreated != "1999-01-01"

    @pytest.mark.skipif(
        platform.system() == "Windows",
        reason="symlink creation requires SeCreateSymbolicLinkPrivilege on Windows",
    )
    def test_normalizes_the_path_before_calling_add_content(
        self, mock_db, tags, tmp_path, stale_content
    ):
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        track = real_dir / "a.flac"
        track.write_bytes(b"")
        link = tmp_path / "link.flac"
        link.symlink_to(track)

        _build_content(mock_db, _candidate(str(link), tags))

        called_path = mock_db.add_content.call_args[0][0]
        assert called_path == normalize_path(str(track))
        assert called_path != str(link)

    def test_keeps_add_contents_file_type_when_the_codec_is_unknown(
        self, mock_db, tags, tmp_path, stale_content
    ):
        # read_tags returns None for a container it cannot type; add_content's
        # extension-derived guess is the only value available, so it stands.
        track = tmp_path / "a.flac"
        track.write_bytes(b"")

        content = _build_content(
            mock_db, _candidate(str(track), {**tags, "file_type": None})
        )

        assert content.FileType == 99

    def test_rewrites_the_backslashed_path_add_content_stores(
        self, mock_db, tags, tmp_path, stale_content
    ):
        # add_content stores str(Path(path)), which backslashes on Windows.
        # Rekordbox forward-slashes FolderPath on every platform, so the row
        # must not keep what add_content wrote. Simulated here so the
        # regression is caught on any platform, not only in Windows CI.
        track = tmp_path / "a.flac"
        track.write_bytes(b"")
        stale_content.FolderPath = "C:\\Users\\dj\\a.flac"

        content = _build_content(mock_db, _candidate(str(track), tags))

        assert content.FolderPath == normalize_path(str(track))
        assert "\\" not in content.FolderPath


class TestCreatedDate:
    """st_birthtime is macOS and BSD only, so the fallbacks never run on the
    development platform and need the stat result stubbed to be reached."""

    class _Stat:
        st_ctime = 1_600_000_000.0
        st_mtime = 1_500_000_000.0

    def test_uses_birthtime_when_the_platform_reports_it(self, monkeypatch, tmp_path):
        track = tmp_path / "a.flac"
        track.write_bytes(b"")
        stat = self._Stat()
        stat.st_birthtime = 1_400_000_000.0  # ty: ignore[unresolved-attribute]
        monkeypatch.setattr(import_module.os, "stat", lambda _: stat)

        assert (
            import_module._created_date(str(track))
            == datetime.date.fromtimestamp(1_400_000_000.0).isoformat()
        )

    def test_falls_back_to_ctime_on_windows(self, monkeypatch, tmp_path):
        monkeypatch.setattr(import_module.os, "stat", lambda _: self._Stat())
        monkeypatch.setattr(import_module.os, "name", "nt")

        assert (
            import_module._created_date(str(tmp_path))
            == datetime.date.fromtimestamp(self._Stat.st_ctime).isoformat()
        )

    def test_falls_back_to_mtime_elsewhere(self, monkeypatch, tmp_path):
        # Linux reports no creation time at all, and st_ctime there means the
        # inode-change time, which a chmod would move.
        monkeypatch.setattr(import_module.os, "stat", lambda _: self._Stat())
        monkeypatch.setattr(import_module.os, "name", "posix")

        assert (
            import_module._created_date(str(tmp_path))
            == datetime.date.fromtimestamp(self._Stat.st_mtime).isoformat()
        )


class TestClassifyImport:
    """The five-way matrix from the spec, plus the two gates a create clears."""

    @pytest.fixture()
    def a_playlist(self):
        # _classify_import only checks identity, but its parameter is typed
        # as the resolved DjmdPlaylist row (never the raw request string), so
        # tests calling it directly pass the same shape.
        return MagicMock(Name="Crate")

    @pytest.fixture()
    def readable(self, tags):
        with patch("rekordbox_edit.api._import.read_tags", return_value=tags) as reader:
            yield reader

    def test_new_file_without_a_playlist_is_created(self, readable):
        result = _classify_import(_candidate("/music/a.flac"), None, set(), None)
        assert isinstance(result, ImportOp)
        assert result.action == "create"
        assert result.id == ""

    def test_new_file_with_a_playlist_is_created(self, readable, a_playlist):
        result = _classify_import(_candidate("/music/a.flac"), None, set(), a_playlist)
        assert isinstance(result, ImportOp)
        assert result.action == "create"
        assert result.id == ""

    def test_a_create_records_its_tags_on_the_candidate(self, readable, tags):
        # The write and dry-run phases read tags off the candidate rather than
        # re-reading the file, so classification is what has to put them there.
        candidate = _candidate("/music/a.flac")
        _classify_import(candidate, None, set(), None)
        assert candidate.tags == tags

    def test_a_type_add_content_cannot_store_is_skipped(self, readable):
        # .mp4 is collected so it can be reported, but add_content's own
        # getattr(FileType, "MP4") lookup would raise and fail the batch.
        candidate = _candidate("/music/a.mp4")
        result = _classify_import(candidate, None, set(), None)
        assert isinstance(result, SkippedTrack)
        assert result.reason == "unsupported_file_type"
        assert candidate.tags is None
        readable.assert_not_called()

    def test_a_file_mutagen_cannot_read_is_skipped(self):
        with patch(
            "rekordbox_edit.api._import.read_tags",
            side_effect=UnreadableFile("bad header"),
        ):
            result = _classify_import(_candidate("/music/a.flac"), None, set(), None)
        assert isinstance(result, SkippedTrack)
        assert result.reason == "unreadable_file"
        assert result.track is None

    def test_existing_file_without_a_playlist_is_skipped(self, make_djmd_content_item):
        existing = make_djmd_content_item(ID="7")
        result = _classify_import(_candidate("/music/a.flac"), existing, set(), None)
        assert isinstance(result, SkippedTrack)
        assert result.reason == "already_exists"
        assert result.track is not None
        assert result.track.ID == "7"

    def test_existing_file_missing_from_the_playlist_is_added_to_it(
        self, make_djmd_content_item, a_playlist
    ):
        existing = make_djmd_content_item(ID="7")
        result = _classify_import(
            _candidate("/music/a.flac"), existing, set(), a_playlist
        )
        assert isinstance(result, ImportOp)
        assert result.action == "playlist_add"
        assert result.id == "7"

    def test_existing_file_already_in_the_playlist_is_skipped(
        self, make_djmd_content_item, a_playlist
    ):
        existing = make_djmd_content_item(ID="7")
        result = _classify_import(
            _candidate("/music/a.flac"), existing, {"7"}, a_playlist
        )
        assert isinstance(result, SkippedTrack)
        assert result.reason == "already_exists"


@pytest.fixture()
def one_flac(tmp_path):
    track = tmp_path / "a.flac"
    track.write_bytes(b"")
    return str(track)


@pytest.fixture()
def stub_tags():
    with patch("rekordbox_edit.api._import.read_tags") as reader:
        reader.return_value = {
            "title": "A",
            "artist": None,
            "album": None,
            "genre": None,
            "composer": None,
            "label": None,
            "isrc": None,
            "key": None,
            "comment": None,
            "track_no": None,
            "disc_no": None,
            "release_year": None,
            "length": 2,
            "file_type": 5,
        }
        yield reader


class TestImport:
    def test_dry_run_writes_nothing(self, mock_db, one_flac, stub_tags):
        with patch("rekordbox_edit.api._import.find_content_by_key", return_value={}):
            response = import_tracks(
                mock_db, ImportRequest(paths=[one_flac]), dry_run=True
            )

        assert len(response.result.added) == 1
        assert response.result.added[0].action == "create"
        mock_db.session.commit.assert_not_called()

    def test_dry_run_ops_carry_synthetic_planned_tracks(
        self, mock_db, one_flac, stub_tags
    ):
        # New rows have no ID before insert, so the plan's op carries a
        # synthetic stand-in describing what would be created. `tracks`
        # itself stays empty: a dry run changes nothing.
        with patch("rekordbox_edit.api._import.find_content_by_key", return_value={}):
            response = import_tracks(
                mock_db, ImportRequest(paths=[one_flac]), dry_run=True
            )

        assert response.tracks == []
        assert response.result.added[0].track.ID == ""
        assert response.result.added[0].track.Title == "A"

    def test_commits_once_for_the_whole_batch(
        self, mock_db, one_flac, stub_tags, make_djmd_content_item
    ):
        # _build_content's return goes through track_from_content, which
        # reads every DjmdContent column, so the stub needs a fully-shaped
        # row rather than a bare MagicMock(ID=...).
        with (
            patch("rekordbox_edit.api._import.find_content_by_key", return_value={}),
            patch("rekordbox_edit.api._import._build_content") as builder,
        ):
            builder.return_value = make_djmd_content_item(ID="99")
            import_tracks(mock_db, ImportRequest(paths=[one_flac]))

        mock_db.session.commit.assert_called_once()

    def test_a_created_tracks_id_is_refreshed_after_commit(
        self, mock_db, one_flac, stub_tags, make_djmd_content_item
    ):
        # Before insert, a create op's track is _planned_track's synthetic,
        # ID-less stand-in. `--print ids` (and any caller chaining off the
        # response) needs the real post-insert ID, not that placeholder.
        with (
            patch("rekordbox_edit.api._import.find_content_by_key", return_value={}),
            patch("rekordbox_edit.api._import._build_content") as builder,
        ):
            builder.return_value = make_djmd_content_item(ID="99")
            response = import_tracks(mock_db, ImportRequest(paths=[one_flac]))

        assert response.result.added[0].track.ID == "99"
        assert response.tracks[0].ID == "99"

    def test_dry_run_has_empty_tracks_but_ops_carry_theirs(
        self, mock_db, one_flac, stub_tags
    ):
        with patch("rekordbox_edit.api._import.find_content_by_key", return_value={}):
            response = import_tracks(
                mock_db, ImportRequest(paths=[one_flac]), dry_run=True
            )

        assert response.tracks == []
        assert response.result.added[0].track.Title == "A"

    def test_real_run_has_both_tracks_and_ops(
        self, mock_db, one_flac, stub_tags, make_djmd_content_item
    ):
        with (
            patch("rekordbox_edit.api._import.find_content_by_key", return_value={}),
            patch("rekordbox_edit.api._import._build_content") as builder,
        ):
            builder.return_value = make_djmd_content_item(ID="99")
            response = import_tracks(mock_db, ImportRequest(paths=[one_flac]))

        assert response.result.dry_run is False
        assert response.tracks[0].ID == "99"
        assert response.result.added[0].track.ID == "99"

    def test_unreadable_file_is_skipped_without_aborting(
        self, mock_db, tmp_path, one_flac
    ):
        from rekordbox_edit.tags import UnreadableFile

        with (
            patch("rekordbox_edit.api._import.find_content_by_key", return_value={}),
            patch(
                "rekordbox_edit.api._import.read_tags", side_effect=UnreadableFile("x")
            ),
        ):
            response = import_tracks(
                mock_db, ImportRequest(paths=[one_flac]), dry_run=True
            )

        assert response.result.added == []
        assert response.result.skipped[0].reason == "unreadable_file"

    def test_unsupported_file_type_is_skipped_without_raising(self, mock_db, tmp_path):
        # .mp4 passes the extension filter (RBE recognizes the container) but
        # has no pyrekordbox FileType member, so add_content's
        # getattr(FileType, "MP4") raises AttributeError, which its handler
        # does not catch. Classification must skip it before that call.
        bad = tmp_path / "a.mp4"
        bad.write_bytes(b"")

        with patch("rekordbox_edit.api._import.find_content_by_key", return_value={}):
            response = import_tracks(
                mock_db, ImportRequest(paths=[str(bad)]), dry_run=True
            )

        assert response.result.added == []
        assert response.result.skipped == [SkippedTrack(reason="unsupported_file_type")]

    def test_raises_without_a_session(self, mock_db, tmp_path):
        track = tmp_path / "a.flac"
        track.write_bytes(b"")
        mock_db.session = None

        with pytest.raises(RuntimeError, match="No Session"):
            import_tracks(mock_db, ImportRequest(paths=[str(track)]), dry_run=True)

    def test_a_named_non_audio_file_is_reported_as_skipped(self, mock_db, tmp_path):
        # Filtering a named file must not make it vanish silently.
        art = tmp_path / "cover.jpg"
        art.write_bytes(b"")

        with patch("rekordbox_edit.api._import.find_content_by_key", return_value={}):
            response = import_tracks(
                mock_db, ImportRequest(paths=[str(art)]), dry_run=True
            )

        assert response.result.added == []
        assert response.result.skipped == [SkippedTrack(reason="unsupported_file_type")]

    def test_batch_with_one_unsupported_file_still_imports_the_good_one(
        self, mock_db, tmp_path, stub_tags, make_djmd_content_item
    ):
        # A folder holding one good file and one unmapped extension must not
        # abort the whole batch; only the bad file is skipped.
        good = tmp_path / "a.flac"
        good.write_bytes(b"")
        bad = tmp_path / "b.mp4"
        bad.write_bytes(b"")

        with (
            patch("rekordbox_edit.api._import.find_content_by_key", return_value={}),
            patch(
                "rekordbox_edit.api._import._build_content",
                return_value=make_djmd_content_item(ID="99"),
            ) as builder,
        ):
            response = import_tracks(
                mock_db, ImportRequest(paths=[str(good), str(bad)])
            )

        builder.assert_called_once()
        assert len(response.result.added) == 1
        assert response.result.added[0].action == "create"
        assert response.result.skipped == [SkippedTrack(reason="unsupported_file_type")]
        mock_db.session.commit.assert_called_once()

    def test_raises_when_the_playlist_is_missing(self, mock_db, one_flac, stub_tags):
        with patch(
            "rekordbox_edit.api._import.find_playlists_by_name", return_value=[]
        ):
            with pytest.raises(ValueError, match="No playlist named"):
                import_tracks(
                    mock_db, ImportRequest(paths=[one_flac], playlist="Ghost")
                )

    def test_raises_when_the_playlist_name_is_ambiguous(
        self, mock_db, one_flac, stub_tags
    ):
        matches = [MagicMock(ID="1"), MagicMock(ID="2")]
        with patch(
            "rekordbox_edit.api._import.find_playlists_by_name", return_value=matches
        ):
            with pytest.raises(ValueError, match="2 playlists named"):
                import_tracks(mock_db, ImportRequest(paths=[one_flac], playlist="Dupe"))

    def test_requires_recurse_when_walking(self, mock_db, tmp_path):
        (tmp_path / "a.flac").write_bytes(b"")
        with pytest.raises(DirectoryConfirmationRequired) as raised:
            import_tracks(mock_db, ImportRequest(paths=[str(tmp_path)]), dry_run=True)
        # The counts are the payload; the message names no flag, so a caller
        # can hint at whatever it calls the authorization.
        assert (raised.value.directories, raised.value.files) == (1, 1)
        assert "--" not in str(raised.value)

    def test_walks_a_directory_when_recurse_is_set(self, mock_db, tmp_path, stub_tags):
        (tmp_path / "a.flac").write_bytes(b"")
        with patch("rekordbox_edit.api._import.find_content_by_key", return_value={}):
            response = import_tracks(
                mock_db,
                ImportRequest(paths=[str(tmp_path)], recurse=True),
                dry_run=True,
            )
        assert len(response.result.added) == 1

    def test_deduplicates_two_spellings_of_the_same_file(
        self, mock_db, tmp_path, stub_tags, monkeypatch
    ):
        # _expand_paths only de-dupes by exact string, so an absolute path and
        # a relative path naming the same file both survive it and would
        # otherwise classify as two separate "create" ops.
        track = tmp_path / "a.flac"
        track.write_bytes(b"")
        monkeypatch.chdir(tmp_path)

        with patch("rekordbox_edit.api._import.find_content_by_key", return_value={}):
            response = import_tracks(
                mock_db,
                ImportRequest(paths=[str(track), "a.flac"]),
                dry_run=True,
            )

        assert len(response.result.added) == 1
        assert response.tracks == []

    @pytest.mark.skipif(
        platform.system() == "Windows",
        reason="symlink creation requires SeCreateSymbolicLinkPrivilege on Windows",
    )
    def test_deduplicates_a_symlink_and_its_target(self, mock_db, tmp_path, stub_tags):
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        track = real_dir / "a.flac"
        track.write_bytes(b"")
        link = tmp_path / "link.flac"
        link.symlink_to(track)

        with patch("rekordbox_edit.api._import.find_content_by_key", return_value={}):
            response = import_tracks(
                mock_db,
                ImportRequest(paths=[str(track), str(link)]),
                dry_run=True,
            )

        assert len(response.result.added) == 1
        assert response.tracks == []

    def test_new_file_with_playlist_creates_and_adds_to_playlist(
        self, mock_db, one_flac, stub_tags, make_djmd_content_item
    ):
        playlist = MagicMock(ID="pl-1")
        content = make_djmd_content_item(ID="99")
        # The playlist's current membership is irrelevant for a brand-new
        # file, but the query still runs, so it needs an iterable stand-in.
        mock_db.session.query.return_value.filter_by.return_value = []

        with (
            patch(
                "rekordbox_edit.api._import.find_playlists_by_name",
                return_value=[playlist],
            ),
            patch("rekordbox_edit.api._import.find_content_by_key", return_value={}),
            patch(
                "rekordbox_edit.api._import._build_content", return_value=content
            ) as builder,
        ):
            response = import_tracks(
                mock_db, ImportRequest(paths=[one_flac], playlist="Crate")
            )

        builder.assert_called_once()
        mock_db.add_to_playlist.assert_called_once_with(playlist, content)
        assert response.result.added[0].action == "create"

    def test_existing_track_missing_from_playlist_is_added_without_recreating(
        self, mock_db, one_flac, make_djmd_content_item
    ):
        playlist = MagicMock(ID="pl-1")
        existing = make_djmd_content_item(ID="7")
        # An empty playlist: the track's ID is genuinely absent from it.
        mock_db.session.query.return_value.filter_by.return_value = []

        with (
            patch(
                "rekordbox_edit.api._import.find_playlists_by_name",
                return_value=[playlist],
            ),
            patch(
                "rekordbox_edit.api._import.find_content_by_key",
                return_value={_ImportCandidate.of(one_flac).key: existing},
            ),
            patch("rekordbox_edit.api._import._build_content") as builder,
        ):
            response = import_tracks(
                mock_db, ImportRequest(paths=[one_flac], playlist="Crate")
            )

        assert len(response.result.added) == 1
        assert response.result.added[0].action == "playlist_add"
        mock_db.add_to_playlist.assert_called_once_with(playlist, existing)
        # The track already exists; only _build_content would create a
        # second, duplicate row for it.
        builder.assert_not_called()

    def test_existing_track_already_in_playlist_is_skipped(
        self, mock_db, one_flac, make_djmd_content_item
    ):
        playlist = MagicMock(ID="pl-1")
        existing = make_djmd_content_item(ID="7")
        # A real membership row for this exact track, so the "already a
        # member" branch is reached for the right reason rather than by an
        # empty-iterable default.
        song = MagicMock(ContentID="7")
        mock_db.session.query.return_value.filter_by.return_value = [song]

        with (
            patch(
                "rekordbox_edit.api._import.find_playlists_by_name",
                return_value=[playlist],
            ),
            patch(
                "rekordbox_edit.api._import.find_content_by_key",
                return_value={_ImportCandidate.of(one_flac).key: existing},
            ),
            patch("rekordbox_edit.api._import._build_content") as builder,
        ):
            response = import_tracks(
                mock_db, ImportRequest(paths=[one_flac], playlist="Crate")
            )

        assert response.result.added == []
        assert response.result.skipped[0].reason == "already_exists"
        mock_db.add_to_playlist.assert_not_called()
        builder.assert_not_called()

    def test_empty_string_playlist_behaves_like_no_playlist(
        self, mock_db, one_flac, make_djmd_content_item
    ):
        # playlist="" resolves to None (falsy), but _classify_import used to
        # be handed the raw request field instead of the resolved value, so
        # it saw "" (not None) and classified an existing track as
        # playlist_add. The write phase then found playlist is None and
        # skipped add_to_playlist, so the CLI reported a placement that never
        # happened. Classification and execution must agree.
        existing = make_djmd_content_item(ID="7")

        with (
            patch(
                "rekordbox_edit.api._import.find_content_by_key",
                return_value={_ImportCandidate.of(one_flac).key: existing},
            ),
            patch("rekordbox_edit.api._import.find_playlists_by_name") as find_pl,
            patch("rekordbox_edit.api._import._build_content") as builder,
        ):
            response = import_tracks(
                mock_db, ImportRequest(paths=[one_flac], playlist="")
            )

        find_pl.assert_not_called()
        assert response.result.added == []
        assert response.result.skipped[0].reason == "already_exists"
        mock_db.add_to_playlist.assert_not_called()
        builder.assert_not_called()

    def test_write_failure_rolls_back_and_reraises(
        self, mock_db, tmp_path, stub_tags, make_djmd_content_item, caplog
    ):
        # Unlike convert, import relied entirely on with_database's implicit
        # rollback on close, leaving no record that rows were built and then
        # discarded mid-batch.
        good = tmp_path / "a.flac"
        good.write_bytes(b"")
        failing = tmp_path / "b.flac"
        failing.write_bytes(b"")

        built = make_djmd_content_item(ID="1")

        with (
            patch("rekordbox_edit.api._import.find_content_by_key", return_value={}),
            patch(
                "rekordbox_edit.api._import._build_content",
                side_effect=[built, RuntimeError("db exploded")],
            ),
            caplog.at_level("ERROR"),
        ):
            with pytest.raises(RuntimeError, match="db exploded"):
                import_tracks(mock_db, ImportRequest(paths=[str(good), str(failing)]))

        mock_db.session.rollback.assert_called_once()
        mock_db.session.commit.assert_not_called()
        assert any("rolling back" in message for message in caplog.messages)


class TestImportFromApprovedOps:
    """The write pass walks no directories, so nothing joins the batch late."""

    def test_a_file_created_during_the_prompt_is_not_imported(
        self, mock_db, tmp_path, stub_tags, make_track
    ):
        crate = tmp_path / "crate"
        crate.mkdir()
        previewed = crate / "a.flac"
        previewed.write_bytes(b"")
        latecomer = crate / "b.flac"
        latecomer.write_bytes(b"")
        approved = [
            ImportOp(
                id="", path=str(previewed), action="create", track=make_track(ID="")
            )
        ]

        with patch("rekordbox_edit.api._import.find_content_by_key", return_value={}):
            response = import_tracks(
                mock_db,
                ImportRequest(paths=[str(crate)], recurse=True),
                dry_run=True,
                ops=approved,
            )

        assert [op.path for op in response.result.added] == [str(previewed)]

    def test_a_vanished_file_is_db_or_fs_changed(
        self, mock_db, tmp_path, stub_tags, make_track
    ):
        gone = str(tmp_path / "gone.flac")
        op_track = make_track(ID="")
        approved = [ImportOp(id="", path=gone, action="create", track=op_track)]

        with patch("rekordbox_edit.api._import.find_content_by_key", return_value={}):
            response = import_tracks(
                mock_db, ImportRequest(paths=[gone]), dry_run=True, ops=approved
            )

        assert response.result.added == []
        assert response.result.skipped == [
            SkippedTrack(reason="db_or_fs_changed", track=op_track)
        ]

    def test_ops_skip_the_directory_gate(
        self, mock_db, tmp_path, stub_tags, make_track
    ):
        # _expand_paths never runs, so an unconfirmed directory cannot raise.
        crate = tmp_path / "crate"
        crate.mkdir()
        track_file = crate / "a.flac"
        track_file.write_bytes(b"")
        approved = [
            ImportOp(
                id="", path=str(track_file), action="create", track=make_track(ID="")
            )
        ]

        with patch("rekordbox_edit.api._import.find_content_by_key", return_value={}):
            response = import_tracks(
                mock_db,
                ImportRequest(paths=[str(crate)]),
                dry_run=True,
                ops=approved,
            )

        assert len(response.result.added) == 1


class TestImportStampsUsns:
    """Against the real library, since stamping is a database behavior."""

    _COUNTER = text(
        "SELECT int_1 FROM agentRegistry WHERE registry_id = 'localUpdateCount'"
    )

    _AUDIO = Path(__file__).parent.parent / "e2e/fixtures/audio"

    @pytest.fixture
    def audio_file(self, tmp_path):
        source = self._AUDIO / "01-flac-44_1k-16b.flac"
        if not source.is_file():
            pytest.skip(f"audio fixture missing: {source}")
        target = tmp_path / source.name
        shutil.copy(source, target)
        return target

    def test_an_imported_row_is_stamped(self, db, audio_file):
        session = require_session(db)
        start = session.execute(self._COUNTER).scalar()

        response = import_tracks(db, ImportRequest(paths=[str(audio_file)]))

        assert len(response.result.added) == 1
        content = db.get_content().filter_by(ID=response.result.added[0].id).one()
        assert content.rb_local_usn is not None
        assert content.rb_local_usn <= session.execute(self._COUNTER).scalar()
        assert session.execute(self._COUNTER).scalar() > start

    def test_rows_created_along_the_way_are_stamped_too(self, db, audio_file):
        # The fixture already knows the stock tags, so give this file unseen
        # ones and watch the import spend a USN on each new relation.
        tags = mutagen.File(audio_file)
        tags["artist"] = "An Unseen Artist"
        tags["album"] = "An Unseen Album"
        tags.save()

        session = require_session(db)
        start = session.execute(self._COUNTER).scalar()

        import_tracks(db, ImportRequest(paths=[str(audio_file)]))

        assert session.execute(self._COUNTER).scalar() > start + 1

    def test_a_dry_run_leaves_the_counter_alone(self, db, audio_file):
        session = require_session(db)
        start = session.execute(self._COUNTER).scalar()

        import_tracks(db, ImportRequest(paths=[str(audio_file)]), dry_run=True)

        assert session.execute(self._COUNTER).scalar() == start


class TestImportRefusesWhileRekordboxRuns:
    def test_write_is_refused(self, mock_db, one_flac, stub_tags):
        mock_db.session.query.return_value.filter_by.return_value.__iter__ = (
            lambda self: iter([])
        )

        with patch("rekordbox_edit.api._utils.get_rekordbox_pid", return_value=9):
            with pytest.raises(RekordboxRunningError):
                import_tracks(mock_db, ImportRequest(paths=[one_flac]))

        mock_db.session.commit.assert_not_called()

    def test_dry_run_is_allowed(self, mock_db, one_flac, stub_tags):
        with patch("rekordbox_edit.api._utils.get_rekordbox_pid", return_value=9):
            response = import_tracks(
                mock_db, ImportRequest(paths=[one_flac]), dry_run=True
            )

        assert len(response.result.added) == 1
