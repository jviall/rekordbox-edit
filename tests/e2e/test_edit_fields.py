"""Real-DB integration net for the new edit fields.

Each test copies the committed fixture DB to its own tmp path and drives the
`edit` API against it, so the relational apply and orphan-delete paths are
exercised against a real SQLite database with real relationships. Order-
independent: shares nothing with the ordered journey suite.
"""

import shutil

import pytest
from pyrekordbox import Rekordbox6Database
from pyrekordbox.db6 import tables as tb

from rekordbox_edit.api._edit import edit
from rekordbox_edit.models import EditRequest

pytestmark = pytest.mark.e2e


def test_artist_reuse_deletes_orphan(fresh_db):
    db = Rekordbox6Database(str(fresh_db))
    assert db.session is not None
    before = db.session.query(tb.DjmdArtist).count()

    # Interchange is Gamma's only track; move it to the existing Alpha.
    edit(
        db,
        EditRequest(
            exact_title=["Interchange"], field="ArtistName", replace_value="Alpha"
        ),
    )

    moved = db.session.query(tb.DjmdContent).filter_by(Title="Interchange").one()
    assert moved.ArtistName == "Alpha"
    assert db.session.query(tb.DjmdArtist).filter_by(Name="Gamma").first() is None
    assert db.session.query(tb.DjmdArtist).count() == before - 1
    db.close()


def test_artist_reassign_keeps_shared_artist(fresh_db):
    db = Rekordbox6Database(str(fresh_db))
    assert db.session is not None
    before = db.session.query(tb.DjmdArtist).count()

    # Apple Alpha shares Alpha with Wave Alpha, so Alpha survives the move.
    edit(
        db,
        EditRequest(
            exact_title=["Apple Alpha"], field="ArtistName", replace_value="Beta"
        ),
    )

    moved = db.session.query(tb.DjmdContent).filter_by(Title="Apple Alpha").one()
    assert moved.ArtistName == "Beta"
    assert db.session.query(tb.DjmdArtist).filter_by(Name="Alpha").first() is not None
    assert db.session.query(tb.DjmdArtist).count() == before
    db.close()


def test_album_reuse_deletes_orphan_and_keeps_album_artist(fresh_db):
    db = Rekordbox6Database(str(fresh_db))
    assert db.session is not None
    before = db.session.query(tb.DjmdAlbum).count()
    target = db.session.query(tb.DjmdAlbum).filter_by(Name="Lossless Vol 1").first()
    assert target is not None
    album_artist_before = target.AlbumArtistID

    # Interchange is the only track on "AIFF Sampler"; move it to a shared album.
    edit(
        db,
        EditRequest(
            exact_title=["Interchange"],
            field="AlbumName",
            replace_value="Lossless Vol 1",
        ),
    )

    moved = db.session.query(tb.DjmdContent).filter_by(Title="Interchange").one()
    assert moved.AlbumName == "Lossless Vol 1"
    assert db.session.query(tb.DjmdAlbum).filter_by(Name="AIFF Sampler").first() is None
    assert db.session.query(tb.DjmdAlbum).count() == before - 1
    # The reused album's album-artist is left untouched (deliberate divergence).
    after = db.session.query(tb.DjmdAlbum).filter_by(Name="Lossless Vol 1").first()
    assert after is not None
    assert after.AlbumArtistID == album_artist_before
    db.close()


def test_album_create_new_has_no_album_artist(fresh_db):
    db = Rekordbox6Database(str(fresh_db))
    assert db.session is not None

    # Apple Alpha shares "Apple Lossless" with Apple Beta, so nothing orphans.
    edit(
        db,
        EditRequest(
            exact_title=["Apple Alpha"],
            field="AlbumName",
            replace_value="Fresh Album ZZZ",
        ),
    )

    album = db.session.query(tb.DjmdAlbum).filter_by(Name="Fresh Album ZZZ").first()
    assert album is not None
    moved = db.session.query(tb.DjmdContent).filter_by(Title="Apple Alpha").one()
    assert moved.AlbumID == album.ID
    assert album.AlbumArtistID in (None, "")
    assert album.SearchStr is None
    db.close()


