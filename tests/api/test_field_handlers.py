from typing import get_args
from unittest.mock import MagicMock, patch

import pytest
from pyrekordbox.db6 import tables as tb

from rekordbox_edit.api._field_handlers import (
    FIELD_HANDLERS,
    FolderPathField,
    RelationalField,
    StringField,
)
from rekordbox_edit.api._relations import RELATIONS, find_by_name, get_or_create
from rekordbox_edit.errors import DependencyMissingError
from rekordbox_edit.models import EditRequest, SkipReason


def _artist_handler():
    return RelationalField("ArtistName", "ArtistID", "ArtistName", "artist")


class TestStringField:
    def test_current_value_reads_named_column(self, make_djmd_content_item):
        content = make_djmd_content_item(ID="1", Title="Old")
        handler = StringField("Title", "Title")
        assert handler.current_value(content) == "Old"

    def test_compute_plain_replace(self):
        handler = StringField("Title", "Title")
        args = EditRequest(title=["x"], field="Title", replace_value="New")
        assert handler.compute_new_value("Old", args) == "New"

    def test_compute_match_replace(self):
        handler = StringField("Title", "Title")
        args = EditRequest(
            title=["x"], field="Title", replace_value="Earth", match_pattern="World"
        )
        assert handler.compute_new_value("Hello World", args) == "Hello Earth"

    def test_compute_plain_replace_sets_from_none(self):
        # Plain --replace assigns a value even to an empty field.
        handler = StringField("Title", "Title")
        args = EditRequest(title=["x"], field="Title", replace_value="New")
        assert handler.compute_new_value(None, args) == "New"

    def test_compute_match_skips_none(self):
        # --match has no text to search when the field is empty.
        handler = StringField("Title", "Title")
        args = EditRequest(
            title=["x"], field="Title", replace_value="b", match_pattern="a"
        )
        assert handler.compute_new_value(None, args) is None

    def test_apply_sets_column(self, make_djmd_content_item):
        content = make_djmd_content_item(ID="1", Title="Old")
        StringField("Title", "Title").apply(db=None, content=content, new_value="New")
        assert content.Title == "New"


class TestCommentField:
    def test_registered_over_commnt_column(self):
        handler = FIELD_HANDLERS["Comment"]
        assert isinstance(handler, StringField)
        assert handler.column == "Commnt"

    def test_current_and_apply_use_commnt(self, make_djmd_content_item):
        content = make_djmd_content_item(ID="1")
        content.Commnt = "old note"
        handler = FIELD_HANDLERS["Comment"]
        assert handler.current_value(content) == "old note"
        db = MagicMock()
        handler.apply(db=db, content=content, new_value="new note")
        assert content.Commnt == "new note"


class TestRegistry:
    def test_title_registered(self):
        assert FIELD_HANDLERS["Title"].name == "Title"
        assert FIELD_HANDLERS["Title"].supports_match is True


class TestRelationalArtist:
    def test_current_value_reads_name_proxy(self, make_djmd_content_item):
        content = make_djmd_content_item(ID="1", ArtistName="Gamma")
        assert _artist_handler().current_value(content) == "Gamma"

    def test_compute_plain_replace(self):
        args = EditRequest(title=["x"], field="ArtistName", replace_value="Alpha")
        assert _artist_handler().compute_new_value("Gamma", args) == "Alpha"


