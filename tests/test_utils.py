"""Unit tests for utils module functionality."""

from typing import Callable
from unittest.mock import patch

import pytest
from pyrekordbox.db6 import DjmdContent

from rekordbox_edit.utils import (
    PRINT_WIDTHS,
    PrintableField,
    UserQuit,
    get_audio_info,
    get_extension_for_format,
    get_file_type_for_format,
    get_file_type_name,
    print_track_info,
)


class TestGetFileTypeName:
    """Test getter functions."""

    def test_get_file_type_name_known_types(self):
        """Test get_file_type_name with known file type codes."""
        assert get_file_type_name(0) == "MP3"
        assert get_file_type_name(1) == "MP3"
        assert get_file_type_name(4) == "M4A"
        assert get_file_type_name(5) == "FLAC"
        assert get_file_type_name(11) == "WAV"
        assert get_file_type_name(12) == "AIFF"

    def test_get_file_type_name_unknown_types(self):
        """Test get_file_type_name with unknown file type codes."""

        with pytest.raises(ValueError, match="Unknown file_type: None"):
            get_file_type_name(None)  # ty: ignore[invalid-argument-type]
        with pytest.raises(ValueError, match="Unknown file_type: -1"):
            get_file_type_name(-1)
        with pytest.raises(ValueError, match="Unknown file_type: 99"):
            get_file_type_name(99)


class TestGetFileTypeForFormat:
    def test_get_file_type_for_format_case_insensitive(self):
        """Test get_file_type_for_format is case-insensitive."""
        assert get_file_type_for_format("MP3") == 1
        assert get_file_type_for_format("mp3") == 1
        assert get_file_type_for_format("Mp3") == 1
        assert get_file_type_for_format("FLAC") == 5
        assert get_file_type_for_format("flac") == 5
        assert get_file_type_for_format("wav") == 11
        assert get_file_type_for_format("AIFF") == 12
        assert get_file_type_for_format("M4A") == 4

    def test_get_file_type_for_format_invalid(self):
        """Test get_file_type_for_format with invalid formats."""
        import pytest

        with pytest.raises(ValueError, match="Unknown format: invalid"):
            get_file_type_for_format("invalid")

        with pytest.raises(ValueError, match="Format name cannot be empty or None"):
            get_file_type_for_format("")

        with pytest.raises(ValueError, match="Format name cannot be empty or None"):
            get_file_type_for_format(None)  # ty: ignore[invalid-argument-type]


class TestGetGetExtensionForFormat:
    def test_get_extension_for_format_case_insensitive(self):
        """Test get_extension_for_format is case-insensitive."""
        assert get_extension_for_format("MP3") == ".mp3"
        assert get_extension_for_format("mp3") == ".mp3"
        assert get_extension_for_format("Mp3") == ".mp3"
        assert get_extension_for_format("FLAC") == ".flac"
        assert get_extension_for_format("flac") == ".flac"
        assert get_extension_for_format("WAV") == ".wav"
        assert get_extension_for_format("wav") == ".wav"
        assert get_extension_for_format("AIFF") == ".aiff"
        assert get_extension_for_format("aiff") == ".aiff"
        assert get_extension_for_format("ALAC") == ".m4a"
        assert get_extension_for_format("alac") == ".m4a"

    def test_get_extension_for_format_invalid(self):
        """Test get_extension_for_format with invalid formats."""
        import pytest

        with pytest.raises(ValueError, match="Unknown format: invalid"):
            get_extension_for_format("invalid")

        with pytest.raises(ValueError, match="Format name cannot be empty or None"):
            get_extension_for_format("")

        with pytest.raises(ValueError, match="Format name cannot be empty or None"):
            get_extension_for_format(None)  # ty: ignore[invalid-argument-type]