def test_rating_written_as_the_star_count(fresh_db):
    db = Rekordbox6Database(str(fresh_db))
    assert db.session is not None
    edit(
        db, EditRequest(exact_title=["Apple Alpha"], field="Rating", replace_value="4")
    )
    moved = db.session.query(tb.DjmdContent).filter_by(Title="Apple Alpha").one()
    assert moved.Rating == 4
    db.close()


def test_folderpath_relocation_updates_paths_only(fresh_db, staged_audio, tmp_path):
    new_dir = tmp_path / "moved"
    new_dir.mkdir()
    shutil.copy(staged_audio / "01-flac-44_1k-16b.flac", new_dir)

    db = Rekordbox6Database(str(fresh_db))
    assert db.session is not None
    before = db.session.query(tb.DjmdContent).filter_by(Title="Wave Alpha").one()
    old_size, old_type, old_rate = before.FileSize, before.FileType, before.SampleRate

    edit(
        db,
        EditRequest(
            exact_title=["Wave Alpha"],
            field="FolderPath",
            match_pattern=staged_audio.as_posix(),
            replace_value=new_dir.as_posix(),
        ),
    )

    moved = db.session.query(tb.DjmdContent).filter_by(Title="Wave Alpha").one()
    assert moved.FolderPath == f"{new_dir.as_posix()}/01-flac-44_1k-16b.flac"
    assert moved.FileNameL == "01-flac-44_1k-16b.flac"
    # Byte-identical file: the technical columns stay as they were.
    assert moved.FileSize == old_size
    assert moved.FileType == old_type
    assert moved.SampleRate == old_rate
    db.close()


def test_folderpath_repoint_syncs_metadata(fresh_db, staged_audio):
    target = staged_audio / "05-aiff-44_1k-16b.aiff"

    db = Rekordbox6Database(str(fresh_db))
    assert db.session is not None

    # Repoint the FLAC track "Wave Alpha" at a staged AIFF file.
    edit(
        db,
        EditRequest(
            exact_title=["Wave Alpha"],
            field="FolderPath",
            replace_value=target.as_posix(),
            allow_mismatch=True,
        ),
    )

    moved = db.session.query(tb.DjmdContent).filter_by(Title="Wave Alpha").one()
    assert moved.FolderPath == target.as_posix()
    assert moved.FileNameL == "05-aiff-44_1k-16b.aiff"
    assert moved.FileType == 12  # AIFF
    assert moved.FileSize == target.stat().st_size
    assert moved.SampleRate == 44100
    assert moved.BitDepth == 16
    db.close()


def test_folderpath_missing_file_skips_track(fresh_db):
    db = Rekordbox6Database(str(fresh_db))
    assert db.session is not None
    before = db.session.query(tb.DjmdContent).filter_by(Title="Wave Alpha").one()
    old_path = before.FolderPath

    response = edit(
        db,
        EditRequest(
            exact_title=["Wave Alpha"],
            field="FolderPath",
            replace_value="/nowhere/does-not-exist.flac",
        ),
    )

    assert [s.reason for s in response.result.skipped] == ["file_not_found"]
    assert response.result.edits == []
    unchanged = db.session.query(tb.DjmdContent).filter_by(Title="Wave Alpha").one()
    assert unchanged.FolderPath == old_path
    db.close()


