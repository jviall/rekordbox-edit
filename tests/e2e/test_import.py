"""End-to-end: the row `import` writes must match Rekordbox's import shape.

Column expectations come from research/import-track-row-shape/. Changing one
without new evidence there is a regression, not a fix.

Each test gets its own DB copy and its own copy of the source audio file
under `tmp_path`, never the canonical staged directory from conftest. The
fixture DB already carries a row for every file under that canonical
directory (test_journey.py's `Wave Alpha`, `Interchange`, etc. are those same
files), so importing straight from there would hit the dedup path instead of
creating a row. Importing an independent copy exercises the create path
while keeping the real embedded tags this research is grounded in.
"""

import shutil
from pathlib import Path

import pytest
from pyrekordbox import Rekordbox6Database
from pyrekordbox.db6 import tables as tb

from rekordbox_edit.query import normalize_path
from tests.e2e.conftest import AUDIO_DIR, CliRun

pytestmark = pytest.mark.e2e


# Columns Rekordbox writes as an empty value on an imported, un-analyzed row.
EXPECTED_EMPTY = {
    "FileNameS": "",
    "OrgFolderPath": "",
    "ImagePath": "",
    "Subtitle": "",
    "ReleaseDate": "",
    "ModifiedByRBM": "",
    "DeliveryComment": "",
    "Lyricist": "",
    "Reserved1": "",
    "ColorID": "0",
    "VideoAssociate": "0",
    "ExtInfo": "null",
    "HotCueAutoLoad": "on",
    "DeliveryControl": "on",
    "AnalysisDataPath": "",
    "Rating": 0,
    "DJPlayCount": 0,
    "LyricStatus": 0,
    "SamplerTrackInfo": 0,
    "SamplerPlayOffset": 0,
    "ServiceID": 0,
    "SamplerGain": 0.0,
    "rb_data_status": 0,
    "rb_local_data_status": 0,
    "rb_local_deleted": 0,
    "rb_local_synced": 0,
}

# Analysis fills BPM and Analysed, so an import leaves them at zero.
# SampleRate, BitDepth, and BitRate are read from the file instead: rekordbox
# waits for analysis to fill them, and this tool deliberately does not.
EXPECTED_ZERO = ("BPM", "Analysed")


@pytest.fixture
def staged_track(tmp_path: Path):
    """Copy a named audio fixture to a path the DB fixture has never
    recorded, so `import` always takes the create path."""

    def _copy(name: str) -> Path:
        dst = tmp_path / "import-src" / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(AUDIO_DIR / name, dst)
        return dst

    return _copy


def test_imported_row_matches_the_rekordbox_import_shape(
    rbe: CliRun, fresh_db: Path, staged_track
):
    """Import one fixture file and check the row column by column."""
    track = staged_track("01-flac-44_1k-16b.flac")
    result = rbe("import", str(track), "--yes")
    assert result.returncode == 0, result.stderr

    db = Rekordbox6Database(str(fresh_db))
    assert db.session is not None
    row = (
        db.session.query(tb.DjmdContent)
        .filter_by(FolderPath=normalize_path(str(track)))
        .one()
    )

    assert row.FileType == 5
    assert row.Title == "Wave Alpha"
    assert row.ArtistName == "Alpha"
    assert row.AlbumName == "Lossless Vol 1"
    assert row.Length == 2
    assert row.FileSize == track.stat().st_size

    # Read from the stream header at import, following the same conventions
    # `edit` applies. FLAC bitrate is stored as 0 for variable-rate audio.
    assert row.SampleRate == 44100
    assert row.BitDepth == 16
    assert row.BitRate == 0

    for column, expected in EXPECTED_EMPTY.items():
        assert getattr(row, column) == expected, f"{column} diverges from Rekordbox"
    for column in EXPECTED_ZERO:
        assert getattr(row, column) == 0, f"{column} should await analysis"

    # NULL on every sampled Rekordbox row; no observed value to imitate.
    assert row.SearchStr is None
    assert row.AnalysisUpdated is None
    assert row.TrackInfoUpdated is None
    db.close()


def test_adding_the_same_file_twice_creates_one_row(
    rbe: CliRun, fresh_db: Path, staged_track
):
    track = staged_track("01-flac-44_1k-16b.flac")
    rbe("import", str(track), "--yes")
    second = rbe("import", str(track), "--yes")
    assert second.returncode == 0, second.stderr

    db = Rekordbox6Database(str(fresh_db))
    assert db.session is not None
    rows = (
        db.session.query(tb.DjmdContent)
        .filter_by(FolderPath=normalize_path(str(track)))
        .all()
    )
    assert len(rows) == 1
    db.close()


def test_untagged_file_falls_back_to_the_filename_stem(
    rbe: CliRun, fresh_db: Path, staged_track
):
    # The AIFF fixture carries no tags at all.
    track = staged_track("05-aiff-44_1k-16b.aiff")
    result = rbe("import", str(track), "--yes")
    assert result.returncode == 0, result.stderr

    db = Rekordbox6Database(str(fresh_db))
    assert db.session is not None
    row = (
        db.session.query(tb.DjmdContent)
        .filter_by(FolderPath=normalize_path(str(track)))
        .one()
    )
    assert row.Title == "05-aiff-44_1k-16b"
    assert row.FileType == 12
    db.close()