class TestTruncateField:
    """Test truncate_field function."""

    def test_truncate_field_none_value(self):
        """Test truncate_field returns empty string for None value."""
        from rekordbox_edit.utils import PrintableField, truncate_field

        result = truncate_field(PrintableField.Title, None)
        assert result == ""

    def test_truncate_field_empty_string(self):
        """Test truncate_field with empty string."""
        from rekordbox_edit.utils import PrintableField, truncate_field

        result = truncate_field(PrintableField.Title, "")
        assert result == ""

    def test_truncate_field_short_value(self):
        """Test truncate_field returns value as-is when it fits."""
        from rekordbox_edit.utils import PrintableField, truncate_field

        short_title = "Short Title"
        result = truncate_field(PrintableField.Title, short_title)
        assert result == short_title

    def test_truncate_field_exact_width(self):
        """Test truncate_field with value exactly at width limit."""
        from rekordbox_edit.utils import (
            PRINT_WIDTHS,
            PrintableField,
            truncate_field,
        )

        # Create a value exactly the width of Title field (25 chars)
        exact_width_title = "X" * PRINT_WIDTHS[PrintableField.Title]
        result = truncate_field(PrintableField.Title, exact_width_title)
        assert result == exact_width_title

    def test_truncate_field_long_value(self):
        """Test truncate_field truncates long values with ellipsis."""
        from rekordbox_edit.utils import PrintableField, truncate_field

        long_title = "This is a very long title that exceeds the width limit"
        result = truncate_field(PrintableField.Title, long_title)

        assert "..." in result
        assert len(result) == PRINT_WIDTHS[PrintableField.Title]

    def test_truncate_field_minimal_truncation(self):
        """Test truncate_field with value just over the limit."""
        from rekordbox_edit.utils import (
            PRINT_WIDTHS,
            PrintableField,
            truncate_field,
        )

        # Create a value just 1 char over the limit
        over_limit_title = "X" * (PRINT_WIDTHS[PrintableField.Title] + 1)
        result = truncate_field(PrintableField.Title, over_limit_title)

        assert "..." in result
        assert len(result) == PRINT_WIDTHS[PrintableField.Title]


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
        self, capsys, make_djmd_content_item: Callable[[], DjmdContent]
    ):
        """Test printing a single track with the default print_columns.

        Default columns are: ID, Title, FileType, SampleRate, BitDepth, FolderPath
        (ArtistName and AlbumName are NOT included by default)
        """
        # Setup mock content
        mock_content = make_djmd_content_item()

        print_track_info([mock_content])

        captured = capsys.readouterr()
        # Check default columns are present
        assert mock_content.Title in captured.out
        assert get_file_type_name(mock_content.FileType) in captured.out
        assert str(mock_content.SampleRate) in captured.out
        assert str(mock_content.BitDepth) in captured.out
        # FolderPath should be in output (may or may not be truncated depending on length)
        # The default test path is 66 chars, column width is 80, so no truncation
        assert "test_track.wav" in captured.out

    def test_track_with_zero_values(self, capsys, make_djmd_content_item):
        """Test printing track with zero values."""
        # Setup mock content with zero values
        mock_content = make_djmd_content_item(
            ID=123,
            SampleRate=0,
            BitRate=0,
            BitDepth=0,
        )

        print_track_info([mock_content], self.TEST_PRINT_COLUMNS)

        captured = capsys.readouterr()
        lines = captured.out.split("\n")
        data_line = [line for line in lines if "test" in line][0]
        assert data_line.count("0") == 3

    def test_multiple_tracks(self, capsys, make_djmd_content_item):
        """Test printing multiple tracks."""
        mock_content1 = make_djmd_content_item(
            ID=123,
            FileNameL="track1.flac",
            FileType=5,
            FolderPath="/path/track1.flac",
        )

        mock_content2 = make_djmd_content_item(
            ID=456,
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


class TestGetAudioInfo:
    """Test get_audio_info function."""

    @pytest.fixture()
    def ffmpeg_exists(self, mocker):
        mocker.patch("rekordbox_edit.utils.shutil", return_value=True)

    @patch("rekordbox_edit.utils.ffmpeg.probe")
    def test_get_audio_info_successful(self, mock_probe, ffmpeg_exists):
        """Test successful probe with complete audio information."""
        # Setup mock probe response
        mock_probe.return_value = {
            "streams": [
                {
                    "codec_type": "audio",
                    "bits_per_sample": 24,
                    "sample_rate": "48000",
                    "channels": 2,
                    "bit_rate": "2304000",  # 2304 kbps
                }
            ]
        }

        # Execute
        result = get_audio_info("/path/to/audio.flac")

        # Assert
        assert result["bit_depth"] == 24
        assert result["sample_rate"] == 48000
        assert result["channels"] == 2
        assert result["bitrate"] == 2304  # Converted to kbps

    @patch("rekordbox_edit.utils.ffmpeg.probe")
    def test_get_audio_info__with_bits_per_raw_sample(self, mock_probe, ffmpeg_exists):
        """When getting bit depth from bits_per_raw_sample."""
        # Setup mock probe response without bits_per_sample
        mock_probe.return_value = {
            "streams": [
                {
                    "codec_type": "audio",
                    "bits_per_raw_sample": 16,
                    "sample_rate": "44100",
                    "channels": 2,
                    "bit_rate": "1411200",
                }
            ]
        }

        # Execute
        result = get_audio_info("/path/to/audio.wav")

        # Assert
        assert result["bit_depth"] == 16
        assert result["bitrate"] == 1411

    @patch("rekordbox_edit.utils.ffmpeg.probe")
    def test_get_audio_info__with_sample_fmt_parsing(self, mock_probe, ffmpeg_exists):
        """Test getting bit depth from sample_fmt."""
        # Setup mock probe response with sample_fmt
        mock_probe.return_value = {
            "streams": [
                {
                    "codec_type": "audio",
                    "sample_fmt": "s32",
                    "sample_rate": "96000",
                    "channels": 2,
                }
            ]
        }

        # Execute
        result = get_audio_info("/path/to/audio.wav")

        # Assert
        assert result["bit_depth"] == 32
        assert result["sample_rate"] == 96000

    @patch("rekordbox_edit.utils.ffmpeg.probe")
    def test_get_audio_info__calculated_bitrate(self, mock_probe, ffmpeg_exists):
        """Test bitrate calculation when not provided."""
        # Setup mock probe response without bitrate
        mock_probe.return_value = {
            "streams": [
                {
                    "codec_type": "audio",
                    "bits_per_sample": 16,
                    "sample_rate": "44100",
                    "channels": 2,
                    # No bit_rate field
                }
            ]
        }

        # Execute
        result = get_audio_info("/path/to/audio.wav")

        # Assert - calculated: 44100 * 16 * 2 / 1000 = 1411.2 -> 1411
        assert result["bitrate"] == 1411

    @patch("rekordbox_edit.utils.ffmpeg.probe")
    def test_get_audio_info__no_audio_stream(self, mock_probe, ffmpeg_exists):
        """Test exception is raised when no audio stream exists."""
        # Setup mock probe response without audio stream
        mock_probe.return_value = {
            "streams": [{"codec_type": "video", "width": 1920, "height": 1080}]
        }

        # Execute
        with pytest.raises(Exception, match="No audio stream"):
            get_audio_info("/path/to/video.mp4")

    @patch("rekordbox_edit.utils.ffmpeg.probe")
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=False)
    def test_get_audio_info__checks_for_ffmpeg(self, mock_ffmpeg_in_path, mock_probe):
        """Test that we check for ffmpeg first."""
        with pytest.raises(Exception, match="FFmpeg is required"):
            get_audio_info("/nonexistent/file.flac")

    @patch("rekordbox_edit.utils.ffmpeg.probe")
    def test_get_audio_info__with_zero_values(self, mock_probe, ffmpeg_exists):
        """Test handling of zero values in probe data."""
        # Setup mock probe response with zero bit depth
        mock_probe.return_value = {
            "streams": [
                {
                    "codec_type": "audio",
                    "bits_per_sample": 0,  # Zero value
                    "sample_fmt": "s24",  # Should use this instead
                    "sample_rate": "48000",
                    "channels": 2,
                }
            ]
        }

        # Execute
        result = get_audio_info("/path/to/audio.flac")

        # Assert - should use sample_fmt parsing
        assert result["bit_depth"] == 24

    @patch("rekordbox_edit.utils.ffmpeg.probe")
    def test_get_audio_info__unknown_bit_depth_returns_none(
        self, mock_probe, ffmpeg_exists
    ):
        """When bit depth cannot be determined, bit_depth is None."""
        mock_probe.return_value = {
            "streams": [
                {
                    "codec_type": "audio",
                    "sample_rate": "48000",
                    "channels": 2,
                    "bit_rate": "1411200",
                }
            ]
        }

        result = get_audio_info("/path/to/audio.flac")

        assert result["bit_depth"] is None
        assert result["bitrate"] == 1411  # still available from probe

    @patch("rekordbox_edit.utils.ffmpeg.probe")
    def test_get_audio_info__unknown_bitrate_returns_none(
        self, mock_probe, ffmpeg_exists
    ):
        """When bitrate cannot be determined (no stream bitrate, no sample_rate to calculate), bitrate is None."""
        mock_probe.return_value = {
            "streams": [
                {
                    "codec_type": "audio",
                    "bits_per_sample": 24,
                    "sample_fmt": "s24",
                    "channels": 2,
                    # no bit_rate, no sample_rate — calculation impossible
                }
            ]
        }

        result = get_audio_info("/path/to/audio.flac")

        assert result["bit_depth"] == 24
        assert result["bitrate"] is None

    @patch("rekordbox_edit.utils.ffmpeg.probe")
    def test_get_audio_info__mp3_bit_depth_is_none(self, mock_probe, ffmpeg_exists):
        """MP3 has no true bit depth; get_audio_info returns None and leaves it to the caller."""
        mock_probe.return_value = {
            "streams": [
                {
                    "codec_type": "audio",
                    "codec_name": "mp3",
                    "bits_per_sample": 0,  # ffmpeg typically reports 0 for mp3
                    "sample_rate": "44100",
                    "channels": 2,
                    "bit_rate": "320000",
                }
            ]
        }

        result = get_audio_info("/path/to/audio.mp3")

        assert result["bit_depth"] is None
        assert result["bitrate"] == 320
        assert result["sample_rate"] == 44100