class TestRatingField:
    def test_no_match_support(self):
        assert FIELD_HANDLERS["Rating"].supports_match is False

    def test_validate_rejects_out_of_range(self):
        args = EditRequest(title=["x"], field="Rating", replace_value="9")
        with pytest.raises(ValueError):
            FIELD_HANDLERS["Rating"].validate_request(args)

    def test_validate_warns_and_ignores_match(self):
        args = EditRequest(
            title=["x"], field="Rating", replace_value="3", match_pattern="x"
        )
        # Must not raise; --match is ignored for Rating.
        FIELD_HANDLERS["Rating"].validate_request(args)

    def test_current_value_is_star_string(self, make_djmd_content_item):
        content = make_djmd_content_item(ID="1")
        content.Rating = 3
        assert FIELD_HANDLERS["Rating"].current_value(content) == "3"

    def test_apply_writes_the_star_count_itself(self, make_djmd_content_item):
        # DjmdContent.Rating holds 0-5. The 0/51/102/153/204/255 encoding
        # belongs to rekordbox's XML export, not to this column.
        content = make_djmd_content_item(ID="1")
        content.Rating = 0
        handler = FIELD_HANDLERS["Rating"]
        args = EditRequest(title=["x"], field="Rating", replace_value="4")
        new_value = handler.compute_new_value(handler.current_value(content), args)
        assert new_value == "4"
        handler.apply(db=MagicMock(), content=content, new_value=new_value)
        assert content.Rating == 4


#: Every relational field, as (edit field, foreign key column, relation kind).
#: Composer shares the artist table with ArtistName, so it rides the same cases
#: to prove one role's edit does not collect a record another role still holds.
RELATIONAL_CASES = [
    ("ArtistName", "ArtistID", "artist"),
    ("AlbumName", "AlbumID", "album"),
    ("Genre", "GenreID", "genre"),
    ("Label", "LabelID", "label"),
    ("ComposerName", "ComposerID", "artist"),
]


@pytest.fixture
def tracks(db):
    """Two tracks from the fixture library, to test shared references."""
    rows = db.session.query(tb.DjmdContent).order_by(tb.DjmdContent.ID).limit(2).all()
    assert len(rows) == 2, "fixture library needs at least two tracks"
    return rows


def _point_at(db, content, fk_column, kind, name):
    """Give the track a freshly created record of `kind` to sit on."""
    record = get_or_create(db, kind, name)
    db.session.flush()
    setattr(content, fk_column, record.ID)
    db.session.flush()
    return record


