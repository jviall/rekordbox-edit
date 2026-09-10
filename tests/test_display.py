"""Unit tests for the display module."""

import pytest
from rich.console import Console

from rekordbox_edit import display
from rekordbox_edit.display import (
    PrintableField,
    RbeHighlighter,
    print_track_info,
)
from rekordbox_edit.utils import get_file_type_name


def _spans(line: str) -> dict[str, list[str]]:
    """Map each style name RbeHighlighter applied to the substrings it covers."""
    text = RbeHighlighter()(line)
    result: dict[str, list[str]] = {}
    for span in text.spans:
        result.setdefault(str(span.style), []).append(text.plain[span.start : span.end])
    return result


class TestRbeHighlighter:
    """RbeHighlighter picks out actions, paths, options, and counters."""

    def test_action_after_progress_counter(self):
        spans = _spans("[1/49] converted 03 Good Drank.aiff")
        assert spans["rbe.action"] == ["converted"]
        assert spans["rbe.count"] == ["[1/49]"]

    def test_action_at_line_start(self):
        spans = _spans("Skipping 1 file(s): output exists (use --overwrite to convert)")
        assert spans["rbe.action"] == ["Skipping"]
        assert spans["rbe.option"] == ["--overwrite"]

    def test_target_format_is_an_option(self):
        spans = _spans("Converted 49 files to FLAC")
        assert spans["rbe.action"] == ["Converted"]
        assert spans["rbe.option"] == ["FLAC"]

    def test_action_after_leading_newline(self):
        """convert's batch summary opens with its own "\\n" (a blank line
        before the summary); "^" alone only matches string-start, so the
        action word right after that newline needs its own anchor."""
        spans = _spans("\nConverted 49 files to FLAC")
        assert spans["rbe.action"] == ["Converted"]

    def test_format_whitelist_is_registry_driven(self):
        """A format spelled as its lowercase extension (not just the display
        name) is still recognized, since the whitelist is built from every
        FileTypeInfo's name/token/extensions/aliases, not a hand-kept list."""
        spans = _spans("--format-out aif")
        assert spans["rbe.option"] == ["--format-out", "aif"]

    def test_absolute_path(self):
        spans = _spans("Failed to delete /Volumes/GIG MUSIC/track.aiff: reason")
        assert "/Volumes/GIG" in spans["rbe.path"]

    def test_action_word_inside_a_filename_is_not_highlighted(self):
        """A track literally named 'Converted Soul.aiff' is not the verb."""
        spans = _spans("[2/2] converted Converted Soul.aiff")
        assert spans["rbe.action"] == ["converted"]

    def test_bracketed_filename_is_not_mistaken_for_a_counter(self):
        spans = _spans("Skipping Set [b].aiff: output exists")
        assert "rbe.count" not in spans


@pytest.fixture
def wide_console(monkeypatch):
    """Swap the module console for one wide enough to render without truncation.

    Rich's default non-TTY width is 80 cols, which truncates long values
    (e.g. FolderPath) with an ellipsis and makes substring assertions flaky.
    """
    monkeypatch.setattr(
        display,
        "console",
        Console(
            record=True,
            width=400,
            theme=display.RBE_THEME,
            highlighter=display.RbeHighlighter(),
        ),
    )


@pytest.fixture
def terminal_console(monkeypatch):
    """Swap the module console for one the width of an ordinary terminal.

    `wide_console` exists to keep substring assertions stable, but a preview
    that only renders at 400 columns is not a preview anyone sees.
    """
    monkeypatch.setattr(
        display,
        "console",
        Console(
            record=True,
            width=100,
            theme=display.RBE_THEME,
            highlighter=display.RbeHighlighter(),
        ),
    )