class TestConfirm:
    """Test confirm function."""

    @pytest.fixture
    def mock_dependencies(self, mocker):
        """Mock all dependencies for confirm function."""
        mock_click_prompt = mocker.patch("rekordbox_edit.utils.click.prompt")
        mock_logger = mocker.patch("rekordbox_edit.utils.logger")
        return {
            "click_prompt": mock_click_prompt,
            "logger": mock_logger,
        }

    def test_confirm_yes(self, mock_dependencies):
        """Test confirm returns True when user enters 'y'."""
        from rekordbox_edit.utils import confirm

        mock_dependencies["click_prompt"].return_value = "y"

        result = confirm("Continue?", default=False, abort=False)

        assert result is True
        mock_dependencies["click_prompt"].assert_called_once()

    def test_confirm_no(self, mock_dependencies):
        """Test confirm returns False when user enters 'n' with abort=False."""
        from rekordbox_edit.utils import confirm

        mock_dependencies["click_prompt"].return_value = "n"

        result = confirm("Continue?", default=True, abort=False)

        assert result is False
        mock_dependencies["click_prompt"].assert_called_once()

    def test_confirm_quit(self, mock_dependencies):
        """Test confirm raises UserQuit when user enters 'q' with abort=False."""
        from rekordbox_edit.utils import confirm

        mock_dependencies["click_prompt"].return_value = "q"

        with pytest.raises(UserQuit, match="User quit"):
            confirm("Continue?", default=True, abort=False)

    def test_confirm_no_abort_true(self, mock_dependencies):
        """Test confirm raises UserQuit when user enters 'n' with abort=True."""
        from rekordbox_edit.utils import confirm

        mock_dependencies["click_prompt"].return_value = "n"

        with pytest.raises(UserQuit, match="User declined"):
            confirm("Continue?", default=True, abort=True)

        mock_dependencies["click_prompt"].assert_called_once()

    def test_confirm_no_binary_true(self, mock_dependencies):
        """Test confirm raises UserQuit when user enters 'n' with abort=True."""
        from rekordbox_edit.utils import confirm

        mock_dependencies["click_prompt"].return_value = "n"

        confirm("Continue?", default=True, binary=True)

        mock_dependencies["click_prompt"].assert_called_once()

    def test_confirm_case_insensitive_yes(self, mock_dependencies):
        """Test confirm handles case-insensitive 'YES' input."""
        from rekordbox_edit.utils import confirm

        mock_dependencies["click_prompt"].return_value = "Y"

        result = confirm("Continue?", default=False, abort=False)

        assert result is True

    def test_confirm_case_insensitive_no(self, mock_dependencies):
        """Test confirm handles case-insensitive 'NO' input."""
        from rekordbox_edit.utils import confirm

        mock_dependencies["click_prompt"].return_value = "N"

        result = confirm("Continue?", default=True, abort=False)

        assert result is False

    def test_confirm_case_insensitive_quit(self, mock_dependencies):
        """Test confirm handles case-insensitive 'QUIT' input."""
        from rekordbox_edit.utils import confirm

        mock_dependencies["click_prompt"].return_value = "Q"

        with pytest.raises(UserQuit, match="User quit"):
            confirm("Continue?", default=True, abort=False)