@pytest.mark.parametrize("field,fk_column,kind", RELATIONAL_CASES)
class TestRelationalApply:
    """Every relational field against the real database, since orphan
    collection is a property of what the tables still reference."""

    def test_reuses_an_existing_record(self, db, tracks, field, fk_column, kind):
        content = tracks[0]
        _point_at(db, content, fk_column, kind, "RBE Old")
        target = get_or_create(db, kind, "RBE Reuse Target")
        db.session.flush()

        FIELD_HANDLERS[field].apply(db, content, "RBE Reuse Target")

        assert str(getattr(content, fk_column)) == str(target.ID)
        table = RELATIONS[kind].table
        name_attr = RELATIONS[kind].name_attr
        duplicates = (
            db.session.query(table)
            .filter(getattr(table, name_attr) == "RBE Reuse Target")
            .count()
        )
        assert duplicates == 1

    def test_creates_a_record_when_the_name_is_new(
        self, db, tracks, field, fk_column, kind
    ):
        content = tracks[0]
        _point_at(db, content, fk_column, kind, "RBE Old")

        FIELD_HANDLERS[field].apply(db, content, "RBE Brand New")

        created = find_by_name(db, kind, "RBE Brand New")
        assert str(getattr(content, fk_column)) == str(created.ID)

    def test_collects_the_vacated_record(self, db, tracks, field, fk_column, kind):
        content = tracks[0]
        old = _point_at(db, content, fk_column, kind, "RBE Soon Orphaned")
        old_id = old.ID

        FIELD_HANDLERS[field].apply(db, content, "RBE Somewhere Else")

        table = RELATIONS[kind].table
        assert db.session.query(table).filter_by(ID=old_id).first() is None

    def test_keeps_a_record_another_track_still_holds(
        self, db, tracks, field, fk_column, kind
    ):
        content, sibling = tracks
        shared = _point_at(db, content, fk_column, kind, "RBE Shared")
        setattr(sibling, fk_column, shared.ID)
        db.session.flush()

        FIELD_HANDLERS[field].apply(db, content, "RBE Somewhere Else")

        table = RELATIONS[kind].table
        assert db.session.query(table).filter_by(ID=shared.ID).first() is not None

    def test_leaves_other_tracks_on_the_shared_record(
        self, db, tracks, field, fk_column, kind
    ):
        """Rekordbox reassigns the track rather than renaming the record every
        other track shares."""
        content, sibling = tracks
        shared = _point_at(db, content, fk_column, kind, "RBE Shared")
        setattr(sibling, fk_column, shared.ID)
        db.session.flush()

        FIELD_HANDLERS[field].apply(db, content, "RBE Somewhere Else")

        assert str(getattr(sibling, fk_column)) == str(shared.ID)
        assert getattr(shared, RELATIONS[kind].name_attr) == "RBE Shared"

    def test_reports_the_rows_it_created_and_collected(
        self, db, tracks, field, fk_column, kind
    ):
        """The caller stamps what a write created and reserves a USN for what
        it collected, so a handler has to say which rows those were."""
        content = tracks[0]
        _point_at(db, content, fk_column, kind, "RBE Soon Orphaned")

        incidental = FIELD_HANDLERS[field].apply(db, content, "RBE Brand New")

        assert [getattr(r, RELATIONS[kind].name_attr) for r in incidental.created] == [
            "RBE Brand New"
        ]
        assert incidental.deleted == 1

    def test_reports_nothing_when_it_reuses_and_orphans_nothing(
        self, db, tracks, field, fk_column, kind
    ):
        content, sibling = tracks
        shared = _point_at(db, content, fk_column, kind, "RBE Shared")
        setattr(sibling, fk_column, shared.ID)
        target = get_or_create(db, kind, "RBE Reuse Target")
        db.session.flush()

        incidental = FIELD_HANDLERS[field].apply(db, content, "RBE Reuse Target")

        assert str(getattr(content, fk_column)) == str(target.ID)
        assert incidental.created == ()
        assert incidental.deleted == 0

    def test_clearing_writes_the_empty_foreign_key(
        self, db, tracks, field, fk_column, kind
    ):
        content = tracks[0]
        _point_at(db, content, fk_column, kind, "RBE Soon Cleared")

        FIELD_HANDLERS[field].apply(db, content, "")

        assert getattr(content, fk_column) == RELATIONS[kind].empty_value

    def test_no_previous_record_collects_nothing(
        self, db, tracks, field, fk_column, kind
    ):
        content = tracks[0]
        setattr(content, fk_column, "")
        db.session.flush()

        FIELD_HANDLERS[field].apply(db, content, "RBE Fresh")

        assert find_by_name(db, kind, "RBE Fresh") is not None


def test_composer_edit_spares_an_artist_still_credited(db, tracks):
    """One DjmdArtist row can be both a track's artist and its composer;
    vacating one role must not collect the record the other still holds."""
    content = tracks[0]
    artist = get_or_create(db, "artist", "RBE Double Duty")
    db.session.flush()
    content.ArtistID = artist.ID
    content.ComposerID = artist.ID
    db.session.flush()

    FIELD_HANDLERS["ComposerName"].apply(db, content, "RBE Someone Else")

    assert db.session.query(tb.DjmdArtist).filter_by(ID=artist.ID).first() is not None
    assert content.ArtistID == artist.ID