class TestPrintTrackInfo:
    """Test print_track_info function."""

    TEST_PRINT_COLUMNS = [
        PrintableField.ID,
        PrintableField.FileNameL,
        PrintableField.Title,
        PrintableField.ArtistName,
        PrintableField.AlbumName,
        PrintableField.FileType,
        PrintableField.SampleRate,
        PrintableField.BitDepth,
        PrintableField.BitRate,
        PrintableField.FolderPath,
    ]

    def test_empty_content_list(self, capsys):
        """Test printing with empty content list."""
        print_track_info([])

        captured = capsys.readouterr()
        assert captured.out == ""

    def test_default_columns(
        self,
        capsys,
        wide_console,
        make_track,
    ):
        """Default columns include ID, Title, FileType, SampleRate, BitDepth, FileNameL, FolderPath."""
        mock_content = make_track(
            FileNameL="my-song.flac",
            FolderPath="/music/library/my-song.flac",
        )

        print_track_info([mock_content])

        captured = capsys.readouterr()
        assert mock_content.Title in captured.out
        assert get_file_type_name(mock_content.FileType) in captured.out
        assert str(mock_content.SampleRate) in captured.out
        assert str(mock_content.BitDepth) in captured.out
        assert "my-song.flac" in captured.out
        # FolderPath renders the directory portion, not the full path
        assert "/music/library" in captured.out

    def test_track_with_zero_values(self, capsys, wide_console, make_track):
        """Test printing track with zero values."""
        mock_content = make_track(
            ID="123",
            SampleRate=0,
            BitRate=0,
            BitDepth=0,
        )

        print_track_info([mock_content], self.TEST_PRINT_COLUMNS)

        captured = capsys.readouterr()
        lines = captured.out.split("\n")
        data_line = [line for line in lines if "test" in line][0]
        assert data_line.count("0") == 3

    def test_change_preview_renders_old_struck_through_with_new(
        self, capsys, wide_console, make_track
    ):
        """When changed_field + new_values are provided, both old and new appear in the cell."""
        mock_content = make_track(Title="Old Name")

        print_track_info(
            [mock_content],
            print_columns=[PrintableField.Title],
            changed_field=PrintableField.Title,
            new_values=["New Name"],
        )

        captured = capsys.readouterr()
        assert "Old Name" in captured.out
        assert "New Name" in captured.out

    def test_change_preview_shows_the_new_path_at_terminal_width(
        self, capsys, terminal_console, make_track
    ):
        """A path rewrite is the case this preview exists for, and paths are long.

        Old and new share one no-wrap ellipsis cell, so the old value alone
        fills the column and the new value is truncated away entirely. A bulk
        repoint is then unverifiable from --dry-run.
        """
        old = (
            "A:/Music/Any Time, Any Place - Janet Jackson (1994) "
            "{V25H-38435} [FLAC-CD]/03 Janet Jackson - Any Time, Any Place.flac"
        )
        new = old.replace("A:/Music/", "A:/rbe_migration_copy/Music/")

        print_track_info(
            [make_track(FolderPath=old)],
            changed_field=PrintableField.FolderPath,
            new_values=[new],
        )

        # The cell wraps, so the path is split across lines; join it back up.
        rendered = "".join(capsys.readouterr().out.split())
        assert "rbe_migration_copy/Music/" in rendered
        assert "A:/Music/AnyTime" in rendered

    def test_change_preview_requires_both_args(self, make_track):
        """Providing only one of changed_field/new_values raises ValueError."""
        mock_content = make_track()

        with pytest.raises(ValueError, match="must be provided together"):
            print_track_info([mock_content], changed_field=PrintableField.Title)

        with pytest.raises(ValueError, match="must be provided together"):
            print_track_info([mock_content], new_values=["x"])

    def test_change_preview_length_mismatch_raises(self, make_track):
        """new_values length must match content_list length."""
        mock_content = make_track()

        with pytest.raises(ValueError, match="length"):
            print_track_info(
                [mock_content],
                changed_field=PrintableField.Title,
                new_values=["a", "b"],
            )

    def test_multiple_tracks(self, capsys, wide_console, make_track):
        """Test printing multiple tracks."""
        mock_content1 = make_track(
            ID="123",
            FileNameL="track1.flac",
            FileType=5,
            FolderPath="/path/track1.flac",
        )

        mock_content2 = make_track(
            ID="456",
            FileNameL="track2.mp3",
            FileType=1,
            FolderPath="/path/track2.mp3",
        )

        print_track_info([mock_content1, mock_content2])

        captured = capsys.readouterr()
        assert "track1.flac" in captured.out
        assert "track2.mp3" in captured.out
        assert "FLAC" in captured.out
        assert "MP3" in captured.out

    def test_track_with_unknown_file_type(self, capsys, wide_console, make_track):
        """Test printing track with unknown file type."""
        mock_content = make_track(
            ID="123",
            FileType=99,
        )

        print_track_info([mock_content], self.TEST_PRINT_COLUMNS)

        captured = capsys.readouterr()
        assert "UNKNOWN" in captured.out


def test_changed_field_injected_into_columns(capsys, wide_console, make_track):
    from rekordbox_edit.display import (
        PrintableField,
        print_track_info,
    )

    track = make_track(ID="1", ArtistName="Old Artist")
    print_track_info(
        [track],
        changed_field=PrintableField.ArtistName,
        new_values=["New Artist"],
    )
    rendered = capsys.readouterr().out
    assert "Old Artist" in rendered
    assert "New Artist" in rendered


def test_comment_column_renders(capsys, wide_console, make_track):
    track = make_track(ID="1")
    track.Commnt = "hello"
    print_track_info([track], print_columns=[PrintableField.Comment])
    rendered = capsys.readouterr().out
    assert "hello" in rendered


def test_rating_renders_as_stars(capsys, wide_console, make_track):
    track = make_track(ID="1")
    track.Rating = 4
    print_track_info([track], print_columns=[PrintableField.Rating])
    rendered = capsys.readouterr().out
    assert "4" in rendered