def test_genre_create_then_reuse_and_collect_orphan(fresh_db):
    """The fixture library carries no genres, so this drives the whole life
    cycle: create, reuse by name, and collect the record left behind."""
    db = Rekordbox6Database(str(fresh_db))
    assert db.session is not None

    edit(
        db, EditRequest(exact_title=["Interchange"], field="Genre", replace_value="Dub")
    )
    edit(
        db,
        EditRequest(exact_title=["Wave Alpha"], field="Genre", replace_value="Techno"),
    )

    assert db.session.query(tb.DjmdGenre).count() == 2

    # Moving the only Dub track onto the existing Techno row reuses it and
    # leaves Dub unreferenced.
    edit(
        db,
        EditRequest(exact_title=["Interchange"], field="Genre", replace_value="Techno"),
    )

    moved = db.session.query(tb.DjmdContent).filter_by(Title="Interchange").one()
    assert moved.GenreName == "Techno"
    assert db.session.query(tb.DjmdGenre).filter_by(Name="Dub").first() is None
    assert db.session.query(tb.DjmdGenre).count() == 1
    db.close()


def test_label_shared_by_two_tracks_survives_a_move(fresh_db):
    db = Rekordbox6Database(str(fresh_db))
    assert db.session is not None

    for title in ("Interchange", "Wave Alpha"):
        edit(
            db, EditRequest(exact_title=[title], field="Label", replace_value="Ostgut")
        )
    edit(
        db,
        EditRequest(exact_title=["Interchange"], field="Label", replace_value="Warp"),
    )

    assert db.session.query(tb.DjmdLabel).filter_by(Name="Ostgut").first() is not None
    stayed = db.session.query(tb.DjmdContent).filter_by(Title="Wave Alpha").one()
    assert stayed.LabelName == "Ostgut"
    db.close()


def test_clearing_a_label_writes_an_empty_foreign_key(fresh_db):
    db = Rekordbox6Database(str(fresh_db))
    assert db.session is not None

    edit(
        db,
        EditRequest(exact_title=["Interchange"], field="Label", replace_value="Warp"),
    )
    edit(db, EditRequest(exact_title=["Interchange"], field="Label", replace_value=""))

    cleared = db.session.query(tb.DjmdContent).filter_by(Title="Interchange").one()
    assert cleared.LabelID == ""
    assert db.session.query(tb.DjmdLabel).filter_by(Name="Warp").first() is None
    db.close()


def test_composer_edit_spares_the_artist_row_it_shares(fresh_db):
    """Composer and artist read the same DjmdArtist table, so vacating one
    role must not collect a row the other still holds."""
    db = Rekordbox6Database(str(fresh_db))
    assert db.session is not None

    edit(
        db,
        EditRequest(
            exact_title=["Apple Alpha"], field="ComposerName", replace_value="Alpha"
        ),
    )
    edit(
        db,
        EditRequest(
            exact_title=["Apple Alpha"], field="ComposerName", replace_value="Beta"
        ),
    )

    track = db.session.query(tb.DjmdContent).filter_by(Title="Apple Alpha").one()
    assert track.ComposerName == "Beta"
    assert track.ArtistName == "Alpha"
    assert db.session.query(tb.DjmdArtist).filter_by(Name="Alpha").first() is not None
    db.close()


def test_numeric_fields_are_written_as_numbers(fresh_db):
    db = Rekordbox6Database(str(fresh_db))
    assert db.session is not None

    for field, value in (("TrackNo", "7"), ("DiscNo", "2"), ("ReleaseYear", "2024")):
        edit(
            db,
            EditRequest(exact_title=["Interchange"], field=field, replace_value=value),
        )

    track = db.session.query(tb.DjmdContent).filter_by(Title="Interchange").one()
    assert (track.TrackNo, track.DiscNo, track.ReleaseYear) == (7, 2, 2024)
    assert track.ReleaseDate == ""
    db.close()


def test_isrc_is_written_to_its_own_column(fresh_db):
    db = Rekordbox6Database(str(fresh_db))
    assert db.session is not None

    edit(
        db,
        EditRequest(
            exact_title=["Interchange"], field="ISRC", replace_value="USRC17607839"
        ),
    )

    track = db.session.query(tb.DjmdContent).filter_by(Title="Interchange").one()
    assert track.ISRC == "USRC17607839"
    db.close()