class TestIntegerField:
    def test_no_match_support(self):
        assert FIELD_HANDLERS["TrackNo"].supports_match is False

    def test_validate_rejects_non_numeric(self):
        args = EditRequest(title=["x"], field="TrackNo", replace_value="four")
        with pytest.raises(ValueError):
            FIELD_HANDLERS["TrackNo"].validate_request(args)

    def test_validate_warns_and_ignores_match(self):
        args = EditRequest(
            title=["x"], field="TrackNo", replace_value="4", match_pattern="1"
        )
        # Must not raise; --match is ignored for a numeric field.
        FIELD_HANDLERS["TrackNo"].validate_request(args)

    def test_current_value_is_a_string(self, make_djmd_content_item):
        content = make_djmd_content_item(ID="1")
        content.TrackNo = 7
        assert FIELD_HANDLERS["TrackNo"].current_value(content) == "7"

    def test_compute_and_apply_write_an_int(self, make_djmd_content_item):
        content = make_djmd_content_item(ID="1")
        content.ReleaseYear = 1999
        handler = FIELD_HANDLERS["ReleaseYear"]
        args = EditRequest(title=["x"], field="ReleaseYear", replace_value="2024")
        new_value = handler.compute_new_value(handler.current_value(content), args)
        assert new_value == "2024"
        handler.apply(db=MagicMock(), content=content, new_value=new_value)
        assert content.ReleaseYear == 2024

    def test_clearing_writes_zero(self, make_djmd_content_item):
        content = make_djmd_content_item(ID="1")
        content.DiscNo = 3
        handler = FIELD_HANDLERS["DiscNo"]
        args = EditRequest(title=["x"], field="DiscNo", replace_value="")
        new_value = handler.compute_new_value(handler.current_value(content), args)
        assert new_value is not None
        handler.apply(db=MagicMock(), content=content, new_value=new_value)
        assert content.DiscNo == 0

    def test_release_year_leaves_release_date_alone(self, make_djmd_content_item):
        content = make_djmd_content_item(ID="1")
        content.ReleaseYear = 1999
        content.ReleaseDate = "1999-04-01"
        FIELD_HANDLERS["ReleaseYear"].apply(MagicMock(), content, "2024")
        assert content.ReleaseDate == "1999-04-01"


class TestISRCField:
    def test_registered_over_the_isrc_column(self):
        handler = FIELD_HANDLERS["ISRC"]
        assert isinstance(handler, StringField)
        assert handler.column == "ISRC"

    def test_match_replace_applies(self, make_djmd_content_item):
        content = make_djmd_content_item(ID="1")
        content.ISRC = "USRC17607839"
        handler = FIELD_HANDLERS["ISRC"]
        args = EditRequest(
            title=["x"], field="ISRC", replace_value="GBAY", match_pattern="USRC"
        )
        new_value = handler.compute_new_value(handler.current_value(content), args)
        assert new_value is not None
        handler.apply(db=MagicMock(), content=content, new_value=new_value)
        assert content.ISRC == "GBAY17607839"


def _folder_handler():
    return FolderPathField()


def _probe(**overrides):
    info = {
        "bit_depth": 16,
        "sample_rate": 44100,
        "channels": 2,
        "bitrate": 1411,
        "codec": "pcm_s16le",
        "container": "wav",
        "duration": 214.4,
    }
    info.update(overrides)
    return info


def _no_cues(db):
    db.session.query.return_value.filter_by.return_value.first.return_value = None


class TestFolderPathField:
    def test_registered(self):
        handler = FIELD_HANDLERS["FolderPath"]
        assert isinstance(handler, FolderPathField)
        assert handler.supports_match is True

    def test_validate_request_drops_probes_from_an_earlier_run(self):
        # FIELD_HANDLERS holds one instance for the life of the process.
        handler = _folder_handler()
        handler._probes[("1", "/new/song.wav")] = _probe()

        handler.validate_request(
            EditRequest(title=["x"], field="FolderPath", replace_value="/new/song.wav")
        )

        assert handler._probes == {}

    def test_current_value_reads_folder_path(self, make_djmd_content_item):
        content = make_djmd_content_item(ID="1", FolderPath="/old/song.wav")
        assert _folder_handler().current_value(content) == "/old/song.wav"

    def test_compute_normalizes_backslashes(self):
        args = EditRequest(
            title=["x"], field="FolderPath", replace_value=r"C:\Music\song.wav"
        )
        assert (
            _folder_handler().compute_new_value("/old/song.wav", args)
            == "C:/Music/song.wav"
        )

    def test_compute_match_skips_none(self):
        # --match has no text to search when the field is empty.
        args = EditRequest(
            title=["x"],
            field="FolderPath",
            replace_value="/new/song.wav",
            match_pattern="/old",
        )
        assert _folder_handler().compute_new_value(None, args) is None

    @patch("rekordbox_edit.api._field_handlers.os.path.exists", return_value=False)
    def test_validate_missing_file_skips(self, _exists, make_djmd_content_item):
        content = make_djmd_content_item(ID="1")
        args = EditRequest(
            title=["x"], field="FolderPath", replace_value="/new/song.wav"
        )

        reason = _folder_handler().validate_track(
            MagicMock(), content, "/new/song.wav", args
        )

        assert reason == "file_not_found"

    @patch("rekordbox_edit.api._field_handlers.os.path.exists", return_value=False)
    def test_validate_missing_file_allowed_proceeds(
        self, _exists, make_djmd_content_item
    ):
        content = make_djmd_content_item(ID="1")
        args = EditRequest(
            title=["x"],
            field="FolderPath",
            replace_value="/new/song.wav",
            allow_missing=True,
        )

        reason = _folder_handler().validate_track(
            MagicMock(), content, "/new/song.wav", args
        )

        assert reason is None

    @patch("rekordbox_edit.api._field_handlers.get_audio_info")
    @patch("rekordbox_edit.api._field_handlers.os.path.getsize", return_value=1000)
    @patch("rekordbox_edit.api._field_handlers.os.path.exists", return_value=True)
    def test_validate_same_size_skips_probe(
        self, _exists, _getsize, mock_probe, make_djmd_content_item
    ):
        content = make_djmd_content_item(ID="1", FileSize=1000)
        content.FileSize = 1000
        args = EditRequest(
            title=["x"], field="FolderPath", replace_value="/new/song.wav"
        )

        reason = _folder_handler().validate_track(
            MagicMock(), content, "/new/song.wav", args
        )

        assert reason is None
        mock_probe.assert_not_called()

    @patch(
        "rekordbox_edit.api._field_handlers.get_audio_info",
        side_effect=OSError("ffprobe failed"),
    )
    @patch("rekordbox_edit.api._field_handlers.os.path.getsize", return_value=2000)
    @patch("rekordbox_edit.api._field_handlers.os.path.exists", return_value=True)
    def test_validate_probe_failure_skips(
        self, _exists, _getsize, _probe_fn, make_djmd_content_item
    ):
        content = make_djmd_content_item(ID="1")
        content.FileSize = 1000
        args = EditRequest(
            title=["x"], field="FolderPath", replace_value="/new/song.wav"
        )

        reason = _folder_handler().validate_track(
            MagicMock(), content, "/new/song.wav", args
        )

        assert reason == "unknown_file_type"

    @patch(
        "rekordbox_edit.api._field_handlers.get_audio_info",
        side_effect=DependencyMissingError("FFmpeg is required"),
    )
    @patch("rekordbox_edit.api._field_handlers.os.path.getsize", return_value=2000)
    @patch("rekordbox_edit.api._field_handlers.os.path.exists", return_value=True)
    def test_validate_missing_ffmpeg_is_not_a_per_track_skip(
        self, _exists, _getsize, _probe_fn, make_djmd_content_item
    ):
        # Swallowing this would report every track as an unrecognized file
        # rather than naming the missing install.
        content = make_djmd_content_item(ID="1")
        content.FileSize = 1000
        args = EditRequest(
            title=["x"], field="FolderPath", replace_value="/new/song.wav"
        )

        with pytest.raises(DependencyMissingError):
            _folder_handler().validate_track(
                MagicMock(), content, "/new/song.wav", args
            )

    @patch(
        "rekordbox_edit.api._field_handlers.get_audio_info",
        return_value=_probe(codec="vorbis", container="ogg"),
    )
    @patch("rekordbox_edit.api._field_handlers.os.path.getsize", return_value=2000)
    @patch("rekordbox_edit.api._field_handlers.os.path.exists", return_value=True)
    def test_validate_unknown_codec_skips_even_when_gates_are_lifted(
        self, _exists, _getsize, _probe_fn, make_djmd_content_item
    ):
        content = make_djmd_content_item(ID="1")
        content.FileSize = 1000
        args = EditRequest(
            title=["x"],
            field="FolderPath",
            replace_value="/new/song.ogg",
            allow_missing=True,
            allow_mismatch=True,
        )

        reason = _folder_handler().validate_track(
            MagicMock(), content, "/new/song.ogg", args
        )

        assert reason == "unknown_file_type"

    @patch(
        "rekordbox_edit.api._field_handlers.get_audio_info",
        return_value=_probe(duration=300.0),
    )
    @patch("rekordbox_edit.api._field_handlers.os.path.getsize", return_value=2000)
    @patch("rekordbox_edit.api._field_handlers.os.path.exists", return_value=True)
    def test_validate_length_mismatch_with_analysis_skips(
        self, _exists, _getsize, _probe_fn, make_djmd_content_item
    ):
        content = make_djmd_content_item(ID="1")
        content.FileSize = 1000
        content.Length = 214
        content.AnalysisDataPath = "/PIONEER/USBANLZ/x/ANLZ0000.DAT"
        args = EditRequest(
            title=["x"], field="FolderPath", replace_value="/new/song.wav"
        )

        reason = _folder_handler().validate_track(
            MagicMock(), content, "/new/song.wav", args
        )

        assert reason == "length_mismatch"

    @patch(
        "rekordbox_edit.api._field_handlers.get_audio_info",
        return_value=_probe(duration=300.0),
    )
    @patch("rekordbox_edit.api._field_handlers.os.path.getsize", return_value=2000)
    @patch("rekordbox_edit.api._field_handlers.os.path.exists", return_value=True)
    def test_validate_length_mismatch_with_cues_skips(
        self, _exists, _getsize, _probe_fn, make_djmd_content_item
    ):
        content = make_djmd_content_item(ID="1")
        content.FileSize = 1000
        content.Length = 214
        content.AnalysisDataPath = None
        db = MagicMock()
        db.session.query.return_value.filter_by.return_value.first.return_value = (
            MagicMock()  # a cue row exists
        )
        args = EditRequest(
            title=["x"], field="FolderPath", replace_value="/new/song.wav"
        )

        reason = _folder_handler().validate_track(db, content, "/new/song.wav", args)

        assert reason == "length_mismatch"

    @patch(
        "rekordbox_edit.api._field_handlers.get_audio_info",
        return_value=_probe(duration=300.0),
    )
    @patch("rekordbox_edit.api._field_handlers.os.path.getsize", return_value=2000)
    @patch("rekordbox_edit.api._field_handlers.os.path.exists", return_value=True)
    def test_validate_length_mismatch_without_analysis_warns_only(
        self, _exists, _getsize, _probe_fn, make_djmd_content_item
    ):
        content = make_djmd_content_item(ID="1")
        content.FileSize = 1000
        content.Length = 214
        content.AnalysisDataPath = None
        db = MagicMock()
        _no_cues(db)
        args = EditRequest(
            title=["x"], field="FolderPath", replace_value="/new/song.wav"
        )

        reason = _folder_handler().validate_track(db, content, "/new/song.wav", args)

        assert reason is None

    @patch(
        "rekordbox_edit.api._field_handlers.get_audio_info",
        return_value=_probe(duration=300.0),
    )
    @patch("rekordbox_edit.api._field_handlers.os.path.getsize", return_value=2000)
    @patch("rekordbox_edit.api._field_handlers.os.path.exists", return_value=True)
    def test_validate_length_mismatch_allowed_proceeds(
        self, _exists, _getsize, _probe_fn, make_djmd_content_item
    ):
        content = make_djmd_content_item(ID="1")
        content.FileSize = 1000
        content.Length = 214
        content.AnalysisDataPath = "/PIONEER/USBANLZ/x/ANLZ0000.DAT"
        args = EditRequest(
            title=["x"],
            field="FolderPath",
            replace_value="/new/song.wav",
            allow_mismatch=True,
        )

        reason = _folder_handler().validate_track(
            MagicMock(), content, "/new/song.wav", args
        )

        assert reason is None

    @patch("rekordbox_edit.api._field_handlers.os.path.getsize", return_value=1000)
    @patch("rekordbox_edit.api._field_handlers.os.path.exists", return_value=True)
    def test_apply_relocation_updates_paths_only(
        self, _exists, _getsize, make_djmd_content_item
    ):
        handler = _folder_handler()
        content = make_djmd_content_item(
            ID="1", FolderPath="/old/dir/song.wav", FileNameL="song.wav"
        )
        content.FileSize = 1000
        content.OrgFolderPath = "/old/dir/song.wav"
        content.SampleRate = 44100
        content.BitDepth = 16
        content.BitRate = 1411
        content.FileType = 11
        db = MagicMock()
        args = EditRequest(
            title=["x"], field="FolderPath", replace_value="/new/dir/song.wav"
        )
        assert handler.validate_track(db, content, "/new/dir/song.wav", args) is None

        handler.apply(db, content, "/new/dir/song.wav")

        assert content.FolderPath == "/new/dir/song.wav"
        assert content.FileNameL == "song.wav"
        assert content.OrgFolderPath == "/new/dir/song.wav"
        # Same bytes: technical columns stay as they were.
        assert content.SampleRate == 44100
        assert content.FileSize == 1000

    @patch(
        "rekordbox_edit.api._field_handlers.get_audio_info",
        return_value=_probe(
            codec="flac",
            container="flac",
            bit_depth=24,
            sample_rate=48000,
            bitrate=2304,
            duration=214.9,
        ),
    )
    @patch("rekordbox_edit.api._field_handlers.os.path.getsize", return_value=2000)
    @patch("rekordbox_edit.api._field_handlers.os.path.exists", return_value=True)
    def test_apply_replaced_file_syncs_metadata(
        self, _exists, _getsize, _probe_fn, make_djmd_content_item
    ):
        handler = _folder_handler()
        content = make_djmd_content_item(
            ID="1", FolderPath="/old/dir/song.wav", FileNameL="song.wav", FileType=11
        )
        content.FileSize = 1000
        content.Length = 214
        content.OrgFolderPath = "/elsewhere/song.wav"
        db = MagicMock()
        _no_cues(db)
        args = EditRequest(
            title=["x"], field="FolderPath", replace_value="/new/dir/song.flac"
        )
        assert handler.validate_track(db, content, "/new/dir/song.flac", args) is None

        handler.apply(db, content, "/new/dir/song.flac")

        assert content.FolderPath == "/new/dir/song.flac"
        assert content.FileNameL == "song.flac"
        # OrgFolderPath did not match the old path, so it stays put.
        assert content.OrgFolderPath == "/elsewhere/song.wav"
        assert content.FileType == 5
        assert content.SampleRate == 48000
        assert content.BitDepth == 24
        assert content.BitRate == 0  # FLAC stores VBR as 0
        assert content.FileSize == 2000
        assert content.Length == 214

    @patch(
        "rekordbox_edit.api._field_handlers.get_audio_info",
        return_value=_probe(
            codec="mp3", container="mp3", bit_depth=None, bitrate=None, duration=None
        ),
    )
    @patch("rekordbox_edit.api._field_handlers.os.path.getsize", return_value=2000)
    @patch("rekordbox_edit.api._field_handlers.os.path.exists", return_value=True)
    def test_apply_probes_on_cache_miss_and_keeps_unreported_columns(
        self, _exists, _getsize, mock_probe, make_djmd_content_item
    ):
        # apply without a prior validate_track probes the file itself; columns
        # the probe reports as None keep their stored values.
        handler = _folder_handler()
        content = make_djmd_content_item(
            ID="1", FolderPath="/old/dir/song.wav", FileNameL="song.wav", FileType=11
        )
        content.FileSize = 1000
        content.Length = 214
        content.BitRate = 320

        handler.apply(MagicMock(), content, "/new/dir/song.mp3")

        mock_probe.assert_called_once_with("/new/dir/song.mp3")
        assert content.FileType == 1
        assert content.FileSize == 2000
        assert content.BitDepth == 16  # rekordbox stores MP3 bit depth as 16
        assert content.BitRate == 320
        assert content.Length == 214

    @patch(
        "rekordbox_edit.api._field_handlers.get_audio_info",
        return_value=_probe(codec="vorbis", container="ogg"),
    )
    @patch("rekordbox_edit.api._field_handlers.os.path.getsize", return_value=2000)
    @patch("rekordbox_edit.api._field_handlers.os.path.exists", return_value=True)
    def test_apply_unknown_file_type_leaves_audio_columns(
        self, _exists, _getsize, _probe_fn, make_djmd_content_item
    ):
        handler = _folder_handler()
        content = make_djmd_content_item(
            ID="1", FolderPath="/old/dir/song.wav", FileNameL="song.wav", FileType=11
        )
        content.FileSize = 1000

        handler.apply(MagicMock(), content, "/new/dir/song.ogg")

        assert content.FolderPath == "/new/dir/song.ogg"
        assert content.FileType == 11
        assert content.FileSize == 1000

    @patch("rekordbox_edit.api._field_handlers.os.path.exists", return_value=False)
    def test_apply_allowed_missing_file_writes_paths_only(
        self, _exists, make_djmd_content_item
    ):
        handler = _folder_handler()
        content = make_djmd_content_item(
            ID="1", FolderPath="/old/dir/song.wav", FileNameL="song.wav", FileType=11
        )
        content.FileSize = 1000
        db = MagicMock()
        args = EditRequest(
            title=["x"],
            field="FolderPath",
            replace_value="/gone/dir/song.wav",
            allow_missing=True,
        )
        assert handler.validate_track(db, content, "/gone/dir/song.wav", args) is None

        handler.apply(db, content, "/gone/dir/song.wav")

        assert content.FolderPath == "/gone/dir/song.wav"
        assert content.FileNameL == "song.wav"
        assert content.FileSize == 1000
        assert content.FileType == 11

    @patch("rekordbox_edit.api._field_handlers._update_anlz_paths")
    def test_post_commit_rewrites_ppth_on_rename(
        self, mock_anlz, make_djmd_content_item
    ):
        content = make_djmd_content_item(
            ID="1", FolderPath="/new/dir/song.flac", FileNameL="song.flac"
        )
        db = MagicMock()

        _folder_handler().post_commit(db, content, "/old/dir/song.wav")

        mock_anlz.assert_called_once_with(db, content, "song.flac")

    @patch("rekordbox_edit.api._field_handlers._update_anlz_paths")
    def test_post_commit_skips_when_basename_unchanged(
        self, mock_anlz, make_djmd_content_item
    ):
        content = make_djmd_content_item(
            ID="1", FolderPath="/new/dir/song.wav", FileNameL="song.wav"
        )

        _folder_handler().post_commit(MagicMock(), content, "/old/dir/song.wav")

        mock_anlz.assert_not_called()

    @patch("rekordbox_edit.api._field_handlers._update_anlz_paths")
    def test_post_commit_swallows_anlz_errors(self, mock_anlz, make_djmd_content_item):
        mock_anlz.side_effect = OSError("disk full")
        content = make_djmd_content_item(
            ID="1", FolderPath="/new/dir/song.flac", FileNameL="song.flac"
        )

        # Must not raise: the row commit already succeeded.
        _folder_handler().post_commit(MagicMock(), content, "/old/dir/song.wav")


class TestGatedSkipReasons:
    def test_folder_path_maps_each_gate_to_its_field(self):
        assert FIELD_HANDLERS["FolderPath"].gated_skip_reasons == {
            "file_not_found": "allow_missing",
            "length_mismatch": "allow_mismatch",
        }

    def test_handlers_without_gates_declare_nothing(self):
        # A caller offering to lift a gate reads this rather than keeping its
        # own list, so a handler with no gates must offer no prompt.
        assert FIELD_HANDLERS["Title"].gated_skip_reasons == {}

    def test_every_declared_reason_is_a_real_skip_reason(self):
        valid = set(get_args(SkipReason))
        for handler in FIELD_HANDLERS.values():
            assert set(handler.gated_skip_reasons) <= valid

    def test_every_declared_field_exists_on_the_request(self):
        # The CLI reads these with getattr, so a typo would silently stop
        # lifting the gate rather than fail.
        for handler in FIELD_HANDLERS.values():
            for field in handler.gated_skip_reasons.values():
                assert field in EditRequest.model_fields
