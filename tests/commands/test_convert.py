"""Unit tests for convert command functionality."""

import os
from unittest.mock import Mock, patch

import ffmpeg
import pytest
from callee import Regex, String

from rekordbox_edit.commands.convert import (
    cleanup_converted_files,
    convert_command,
    convert_to_lossless,
    convert_to_mp3,
    get_output_path,
    rollback_and_cleanup,
    update_database_record,
)
from rekordbox_edit.utils import OutputFormats, UserQuit


@pytest.fixture(autouse=True)
def mock_logger():
    """Mock the logger for all tests in this module."""
    with patch("rekordbox_edit.commands.convert.logger") as mock_log:
        yield mock_log


class TestConvertToLossless:
    """Test convert_to_lossless function."""

    @patch("rekordbox_edit.commands.convert.get_audio_info")
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    @patch("rekordbox_edit.commands.convert.ffmpeg")
    def test_convert_to_aiff_16bit(
        self, mock_ffmpeg, mock_ffmpeg_in_path, mock_get_audio_info
    ):
        """Test converting to AIFF with 16-bit depth."""
        # Setup
        mock_ffmpeg_in_path.return_value = True
        mock_get_audio_info.return_value = {"bit_depth": 16}
        mock_input = Mock()
        mock_output = Mock()
        mock_ffmpeg.input.return_value = mock_input
        mock_input.output.return_value = mock_output
        mock_output.overwrite_output.return_value = mock_output
        mock_output.run.return_value = None

        # Execute
        result = convert_to_lossless("input.flac", "output.aiff", OutputFormats.AIFF)

        # Assert
        assert result is True
        mock_get_audio_info.assert_called_once_with("input.flac")
        mock_ffmpeg.input.assert_called_once_with("input.flac")
        mock_input.output.assert_called_once_with(
            "output.aiff", acodec="pcm_s16be", map_metadata=0, write_id3v2=1
        )

    @patch("rekordbox_edit.commands.convert.get_audio_info")
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    @patch("rekordbox_edit.commands.convert.ffmpeg")
    def test_convert_to_wav_24bit(
        self, mock_ffmpeg, mock_ffmpeg_in_path, mock_get_audio_info
    ):
        """Test converting to WAV with 24-bit depth."""
        # Setup
        mock_ffmpeg_in_path.return_value = True
        mock_get_audio_info.return_value = {"bit_depth": 24}
        mock_input = Mock()
        mock_output = Mock()
        mock_ffmpeg.input.return_value = mock_input
        mock_input.output.return_value = mock_output
        mock_output.overwrite_output.return_value = mock_output
        mock_output.run.return_value = None

        # Execute
        result = convert_to_lossless("input.flac", "output.wav", OutputFormats.WAV)

        # Assert
        assert result is True
        mock_input.output.assert_called_once_with(
            "output.wav", acodec="pcm_s24le", map_metadata=0, write_id3v2=1
        )

    @patch("rekordbox_edit.commands.convert.get_audio_info")
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    @patch("rekordbox_edit.commands.convert.ffmpeg")
    def test_convert_to_flac(
        self, mock_ffmpeg, mock_ffmpeg_in_path, mock_get_audio_info
    ):
        """Test converting to FLAC."""
        # Setup
        mock_ffmpeg_in_path.return_value = True
        mock_get_audio_info.return_value = {"bit_depth": 24}
        mock_input = Mock()
        mock_output = Mock()
        mock_ffmpeg.input.return_value = mock_input
        mock_input.output.return_value = mock_output
        mock_output.overwrite_output.return_value = mock_output
        mock_output.run.return_value = None

        # Execute
        result = convert_to_lossless("input.wav", "output.flac", OutputFormats.FLAC)

        # Assert
        assert result is True
        mock_input.output.assert_called_once_with(
            "output.flac", acodec="flac", map_metadata=0, write_id3v2=1
        )

    @patch("rekordbox_edit.commands.convert.get_audio_info")
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    @patch("rekordbox_edit.commands.convert.ffmpeg")
    def test_convert_unsupported_format(
        self, mock_ffmpeg, mock_ffmpeg_in_path, mock_get_audio_info
    ):
        """Test conversion with unsupported format raises exception."""
        # Setup
        mock_ffmpeg_in_path.return_value = True
        mock_get_audio_info.return_value = {"bit_depth": 16}

        # Simulate an OutputFormats-like value whose .value is not in codec_maps
        fake_format = Mock()
        fake_format.value = "xyz"

        # Execute & Assert - should raise, not return False
        with pytest.raises(Exception, match="Unsupported lossless format"):
            convert_to_lossless("input.flac", "output.xyz", fake_format)

    @patch("rekordbox_edit.commands.convert.get_audio_info")
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    @patch("rekordbox_edit.commands.convert.ffmpeg")
    def test_convert_ffmpeg_error(
        self, mock_ffmpeg, mock_ffmpeg_in_path, mock_get_audio_info
    ):
        """Test handling of ffmpeg errors."""
        # Setup
        mock_ffmpeg_in_path.return_value = True
        mock_get_audio_info.return_value = {"bit_depth": 16}
        mock_input = Mock()
        mock_output = Mock()
        mock_ffmpeg.input.return_value = mock_input
        mock_input.output.return_value = mock_output
        mock_output.overwrite_output.return_value = mock_output

        # Create an ffmpeg.Error with stderr
        error = ffmpeg.Error("cmd", "stdout", "stderr")
        mock_output.run.side_effect = error

        # Execute
        result = convert_to_lossless("input.flac", "output.aiff", OutputFormats.AIFF)

        # Assert
        assert result is False

    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    def test_convert_to_lossless_ffmpeg_not_found(self, mock_ffmpeg_in_path):
        """Raises exception when FFmpeg is not in PATH."""
        mock_ffmpeg_in_path.return_value = False

        with pytest.raises(Exception, match="FFmpeg not found in PATH"):
            convert_to_lossless("input.flac", "output.aiff", OutputFormats.AIFF)

    @patch("rekordbox_edit.commands.convert.get_audio_info")
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    @patch("rekordbox_edit.commands.convert.ffmpeg")
    def test_convert_to_lossless_unknown_bit_depth_falls_back(
        self, mock_ffmpeg, mock_ffmpeg_in_path, mock_get_audio_info
    ):
        """When bit_depth is not in the codec map, falls back to first codec."""
        mock_ffmpeg_in_path.return_value = True
        mock_get_audio_info.return_value = {"bit_depth": 8}  # Not in {16, 24, 32}
        mock_input = Mock()
        mock_output = Mock()
        mock_ffmpeg.input.return_value = mock_input
        mock_input.output.return_value = mock_output
        mock_output.overwrite_output.return_value = mock_output
        mock_output.run.return_value = None

        result = convert_to_lossless("input.flac", "output.aiff", OutputFormats.AIFF)

        assert result is True
        # Falls back to first codec in map: pcm_s16be for AIFF
        mock_input.output.assert_called_once_with(
            "output.aiff", acodec="pcm_s16be", map_metadata=0, write_id3v2=1
        )

    @patch("rekordbox_edit.commands.convert.get_audio_info")
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    @patch("rekordbox_edit.commands.convert.ffmpeg")
    def test_convert_to_lossless_ffmpeg_error_no_stderr(
        self, mock_ffmpeg, mock_ffmpeg_in_path, mock_get_audio_info
    ):
        """FfmpegError with no stderr skips the decode step and returns False."""
        mock_ffmpeg_in_path.return_value = True
        mock_get_audio_info.return_value = {"bit_depth": 16}
        mock_input = Mock()
        mock_output = Mock()
        mock_ffmpeg.input.return_value = mock_input
        mock_input.output.return_value = mock_output
        mock_output.overwrite_output.return_value = mock_output

        error = ffmpeg.Error("cmd", "stdout", None)  # no stderr
        mock_output.run.side_effect = error

        result = convert_to_lossless("input.flac", "output.aiff", OutputFormats.AIFF)

        assert result is False

    @patch("rekordbox_edit.commands.convert.get_audio_info")
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    @patch("rekordbox_edit.commands.convert.ffmpeg")
    def test_convert_to_lossless_unexpected_exception_reraises(
        self, mock_ffmpeg, mock_ffmpeg_in_path, mock_get_audio_info
    ):
        """Non-ffmpeg exceptions are re-raised after logging."""
        mock_ffmpeg_in_path.return_value = True
        mock_get_audio_info.return_value = {"bit_depth": 16}
        mock_input = Mock()
        mock_output = Mock()
        mock_ffmpeg.input.return_value = mock_input
        mock_input.output.return_value = mock_output
        mock_output.overwrite_output.return_value = mock_output
        mock_output.run.side_effect = RuntimeError("disk full")

        with pytest.raises(RuntimeError, match="disk full"):
            convert_to_lossless("input.flac", "output.aiff", OutputFormats.AIFF)


class TestConvertToMp3:
    """Test convert_to_mp3 function."""

    @patch("rekordbox_edit.commands.convert.get_audio_info")
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    @patch("rekordbox_edit.commands.convert.ffmpeg")
    def test_convert_to_mp3_success(
        self, mock_ffmpeg, mock_ffmpeg_in_path, mock_get_audio_info
    ):
        """Test successful MP3 conversion."""
        # Setup
        mock_ffmpeg_in_path.return_value = True
        mock_input = Mock()
        mock_output = Mock()
        mock_ffmpeg.input.return_value = mock_input
        mock_input.output.return_value = mock_output
        mock_output.overwrite_output.return_value = mock_output
        mock_output.run.return_value = None

        # Execute
        result = convert_to_mp3("input.flac", "output.mp3")

        # Assert
        assert result is True
        mock_ffmpeg.input.assert_called_once_with("input.flac")
        mock_input.output.assert_called_once_with(
            "output.mp3",
            acodec="libmp3lame",
            audio_bitrate="320k",
            map_metadata=0,
            write_id3v2=1,
        )

    @patch("rekordbox_edit.commands.convert.get_audio_info")
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    @patch("rekordbox_edit.commands.convert.ffmpeg")
    def test_convert_to_mp3_ffmpeg_error(
        self, mock_ffmpeg, mock_ffmpeg_in_path, mock_get_audio_info
    ):
        """Test MP3 conversion with ffmpeg error."""
        # Setup
        mock_ffmpeg_in_path.return_value = True
        mock_input = Mock()
        mock_output = Mock()
        mock_ffmpeg.input.return_value = mock_input
        mock_input.output.return_value = mock_output
        mock_output.overwrite_output.return_value = mock_output

        error = ffmpeg.Error("cmd", "stdout", "stderr")
        mock_output.run.side_effect = error

        # Execute
        result = convert_to_mp3("input.flac", "output.mp3")

        # Assert
        assert result is False

    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    def test_convert_to_mp3_ffmpeg_not_found(self, mock_ffmpeg_in_path):
        """Raises exception when FFmpeg is not in PATH."""
        mock_ffmpeg_in_path.return_value = False

        with pytest.raises(Exception, match="FFmpeg not found in PATH"):
            convert_to_mp3("input.flac", "output.mp3")

    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    @patch("rekordbox_edit.commands.convert.ffmpeg")
    def test_convert_to_mp3_ffmpeg_error_no_stderr(
        self, mock_ffmpeg, mock_ffmpeg_in_path
    ):
        """FfmpegError with no stderr skips the decode step and returns False."""
        mock_ffmpeg_in_path.return_value = True
        mock_input = Mock()
        mock_output = Mock()
        mock_ffmpeg.input.return_value = mock_input
        mock_input.output.return_value = mock_output
        mock_output.overwrite_output.return_value = mock_output

        error = ffmpeg.Error("cmd", "stdout", None)  # no stderr
        mock_output.run.side_effect = error

        result = convert_to_mp3("input.flac", "output.mp3")

        assert result is False

    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    @patch("rekordbox_edit.commands.convert.ffmpeg")
    def test_convert_to_mp3_unexpected_exception_reraises(
        self, mock_ffmpeg, mock_ffmpeg_in_path
    ):
        """Non-ffmpeg exceptions are re-raised after logging."""
        mock_ffmpeg_in_path.return_value = True
        mock_input = Mock()
        mock_output = Mock()
        mock_ffmpeg.input.return_value = mock_input
        mock_input.output.return_value = mock_output
        mock_output.overwrite_output.return_value = mock_output
        mock_output.run.side_effect = RuntimeError("permission denied")

        with pytest.raises(RuntimeError, match="permission denied"):
            convert_to_mp3("input.flac", "output.mp3")


class TestUpdateDatabaseRecord:
    """Test update_database_record function."""

    @patch("rekordbox_edit.commands.convert.get_audio_info")
    @patch("os.path.join")
    def test_update_database_record_flac(
        self, mock_join, mock_get_audio_info, make_djmd_content_item
    ):
        """Test updating database record for FLAC conversion."""
        # Setup
        mock_db = Mock()
        mock_content = make_djmd_content_item(ID=123, BitDepth=24)
        mock_db.get_content().filter_by(ID=123).first.return_value = mock_content

        mock_join.return_value = "/path/to/output.flac"
        mock_get_audio_info.return_value = {"bitrate": 1000, "bit_depth": 24}

        # Execute
        update_database_record(mock_db, 123, "output.flac", "/path/to", "FLAC")

        # Assert
        assert mock_content.FileNameL == "output.flac"
        assert mock_content.FolderPath == "/path/to/output.flac"
        assert mock_content.FileType == 5  # FLAC file type
        assert mock_content.BitRate == 0  # FLAC bitrate set to 0

    @patch("rekordbox_edit.commands.convert.get_audio_info")
    @patch("os.path.join")
    def test_update_database_record_mp3(
        self, mock_join, mock_get_audio_info, make_djmd_content_item
    ):
        """Test updating database record for MP3 conversion."""
        # Setup
        mock_db = Mock()
        mock_content = make_djmd_content_item(ID=123)
        mock_db.get_content().filter_by(ID=123).first.return_value = mock_content

        mock_join.return_value = "/path/to/output.mp3"
        mock_get_audio_info.return_value = {"bitrate": 320, "bit_depth": 16}

        # Execute
        update_database_record(mock_db, 123, "output.mp3", "/path/to", "MP3")

        # Assert
        assert mock_content.FileNameL == "output.mp3"
        assert mock_content.FolderPath == "/path/to/output.mp3"
        assert mock_content.FileType == 1  # MP3 file type
        assert mock_content.BitRate == 320

    def test_update_database_record_content_not_found(self):
        """Test updating database record when content not found."""
        # Setup
        mock_db = Mock()
        mock_db.get_content().filter_by(ID=123).first.return_value = None

        # Execute & Assert
        with pytest.raises(Exception, match="Content record with ID 123 not found"):
            update_database_record(mock_db, 123, "output.flac", "/path/to", "FLAC")

    @patch("rekordbox_edit.commands.convert.get_audio_info")
    @patch("os.path.join")
    def test_update_database_record_bit_depth_mismatch(
        self, mock_join, mock_get_audio_info, make_djmd_content_item
    ):
        """Test bit depth verification fails on mismatch."""
        # Setup
        mock_db = Mock()
        mock_content = make_djmd_content_item(ID=123, BitDepth=16)
        mock_db.get_content().filter_by(ID=123).first.return_value = mock_content

        mock_join.return_value = "/path/to/output.aiff"
        mock_get_audio_info.return_value = {"bitrate": 1000, "bit_depth": 24}

        # Execute & Assert
        with pytest.raises(Exception, match="Bit depth mismatch"):
            update_database_record(mock_db, 123, "output.aiff", "/path/to", "AIFF")

    @patch("rekordbox_edit.commands.convert.get_audio_info")
    @patch("os.path.join")
    def test_update_database_record_mp3_none_bitrate_uses_320(
        self, mock_join, mock_get_audio_info, make_djmd_content_item
    ):
        """MP3 conversion with None bitrate from probe defaults to 320kbps."""
        mock_db = Mock()
        mock_content = make_djmd_content_item(ID=123)
        mock_db.get_content().filter_by(ID=123).first.return_value = mock_content

        mock_join.return_value = "/path/to/output.mp3"
        mock_get_audio_info.return_value = {"bitrate": None, "bit_depth": 16}

        update_database_record(mock_db, 123, "output.mp3", "/path/to", "MP3")

        assert mock_content.BitRate == 320

    @patch("rekordbox_edit.commands.convert.get_file_type_for_format")
    @patch("rekordbox_edit.commands.convert.get_audio_info")
    @patch("os.path.join")
    def test_update_database_record_unsupported_format_raises(
        self, mock_join, mock_get_audio_info, mock_get_file_type, make_djmd_content_item
    ):
        """Unsupported output format raises an exception (when get_file_type returns None)."""
        mock_db = Mock()
        mock_content = make_djmd_content_item(ID=123)
        mock_db.get_content().filter_by(ID=123).first.return_value = mock_content

        mock_join.return_value = "/path/to/output.xyz"
        mock_get_audio_info.return_value = {"bitrate": 1000, "bit_depth": 16}
        mock_get_file_type.return_value = (
            None  # simulate unknown format slipping through
        )

        with pytest.raises(Exception, match="Unsupported output format"):
            update_database_record(mock_db, 123, "output.xyz", "/path/to", "XYZ")


class TestCleanupConvertedFiles:
    """Test cleanup_converted_files function."""

    @patch("os.remove")
    def test_cleanup_converted_files_success(self, mock_remove):
        """Test successful cleanup of converted files."""
        converted_files = [
            {"output_path": "/path/file1.aiff"},
            {"output_path": "/path/file2.aiff"},
        ]

        cleanup_converted_files(converted_files)

        assert mock_remove.call_count == 2
        mock_remove.assert_any_call("/path/file1.aiff")
        mock_remove.assert_any_call("/path/file2.aiff")

    @patch("os.remove")
    def test_cleanup_converted_files_with_error(self, mock_remove):
        """Test cleanup when file removal fails."""
        converted_files = [{"output_path": "/path/file1.aiff"}]
        mock_remove.side_effect = OSError("Permission denied")

        # Should not raise exception
        cleanup_converted_files(converted_files)

        mock_remove.assert_called_once_with("/path/file1.aiff")


class TestRollbackAndCleanup:
    """Test rollback_and_cleanup function."""

    def test_rolls_back_session(self, mock_db):
        """Calls db.session.rollback() when db and session are present."""
        rollback_and_cleanup(mock_db, [])
        mock_db.session.rollback.assert_called_once()

    def test_no_db_is_noop(self):
        """Does nothing when db is None."""
        rollback_and_cleanup(None, [])  # should not raise

    def test_no_session_is_noop(self):
        """Does nothing when db.session is None."""
        db = Mock()
        db.session = None
        rollback_and_cleanup(db, [])  # should not raise

    @patch("rekordbox_edit.commands.convert.cleanup_converted_files")
    def test_cleans_up_converted_files(self, mock_cleanup, mock_db):
        """Calls cleanup_converted_files when converted_files is non-empty."""
        converted_files = [{"output_path": "/path/file.aiff"}]
        rollback_and_cleanup(mock_db, converted_files)
        mock_cleanup.assert_called_once_with(converted_files)

    @patch("rekordbox_edit.commands.convert.cleanup_converted_files")
    def test_skips_cleanup_when_no_converted_files(self, mock_cleanup, mock_db):
        """Does not call cleanup_converted_files when converted_files is empty."""
        rollback_and_cleanup(mock_db, [])
        mock_cleanup.assert_not_called()

    @patch("rekordbox_edit.commands.convert.logger")
    def test_rollback_exception_logs_critical_and_reraises(self, mock_logger, mock_db):
        """When rollback raises, logs critical messages and re-raises the exception."""
        error = Exception("DB connection lost")
        mock_db.session.rollback.side_effect = error

        with pytest.raises(Exception, match="DB connection lost"):
            rollback_and_cleanup(mock_db, [])

        assert mock_logger.critical.call_count == 2


class TestGetOutputPath:
    """Test get_output_path function."""

    def test_get_output_path_basic(self, make_djmd_content_item):
        """Test basic output path calculation."""
        content = make_djmd_content_item(
            FileNameL="song.flac",
            FolderPath="/music/folder/song.flac",
        )

        output_path, output_filename, src_dirname = get_output_path(content, "aiff")

        assert output_path == os.path.normpath("/music/folder/song.aiff")
        assert output_filename == "song.aiff"
        assert src_dirname == os.path.normpath("/music/folder")

    def test_get_output_path_mp3(self, make_djmd_content_item):
        """Test output path calculation for MP3."""
        content = make_djmd_content_item(
            FileNameL="song.flac",
            FolderPath="/music/folder/song.flac",
        )

        output_path, output_filename, src_dirname = get_output_path(content, "mp3")

        assert output_path == os.path.normpath("/music/folder/song.mp3")
        assert output_filename == "song.mp3"
        assert src_dirname == os.path.normpath("/music/folder")


class TestConvertCommand:
    """Test convert_command function comprehensively."""

    @patch("rekordbox_edit.commands.convert.cleanup_converted_files")
    @patch("rekordbox_edit.commands.convert.confirm")
    @patch("rekordbox_edit.commands.convert.get_rekordbox_pid")
    @patch("rekordbox_edit.commands.convert.get_filtered_content")
    @patch("rekordbox_edit.commands.convert.Rekordbox6Database")
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    @patch("rekordbox_edit.commands.convert.convert_to_lossless")
    @patch("rekordbox_edit.commands.convert.update_database_record")
    @patch("os.path.exists")
    @patch("os.path.dirname")
    def test_convert_command_success_with_yes_flag(
        self,
        mock_dirname,
        mock_exists,
        mock_update_db,
        mock_convert,
        mock_ffmpeg_in_path,
        mock_db_class,
        mock_get_filtered_content,
        mock_get_rb_pid,
        mock_confirm,
        mock_cleanup_files,
        mock_logger,
        make_djmd_content_item,
    ):
        """Test convert_command successfully completes with --yes flag."""
        # Setup basic mocks
        mock_get_rb_pid.return_value = None  # Rekordbox not running
        mock_ffmpeg_in_path.return_value = True  # FFmpeg available
        mock_dirname.return_value = "/output/folder"
        mock_convert.return_value = True  # Conversion succeeds
        mock_update_db.return_value = True  # Database update succeeds
        mock_confirm.return_value = True
        mock_cleanup_files.return_value = None

        # Mock os.path.exists
        def mock_exists_side_effect(path):
            if path == "/music/folder/test_song.flac":
                return True
            if "test_song.aiff" in path and mock_convert.call_count > 0:
                return True
            return False

        mock_exists.side_effect = mock_exists_side_effect

        # Mock database
        mock_db = Mock()
        mock_db_class.return_value = mock_db
        mock_db.session = Mock()

        # Create a mock content object for conversion
        mock_flac_content = make_djmd_content_item(
            FileType=5,  # FLAC
            ID=123,
            FileNameL="test_song.flac",
            FolderPath="/music/folder/test_song.flac",
        )

        # Mock get_filtered_content to return our test content
        mock_result = Mock()
        mock_result.scalars().all.return_value = [mock_flac_content]
        mock_get_filtered_content.return_value = mock_result

        # Execute command
        from click.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(convert_command, ["--yes"])

        # Validate successful execution
        assert result.exit_code == 0

        mock_db.session.commit.assert_called_once()
        mock_logger.info.assert_any_call(
            String() & Regex(".*Found 1 files to convert.*")
        )
        mock_update_db.assert_called_once()
        mock_convert.assert_called_once()

    @patch("rekordbox_edit.commands.convert.print_track_info")
    @patch("rekordbox_edit.commands.convert.get_rekordbox_pid")
    @patch("rekordbox_edit.commands.convert.get_filtered_content")
    @patch("rekordbox_edit.commands.convert.Rekordbox6Database")
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    @patch("os.path.exists")
    def test_dry_run_shows_files_to_convert(
        self,
        mock_exists,
        mock_ffmpeg_in_path,
        mock_db_class,
        mock_get_filtered_content,
        mock_get_rb_pid,
        mock_print_track_info,
        mock_logger,
        make_djmd_content_item,
    ):
        """--dry-run shows files that would be converted without making changes."""
        mock_get_rb_pid.return_value = None
        mock_ffmpeg_in_path.return_value = True
        mock_exists.return_value = False

        mock_db = Mock()
        mock_db_class.return_value = mock_db
        mock_db.session = Mock()

        mock_content = make_djmd_content_item(
            FileType=5,
            ID="AAA111",
            FileNameL="song.flac",
            FolderPath="/music/song.flac",
        )
        mock_result = Mock()
        mock_result.scalars().all.return_value = [mock_content]
        mock_get_filtered_content.return_value = mock_result

        from click.testing import CliRunner

        result = CliRunner().invoke(convert_command, ["--dry-run"])

        assert result.exit_code == 0
        mock_print_track_info.assert_called_once_with([mock_content])
        mock_db.session.commit.assert_not_called()

    @patch("rekordbox_edit.commands.convert.get_rekordbox_pid")
    @patch("rekordbox_edit.commands.convert.get_filtered_content")
    @patch("rekordbox_edit.commands.convert.Rekordbox6Database")
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    def test_filters_passed_to_get_filtered_content(
        self,
        mock_ffmpeg_in_path,
        mock_db_class,
        mock_get_filtered_content,
        mock_get_rb_pid,
    ):
        """Filter options are forwarded correctly to get_filtered_content."""
        mock_get_rb_pid.return_value = None
        mock_ffmpeg_in_path.return_value = True

        mock_db = Mock()
        mock_db_class.return_value = mock_db
        mock_db.session = Mock()

        mock_result = Mock()
        mock_result.scalars().all.return_value = []
        mock_get_filtered_content.return_value = mock_result

        from click.testing import CliRunner

        CliRunner().invoke(
            convert_command,
            ["--dry-run", "--artist", "Daft Punk", "--format", "flac", "--match-all"],
        )

        call_kwargs = mock_get_filtered_content.call_args.kwargs
        assert call_kwargs["artists"] == ("Daft Punk",)
        assert call_kwargs["formats"] == ("flac",)
        assert call_kwargs["match_all"] is True

    @patch("rekordbox_edit.commands.convert.get_rekordbox_pid")
    @patch("rekordbox_edit.commands.convert.confirm")
    def test_convert_command_rekordbox_running_prompts(
        self,
        mock_confirm,
        mock_get_rb_pid,
    ):
        """Test convert_command prompts when Rekordbox is running."""
        mock_get_rb_pid.return_value = 12345  # Rekordbox is running
        mock_confirm.return_value = False  # User declines

        from click.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(convert_command, ["--dry-run"])

        # Should exit cleanly after user declines
        assert result.exit_code == 0
        mock_confirm.assert_called_once()

    @patch("rekordbox_edit.commands.convert.get_rekordbox_pid")
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    def test_convert_command_ffmpeg_not_available_error(
        self,
        mock_ffmpeg_in_path,
        mock_get_rb_pid,
    ):
        """Test convert_command exits when FFmpeg is not available."""
        mock_get_rb_pid.return_value = None
        mock_ffmpeg_in_path.return_value = False

        from click.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(convert_command, ["--dry-run"])

        assert result.exit_code == 1

    @patch("rekordbox_edit.commands.convert.print_track_info")
    @patch("rekordbox_edit.commands.convert.get_rekordbox_pid")
    @patch("rekordbox_edit.commands.convert.get_filtered_content")
    @patch("rekordbox_edit.commands.convert.Rekordbox6Database")
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    @patch("os.path.exists")
    def test_convert_command_filters_out_lossy_formats(
        self,
        mock_exists,
        mock_ffmpeg_in_path,
        mock_db_class,
        mock_get_filtered_content,
        mock_get_rb_pid,
        mock_print_track_info,
        mock_logger,
        make_djmd_content_item,
    ):
        """Test convert_command filters out MP3 and M4A files."""
        mock_get_rb_pid.return_value = None
        mock_ffmpeg_in_path.return_value = True
        mock_exists.return_value = False  # No output conflicts

        mock_db = Mock()
        mock_db_class.return_value = mock_db
        mock_db.session = Mock()

        mock_flac_content = make_djmd_content_item(
            FileType=5,  # FLAC
            ID="AAAAAA",
            FileNameL="song.flac",
            FolderPath="/music/song.flac",
        )

        mock_mp3_content = make_djmd_content_item(
            FileType=1,  # MP3
            ID="BBBBBB",
        )

        mock_m4a_content = make_djmd_content_item(
            FileType=4,  # M4A
            ID="CCCCCC",
        )

        mock_result = Mock()
        mock_result.scalars().all.return_value = [
            mock_flac_content,
            mock_mp3_content,
            mock_m4a_content,
        ]
        mock_get_filtered_content.return_value = mock_result

        from click.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(convert_command, ["--dry-run"])

        assert result.exit_code == 0
        mock_print_track_info.assert_called_once_with([mock_flac_content])

    @patch("rekordbox_edit.commands.convert.get_rekordbox_pid")
    @patch("rekordbox_edit.commands.convert.get_filtered_content")
    @patch("rekordbox_edit.commands.convert.Rekordbox6Database")
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    @patch("rekordbox_edit.commands.convert.print_track_info")
    def test_convert_command_no_files_to_convert(
        self,
        mock_print_track_info,
        mock_ffmpeg_in_path,
        mock_db_class,
        mock_get_filtered_content,
        mock_get_rb_pid,
    ):
        """Test convert_command when no files need conversion."""
        mock_get_rb_pid.return_value = None
        mock_ffmpeg_in_path.return_value = True

        mock_db = Mock()
        mock_db_class.return_value = mock_db
        mock_db.session = Mock()

        mock_result = Mock()
        mock_result.scalars().all.return_value = []
        mock_get_filtered_content.return_value = mock_result

        from click.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(convert_command, ["--dry-run"])

        assert result.exit_code == 0
        mock_print_track_info.assert_not_called()

    @patch("rekordbox_edit.commands.convert.print_track_info")
    @patch("rekordbox_edit.commands.convert.get_rekordbox_pid")
    @patch("rekordbox_edit.commands.convert.get_filtered_content")
    @patch("rekordbox_edit.commands.convert.Rekordbox6Database")
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    @patch("os.path.exists")
    def test_convert_command_conflict_detection_without_overwrite(
        self,
        mock_exists,
        mock_ffmpeg_in_path,
        mock_db_class,
        mock_get_filtered_content,
        mock_get_rb_pid,
        mock_print_track_info,
        mock_logger,
        make_djmd_content_item,
    ):
        """Test convert_command detects conflicts and skips without --overwrite."""
        mock_get_rb_pid.return_value = None
        mock_ffmpeg_in_path.return_value = True

        # Output file already exists
        mock_exists.return_value = True

        mock_db = Mock()
        mock_db_class.return_value = mock_db
        mock_db.session = Mock()

        mock_flac_content = make_djmd_content_item(
            FileType=5,
            ID="AAAAAA",
            FileNameL="song.flac",
            FolderPath="/music/song.flac",
        )

        mock_result = Mock()
        mock_result.scalars().all.return_value = [mock_flac_content]
        mock_get_filtered_content.return_value = mock_result

        from click.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(convert_command, ["--dry-run"])

        assert result.exit_code == 0
        # Should warn about conflicts
        mock_logger.warning.assert_any_call(
            String()
            & Regex(".*Skipping 1 files \\(output exists, use --overwrite\\).*")
        )

    @patch("rekordbox_edit.commands.convert.print_track_info")
    @patch("rekordbox_edit.commands.convert.get_rekordbox_pid")
    @patch("rekordbox_edit.commands.convert.get_filtered_content")
    @patch("rekordbox_edit.commands.convert.Rekordbox6Database")
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    @patch("os.path.exists")
    def test_convert_command_conflict_with_overwrite(
        self,
        mock_exists,
        mock_ffmpeg_in_path,
        mock_db_class,
        mock_get_filtered_content,
        mock_get_rb_pid,
        mock_print_track_info,
        mock_logger,
        make_djmd_content_item,
    ):
        """Test convert_command includes conflicts with --overwrite flag."""
        mock_get_rb_pid.return_value = None
        mock_ffmpeg_in_path.return_value = True
        mock_exists.return_value = True  # Output exists

        mock_db = Mock()
        mock_db_class.return_value = mock_db
        mock_db.session = Mock()

        mock_flac_content = make_djmd_content_item(
            FileType=5,
            ID="AAAAAA",
            FileNameL="song.flac",
            FolderPath="/music/song.flac",
        )

        mock_result = Mock()
        mock_result.scalars().all.return_value = [mock_flac_content]
        mock_get_filtered_content.return_value = mock_result

        from click.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(convert_command, ["--dry-run", "--overwrite"])

        assert result.exit_code == 0
        # Should info about overwriting
        mock_logger.info.assert_any_call(
            String() & Regex(".*1 output files exist \\(will overwrite\\).*")
        )
        # Should still show files to convert
        mock_print_track_info.assert_called_once()

    @patch("os.remove")
    @patch("rekordbox_edit.commands.convert.cleanup_converted_files")
    @patch("rekordbox_edit.commands.convert.confirm")
    @patch("rekordbox_edit.commands.convert.get_rekordbox_pid")
    @patch("rekordbox_edit.commands.convert.get_filtered_content")
    @patch("rekordbox_edit.commands.convert.Rekordbox6Database")
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    @patch("rekordbox_edit.commands.convert.convert_to_lossless")
    @patch("rekordbox_edit.commands.convert.update_database_record")
    @patch("os.path.exists")
    def test_convert_command_delete_flag_removes_originals(
        self,
        mock_exists,
        mock_update_db,
        mock_convert,
        mock_ffmpeg_in_path,
        mock_db_class,
        mock_get_filtered_content,
        mock_get_rb_pid,
        mock_confirm,
        mock_cleanup_files,
        mock_remove,
        mock_logger,
        make_djmd_content_item,
    ):
        """Test convert_command with --delete flag removes original files."""
        mock_get_rb_pid.return_value = None
        mock_ffmpeg_in_path.return_value = True
        mock_convert.return_value = True
        mock_update_db.return_value = True
        mock_confirm.return_value = True

        def mock_exists_side_effect(path):
            if path == "/music/folder/test_song.flac":
                return True
            if "test_song.aiff" in path:
                return mock_convert.call_count > 0
            return False

        mock_exists.side_effect = mock_exists_side_effect

        mock_db = Mock()
        mock_db_class.return_value = mock_db
        mock_db.session = Mock()

        mock_flac_content = make_djmd_content_item(
            FileType=5,
            ID=123,
            FileNameL="test_song.flac",
            FolderPath="/music/folder/test_song.flac",
        )

        mock_result = Mock()
        mock_result.scalars().all.return_value = [mock_flac_content]
        mock_get_filtered_content.return_value = mock_result

        from click.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(convert_command, ["--yes", "--delete"])

        assert result.exit_code == 0
        mock_remove.assert_called_once_with("/music/folder/test_song.flac")
        mock_logger.info.assert_any_call("Deleted 1 original files")

    def test_convert_print_ids_requires_dry_run_or_yes(self):
        """Test --print=ids requires --dry-run or --yes."""
        from click.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(convert_command, ["--print", "ids"])

        assert result.exit_code != 0
        assert (
            "--print=ids or --print=silent requires --dry-run or --yes" in result.output
        )

    def test_convert_print_silent_requires_dry_run_or_yes(self):
        """Test --print=silent requires --dry-run or --yes."""
        from click.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(convert_command, ["--print", "silent"])

        assert result.exit_code != 0
        assert (
            "--print=ids or --print=silent requires --dry-run or --yes" in result.output
        )

    @patch("rekordbox_edit.commands.convert.print_track_info")
    @patch("rekordbox_edit.commands.convert.get_rekordbox_pid")
    @patch("rekordbox_edit.commands.convert.get_filtered_content")
    @patch("rekordbox_edit.commands.convert.Rekordbox6Database")
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    @patch("os.path.exists")
    def test_convert_print_ids_with_dry_run(
        self,
        mock_exists,
        mock_ffmpeg_in_path,
        mock_db_class,
        mock_get_filtered_content,
        mock_get_rb_pid,
        mock_print_track_info,
        make_djmd_content_item,
    ):
        """Test --print=ids with --dry-run outputs IDs of would-be-converted files."""
        mock_get_rb_pid.return_value = None
        mock_ffmpeg_in_path.return_value = True
        mock_exists.return_value = False

        mock_db = Mock()
        mock_db_class.return_value = mock_db
        mock_db.session = Mock()

        mock_content1 = make_djmd_content_item(FileType=5, ID="AAA111")
        mock_content2 = make_djmd_content_item(FileType=5, ID="BBB222")

        mock_result = Mock()
        mock_result.scalars().all.return_value = [mock_content1, mock_content2]
        mock_get_filtered_content.return_value = mock_result

        from click.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(convert_command, ["--print", "ids", "--dry-run"])

        assert result.exit_code == 0
        assert "AAA111 BBB222" in result.output

    @patch("rekordbox_edit.commands.convert.print_track_info")
    @patch("rekordbox_edit.commands.convert.get_rekordbox_pid")
    @patch("rekordbox_edit.commands.convert.get_filtered_content")
    @patch("rekordbox_edit.commands.convert.Rekordbox6Database")
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    @patch("os.path.exists")
    def test_convert_print_silent_with_dry_run(
        self,
        mock_exists,
        mock_ffmpeg_in_path,
        mock_db_class,
        mock_get_filtered_content,
        mock_get_rb_pid,
        mock_print_track_info,
        make_djmd_content_item,
    ):
        """Test --print=silent with --dry-run produces no output."""
        mock_get_rb_pid.return_value = None
        mock_ffmpeg_in_path.return_value = True
        mock_exists.return_value = False

        mock_db = Mock()
        mock_db_class.return_value = mock_db
        mock_db.session = Mock()

        mock_content = make_djmd_content_item(FileType=5, ID="AAA111")

        mock_result = Mock()
        mock_result.scalars().all.return_value = [mock_content]
        mock_get_filtered_content.return_value = mock_result

        from click.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(convert_command, ["--print", "silent", "--dry-run"])

        assert result.exit_code == 0
        # Should have no output (no IDs, no track info)
        assert result.output.strip() == ""

    @patch("rekordbox_edit.commands.convert.get_rekordbox_pid")
    def test_convert_rekordbox_running_scripting_mode_errors(
        self,
        mock_get_rb_pid,
        mock_logger,
    ):
        """Test --print=ids/silent errors when Rekordbox is running."""
        mock_get_rb_pid.return_value = 12345  # Rekordbox is running

        from click.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(convert_command, ["--print", "ids", "--dry-run"])

        assert result.exit_code == 1
        mock_logger.error.assert_any_call(
            String()
            & Regex(".*Rekordbox is running.*Cannot proceed in scripting mode.*")
        )

    @patch("rekordbox_edit.commands.convert.print_track_info")
    @patch("rekordbox_edit.commands.convert.get_rekordbox_pid")
    @patch("rekordbox_edit.commands.convert.get_filtered_content")
    @patch("rekordbox_edit.commands.convert.Rekordbox6Database")
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    @patch("os.path.exists")
    def test_convert_conflicts_silent_with_yes(
        self,
        mock_exists,
        mock_ffmpeg_in_path,
        mock_db_class,
        mock_get_filtered_content,
        mock_get_rb_pid,
        mock_print_track_info,
        mock_logger,
        make_djmd_content_item,
    ):
        """Test --yes without --overwrite skips conflicts silently."""
        mock_get_rb_pid.return_value = None
        mock_ffmpeg_in_path.return_value = True
        mock_exists.return_value = True  # Output file exists (conflict)

        mock_db = Mock()
        mock_db_class.return_value = mock_db
        mock_db.session = Mock()

        mock_content = make_djmd_content_item(
            FileType=5,
            ID="AAA111",
            FileNameL="song.flac",
            FolderPath="/music/song.flac",
        )

        mock_result = Mock()
        mock_result.scalars().all.return_value = [mock_content]
        mock_get_filtered_content.return_value = mock_result

        from click.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(convert_command, ["--yes"])

        assert result.exit_code == 0
        # Should NOT warn about conflicts when --yes is used
        for call in mock_logger.warning.call_args_list:
            assert "Skipping" not in str(call)
            assert "output exists" not in str(call)

    @patch("os.remove")
    @patch("rekordbox_edit.commands.convert.cleanup_converted_files")
    @patch("rekordbox_edit.commands.convert.get_rekordbox_pid")
    @patch("rekordbox_edit.commands.convert.get_filtered_content")
    @patch("rekordbox_edit.commands.convert.Rekordbox6Database")
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    @patch("rekordbox_edit.commands.convert.convert_to_lossless")
    @patch("rekordbox_edit.commands.convert.update_database_record")
    @patch("os.path.exists")
    def test_convert_delete_default_lossless(
        self,
        mock_exists,
        mock_update_db,
        mock_convert,
        mock_ffmpeg_in_path,
        mock_db_class,
        mock_get_filtered_content,
        mock_get_rb_pid,
        mock_cleanup_files,
        mock_remove,
        mock_logger,
        make_djmd_content_item,
    ):
        """Test lossless output defaults to deleting original files."""
        mock_get_rb_pid.return_value = None
        mock_ffmpeg_in_path.return_value = True
        mock_convert.return_value = True
        mock_update_db.return_value = True

        def mock_exists_side_effect(path):
            if path == "/music/folder/song.flac":
                return True
            if "song.aiff" in path:
                return mock_convert.call_count > 0
            return False

        mock_exists.side_effect = mock_exists_side_effect

        mock_db = Mock()
        mock_db_class.return_value = mock_db
        mock_db.session = Mock()

        mock_content = make_djmd_content_item(
            FileType=5,
            ID=123,
            FileNameL="song.flac",
            FolderPath="/music/folder/song.flac",
        )

        mock_result = Mock()
        mock_result.scalars().all.return_value = [mock_content]
        mock_get_filtered_content.return_value = mock_result

        from click.testing import CliRunner

        runner = CliRunner()
        # No --delete flag, but lossless output should default to delete
        result = runner.invoke(convert_command, ["--yes", "--format-out", "aiff"])

        assert result.exit_code == 0
        mock_remove.assert_called_once_with("/music/folder/song.flac")

    @patch("os.remove")
    @patch("rekordbox_edit.commands.convert.cleanup_converted_files")
    @patch("rekordbox_edit.commands.convert.get_rekordbox_pid")
    @patch("rekordbox_edit.commands.convert.get_filtered_content")
    @patch("rekordbox_edit.commands.convert.Rekordbox6Database")
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    @patch("rekordbox_edit.commands.convert.convert_to_mp3")
    @patch("rekordbox_edit.commands.convert.update_database_record")
    @patch("os.path.exists")
    def test_convert_delete_default_mp3(
        self,
        mock_exists,
        mock_update_db,
        mock_convert,
        mock_ffmpeg_in_path,
        mock_db_class,
        mock_get_filtered_content,
        mock_get_rb_pid,
        mock_cleanup_files,
        mock_remove,
        mock_logger,
        make_djmd_content_item,
    ):
        """Test MP3 output defaults to keeping original files."""
        mock_get_rb_pid.return_value = None
        mock_ffmpeg_in_path.return_value = True
        mock_convert.return_value = True
        mock_update_db.return_value = True

        def mock_exists_side_effect(path):
            if path == "/music/folder/song.flac":
                return True
            if "song.mp3" in path:
                return mock_convert.call_count > 0
            return False

        mock_exists.side_effect = mock_exists_side_effect

        mock_db = Mock()
        mock_db_class.return_value = mock_db
        mock_db.session = Mock()

        mock_content = make_djmd_content_item(
            FileType=5,
            ID=123,
            FileNameL="song.flac",
            FolderPath="/music/folder/song.flac",
        )

        mock_result = Mock()
        mock_result.scalars().all.return_value = [mock_content]
        mock_get_filtered_content.return_value = mock_result

        from click.testing import CliRunner

        runner = CliRunner()
        # No --delete flag, MP3 output should default to keep
        result = runner.invoke(convert_command, ["--yes", "--format-out", "mp3"])

        assert result.exit_code == 0
        mock_remove.assert_not_called()

    @patch("os.remove")
    @patch("rekordbox_edit.commands.convert.cleanup_converted_files")
    @patch("rekordbox_edit.commands.convert.get_rekordbox_pid")
    @patch("rekordbox_edit.commands.convert.get_filtered_content")
    @patch("rekordbox_edit.commands.convert.Rekordbox6Database")
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    @patch("rekordbox_edit.commands.convert.convert_to_lossless")
    @patch("rekordbox_edit.commands.convert.update_database_record")
    @patch("os.path.exists")
    def test_convert_keep_flag_overrides_lossless_default(
        self,
        mock_exists,
        mock_update_db,
        mock_convert,
        mock_ffmpeg_in_path,
        mock_db_class,
        mock_get_filtered_content,
        mock_get_rb_pid,
        mock_cleanup_files,
        mock_remove,
        mock_logger,
        make_djmd_content_item,
    ):
        """Test --keep prevents deletion even for lossless output."""
        mock_get_rb_pid.return_value = None
        mock_ffmpeg_in_path.return_value = True
        mock_convert.return_value = True
        mock_update_db.return_value = True

        def mock_exists_side_effect(path):
            if path == "/music/folder/song.flac":
                return True
            if "song.aiff" in path:
                return mock_convert.call_count > 0
            return False

        mock_exists.side_effect = mock_exists_side_effect

        mock_db = Mock()
        mock_db_class.return_value = mock_db
        mock_db.session = Mock()

        mock_content = make_djmd_content_item(
            FileType=5,
            ID=123,
            FileNameL="song.flac",
            FolderPath="/music/folder/song.flac",
        )

        mock_result = Mock()
        mock_result.scalars().all.return_value = [mock_content]
        mock_get_filtered_content.return_value = mock_result

        from click.testing import CliRunner

        runner = CliRunner()
        # --keep should override the lossless default
        result = runner.invoke(convert_command, ["--yes", "--keep"])

        assert result.exit_code == 0
        mock_remove.assert_not_called()

    @patch("os.remove")
    @patch("rekordbox_edit.commands.convert.cleanup_converted_files")
    @patch("rekordbox_edit.commands.convert.get_rekordbox_pid")
    @patch("rekordbox_edit.commands.convert.get_filtered_content")
    @patch("rekordbox_edit.commands.convert.Rekordbox6Database")
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    @patch("rekordbox_edit.commands.convert.convert_to_mp3")
    @patch("rekordbox_edit.commands.convert.update_database_record")
    @patch("os.path.exists")
    def test_convert_delete_flag_overrides_mp3_default(
        self,
        mock_exists,
        mock_update_db,
        mock_convert,
        mock_ffmpeg_in_path,
        mock_db_class,
        mock_get_filtered_content,
        mock_get_rb_pid,
        mock_cleanup_files,
        mock_remove,
        mock_logger,
        make_djmd_content_item,
    ):
        """Test --delete forces deletion even for MP3 output."""
        mock_get_rb_pid.return_value = None
        mock_ffmpeg_in_path.return_value = True
        mock_convert.return_value = True
        mock_update_db.return_value = True

        def mock_exists_side_effect(path):
            if path == "/music/folder/song.flac":
                return True
            if "song.mp3" in path:
                return mock_convert.call_count > 0
            return False

        mock_exists.side_effect = mock_exists_side_effect

        mock_db = Mock()
        mock_db_class.return_value = mock_db
        mock_db.session = Mock()

        mock_content = make_djmd_content_item(
            FileType=5,
            ID=123,
            FileNameL="song.flac",
            FolderPath="/music/folder/song.flac",
        )

        mock_result = Mock()
        mock_result.scalars().all.return_value = [mock_content]
        mock_get_filtered_content.return_value = mock_result

        from click.testing import CliRunner

        runner = CliRunner()
        # --delete should override the MP3 default
        result = runner.invoke(
            convert_command, ["--yes", "--format-out", "mp3", "--delete"]
        )

        assert result.exit_code == 0
        mock_remove.assert_called_once_with("/music/folder/song.flac")

    @patch("rekordbox_edit.commands.convert.cleanup_converted_files")
    @patch("rekordbox_edit.commands.convert.get_rekordbox_pid")
    @patch("rekordbox_edit.commands.convert.get_filtered_content")
    @patch("rekordbox_edit.commands.convert.Rekordbox6Database")
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    @patch("rekordbox_edit.commands.convert.convert_to_lossless")
    @patch("rekordbox_edit.commands.convert.update_database_record")
    @patch("os.path.exists")
    @patch("os.remove")
    def test_convert_print_ids_with_yes_outputs_converted_ids(
        self,
        mock_remove,
        mock_exists,
        mock_update_db,
        mock_convert,
        mock_ffmpeg_in_path,
        mock_db_class,
        mock_get_filtered_content,
        mock_get_rb_pid,
        mock_cleanup_files,
        make_djmd_content_item,
    ):
        """Test --print=ids with --yes outputs IDs of actually converted files."""
        mock_get_rb_pid.return_value = None
        mock_ffmpeg_in_path.return_value = True
        mock_convert.return_value = True
        mock_update_db.return_value = True

        def mock_exists_side_effect(path):
            if "song.flac" in path:
                return True
            if "song.aiff" in path:
                return mock_convert.call_count > 0
            return False

        mock_exists.side_effect = mock_exists_side_effect

        mock_db = Mock()
        mock_db_class.return_value = mock_db
        mock_db.session = Mock()

        mock_content = make_djmd_content_item(
            FileType=5,
            ID="XYZ789",
            FileNameL="song.flac",
            FolderPath="/music/folder/song.flac",
        )

        mock_result = Mock()
        mock_result.scalars().all.return_value = [mock_content]
        mock_get_filtered_content.return_value = mock_result

        from click.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(convert_command, ["--print", "ids", "--yes", "--keep"])

        assert result.exit_code == 0
        assert "XYZ789" in result.output


class TestConvertCommandErrorPaths:
    """Tests for convert_command error handling and edge case branches."""

    @patch("rekordbox_edit.commands.convert.get_rekordbox_pid")
    @patch("rekordbox_edit.commands.convert.Rekordbox6Database")
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    def test_convert_command_no_db_session_exits(
        self,
        mock_ffmpeg_in_path,
        mock_db_class,
        mock_get_rb_pid,
        mock_db,
    ):
        """Raises and exits when the database has no session."""
        mock_get_rb_pid.return_value = None
        mock_ffmpeg_in_path.return_value = True
        mock_db.session = None
        mock_db_class.return_value = mock_db

        from click.testing import CliRunner

        result = CliRunner().invoke(convert_command, ["--dry-run"])

        assert result.exit_code != 0

    @patch("rekordbox_edit.commands.convert.get_rekordbox_pid")
    @patch("rekordbox_edit.commands.convert.confirm")
    def test_convert_command_rekordbox_running_user_quits(
        self,
        mock_confirm,
        mock_get_rb_pid,
    ):
        """Returns cleanly when UserQuit is raised from the Rekordbox-running prompt."""
        mock_get_rb_pid.return_value = 12345
        mock_confirm.side_effect = UserQuit()

        from click.testing import CliRunner

        result = CliRunner().invoke(convert_command, ["--dry-run"])

        assert result.exit_code == 0

    @patch("rekordbox_edit.commands.convert.print_track_info")
    @patch("rekordbox_edit.commands.convert.get_rekordbox_pid")
    @patch("rekordbox_edit.commands.convert.get_filtered_content")
    @patch("rekordbox_edit.commands.convert.Rekordbox6Database")
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    @patch("os.path.exists")
    def test_convert_command_yes_partial_conflicts_continues(
        self,
        mock_exists,
        mock_ffmpeg_in_path,
        mock_db_class,
        mock_get_filtered_content,
        mock_get_rb_pid,
        mock_print_track_info,
        mock_logger,
        make_djmd_content_item,
        mock_db,
    ):
        """--yes with partial conflicts skips conflicting files and processes the rest."""
        mock_get_rb_pid.return_value = None
        mock_ffmpeg_in_path.return_value = True
        mock_db_class.return_value = mock_db

        content1 = make_djmd_content_item(
            FileType=5, ID="AAA", FileNameL="song1.flac", FolderPath="/music/song1.flac"
        )
        content2 = make_djmd_content_item(
            FileType=5, ID="BBB", FileNameL="song2.flac", FolderPath="/music/song2.flac"
        )
        mock_result = Mock()
        mock_result.scalars().all.return_value = [content1, content2]
        mock_get_filtered_content.return_value = mock_result

        mock_exists.side_effect = lambda path: "song1.aiff" in path

        from click.testing import CliRunner

        result = CliRunner().invoke(convert_command, ["--yes", "--dry-run"])

        assert result.exit_code == 0
        mock_print_track_info.assert_called_once_with([content2])

    @patch("rekordbox_edit.commands.convert.print_track_info")
    @patch("rekordbox_edit.commands.convert.get_rekordbox_pid")
    @patch("rekordbox_edit.commands.convert.get_filtered_content")
    @patch("rekordbox_edit.commands.convert.Rekordbox6Database")
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    @patch("os.path.exists")
    def test_convert_command_partial_conflicts_no_overwrite_continues(
        self,
        mock_exists,
        mock_ffmpeg_in_path,
        mock_db_class,
        mock_get_filtered_content,
        mock_get_rb_pid,
        mock_print_track_info,
        mock_logger,
        make_djmd_content_item,
        mock_db,
    ):
        """Without --overwrite, conflicting files are warned and skipped; others proceed."""
        mock_get_rb_pid.return_value = None
        mock_ffmpeg_in_path.return_value = True
        mock_db_class.return_value = mock_db

        content1 = make_djmd_content_item(
            FileType=5, ID="AAA", FileNameL="song1.flac", FolderPath="/music/song1.flac"
        )
        content2 = make_djmd_content_item(
            FileType=5, ID="BBB", FileNameL="song2.flac", FolderPath="/music/song2.flac"
        )
        mock_result = Mock()
        mock_result.scalars().all.return_value = [content1, content2]
        mock_get_filtered_content.return_value = mock_result

        mock_exists.side_effect = lambda path: "song1.aiff" in path

        from click.testing import CliRunner

        result = CliRunner().invoke(convert_command, ["--dry-run"])

        assert result.exit_code == 0
        mock_logger.warning.assert_called()
        mock_print_track_info.assert_called_once_with([content2])

    @patch("rekordbox_edit.commands.convert.sys")
    @patch("rekordbox_edit.commands.convert.confirm")
    @patch("rekordbox_edit.commands.convert.get_rekordbox_pid")
    @patch("rekordbox_edit.commands.convert.get_filtered_content")
    @patch("rekordbox_edit.commands.convert.Rekordbox6Database")
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    @patch("os.path.exists")
    def test_convert_command_user_declines_batch_confirmation(
        self,
        mock_exists,
        mock_ffmpeg_in_path,
        mock_db_class,
        mock_get_filtered_content,
        mock_get_rb_pid,
        mock_confirm,
        mock_sys,
        mock_logger,
        make_djmd_content_item,
        mock_db,
    ):
        """Returns cleanly when user declines the batch conversion confirmation."""
        mock_sys.stdin.isatty.return_value = True  # not piped — avoids UsageError
        mock_sys.exit.side_effect = SystemExit
        mock_get_rb_pid.return_value = None
        mock_ffmpeg_in_path.return_value = True
        mock_exists.return_value = False
        mock_confirm.return_value = False
        mock_db_class.return_value = mock_db

        mock_result = Mock()
        mock_result.scalars().all.return_value = [
            make_djmd_content_item(
                FileType=5,
                ID="AAA",
                FileNameL="song.flac",
                FolderPath="/music/song.flac",
            )
        ]
        mock_get_filtered_content.return_value = mock_result

        from click.testing import CliRunner

        result = CliRunner().invoke(convert_command, [])

        assert result.exit_code == 0
        mock_logger.info.assert_any_call("Cancelled.")

    @patch("rekordbox_edit.commands.convert.sys")
    @patch("rekordbox_edit.commands.convert.confirm")
    @patch("rekordbox_edit.commands.convert.get_rekordbox_pid")
    @patch("rekordbox_edit.commands.convert.get_filtered_content")
    @patch("rekordbox_edit.commands.convert.Rekordbox6Database")
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    @patch("os.path.exists")
    def test_convert_command_userquit_during_batch_confirmation(
        self,
        mock_exists,
        mock_ffmpeg_in_path,
        mock_db_class,
        mock_get_filtered_content,
        mock_get_rb_pid,
        mock_confirm,
        mock_sys,
        mock_logger,
        make_djmd_content_item,
        mock_db,
    ):
        """Returns cleanly when UserQuit is raised during the batch confirmation."""
        mock_sys.stdin.isatty.return_value = True  # not piped — avoids UsageError
        mock_sys.exit.side_effect = SystemExit
        mock_get_rb_pid.return_value = None
        mock_ffmpeg_in_path.return_value = True
        mock_exists.return_value = False
        mock_confirm.side_effect = UserQuit()
        mock_db_class.return_value = mock_db

        mock_result = Mock()
        mock_result.scalars().all.return_value = [
            make_djmd_content_item(
                FileType=5,
                ID="AAA",
                FileNameL="song.flac",
                FolderPath="/music/song.flac",
            )
        ]
        mock_get_filtered_content.return_value = mock_result

        from click.testing import CliRunner

        result = CliRunner().invoke(convert_command, [])

        assert result.exit_code == 0

    @patch("rekordbox_edit.commands.convert.confirm")
    @patch("rekordbox_edit.commands.convert.get_rekordbox_pid")
    @patch("rekordbox_edit.commands.convert.get_filtered_content")
    @patch("rekordbox_edit.commands.convert.Rekordbox6Database")
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    @patch("os.path.exists")
    def test_convert_command_interactive_user_skips_file(
        self,
        mock_exists,
        mock_ffmpeg_in_path,
        mock_db_class,
        mock_get_filtered_content,
        mock_get_rb_pid,
        mock_confirm,
        mock_logger,
        make_djmd_content_item,
        mock_db,
    ):
        """With --interactive, declining per-file confirmation skips that file."""
        mock_get_rb_pid.return_value = None
        mock_ffmpeg_in_path.return_value = True
        mock_exists.return_value = False
        mock_confirm.return_value = False
        mock_db_class.return_value = mock_db

        mock_result = Mock()
        mock_result.scalars().all.return_value = [
            make_djmd_content_item(
                FileType=5,
                ID="AAA",
                FileNameL="song.flac",
                FolderPath="/music/song.flac",
            )
        ]
        mock_get_filtered_content.return_value = mock_result

        from click.testing import CliRunner

        # --yes skips the batch confirm and avoids the piped-stdin UsageError;
        # --interactive still triggers per-file confirmation
        result = CliRunner().invoke(convert_command, ["--interactive", "--yes"])

        assert result.exit_code == 0
        mock_logger.info.assert_any_call("No files were converted.")

    @patch("rekordbox_edit.commands.convert.confirm")
    @patch("rekordbox_edit.commands.convert.get_rekordbox_pid")
    @patch("rekordbox_edit.commands.convert.get_filtered_content")
    @patch("rekordbox_edit.commands.convert.Rekordbox6Database")
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    @patch("os.path.exists")
    def test_convert_command_interactive_user_quits(
        self,
        mock_exists,
        mock_ffmpeg_in_path,
        mock_db_class,
        mock_get_filtered_content,
        mock_get_rb_pid,
        mock_confirm,
        mock_logger,
        make_djmd_content_item,
        mock_db,
    ):
        """With --interactive, UserQuit during per-file confirmation rolls back and exits."""
        mock_get_rb_pid.return_value = None
        mock_ffmpeg_in_path.return_value = True
        mock_exists.return_value = False
        mock_confirm.side_effect = UserQuit()
        mock_db_class.return_value = mock_db

        mock_result = Mock()
        mock_result.scalars().all.return_value = [
            make_djmd_content_item(
                FileType=5,
                ID="AAA",
                FileNameL="song.flac",
                FolderPath="/music/song.flac",
            )
        ]
        mock_get_filtered_content.return_value = mock_result

        from click.testing import CliRunner

        result = CliRunner().invoke(convert_command, ["--interactive", "--yes"])

        assert result.exit_code == 0
        mock_logger.info.assert_any_call("User quit. Rolling back...")

    @patch("rekordbox_edit.commands.convert.get_rekordbox_pid")
    @patch("rekordbox_edit.commands.convert.get_filtered_content")
    @patch("rekordbox_edit.commands.convert.Rekordbox6Database")
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    @patch("os.path.exists")
    def test_convert_command_source_not_found_exits(
        self,
        mock_exists,
        mock_ffmpeg_in_path,
        mock_db_class,
        mock_get_filtered_content,
        mock_get_rb_pid,
        mock_logger,
        make_djmd_content_item,
        mock_db,
    ):
        """Exits with error when the source file does not exist."""
        mock_get_rb_pid.return_value = None
        mock_ffmpeg_in_path.return_value = True
        mock_exists.return_value = False
        mock_db_class.return_value = mock_db

        mock_result = Mock()
        mock_result.scalars().all.return_value = [
            make_djmd_content_item(
                FileType=5,
                ID="AAA",
                FileNameL="song.flac",
                FolderPath="/music/song.flac",
            )
        ]
        mock_get_filtered_content.return_value = mock_result

        from click.testing import CliRunner

        result = CliRunner().invoke(convert_command, ["--yes"])

        assert result.exit_code == 1
        mock_logger.error.assert_any_call("  Source not found: /music/song.flac")

    @patch("rekordbox_edit.commands.convert.convert_to_lossless")
    @patch("rekordbox_edit.commands.convert.get_rekordbox_pid")
    @patch("rekordbox_edit.commands.convert.get_filtered_content")
    @patch("rekordbox_edit.commands.convert.Rekordbox6Database")
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    @patch("os.path.exists")
    def test_convert_command_conversion_fails_exits(
        self,
        mock_exists,
        mock_ffmpeg_in_path,
        mock_db_class,
        mock_get_filtered_content,
        mock_get_rb_pid,
        mock_convert,
        mock_logger,
        make_djmd_content_item,
        mock_db,
    ):
        """Exits with error and rolls back when conversion fails."""
        mock_get_rb_pid.return_value = None
        mock_ffmpeg_in_path.return_value = True
        mock_convert.return_value = False
        mock_exists.side_effect = lambda path: "song.flac" in path
        mock_db_class.return_value = mock_db

        mock_result = Mock()
        mock_result.scalars().all.return_value = [
            make_djmd_content_item(
                FileType=5,
                ID="AAA",
                FileNameL="song.flac",
                FolderPath="/music/song.flac",
            )
        ]
        mock_get_filtered_content.return_value = mock_result

        from click.testing import CliRunner

        result = CliRunner().invoke(convert_command, ["--yes"])

        assert result.exit_code == 1
        mock_logger.error.assert_any_call("  Conversion failed. Aborting.")

    @patch("rekordbox_edit.commands.convert.convert_to_lossless")
    @patch("rekordbox_edit.commands.convert.get_rekordbox_pid")
    @patch("rekordbox_edit.commands.convert.get_filtered_content")
    @patch("rekordbox_edit.commands.convert.Rekordbox6Database")
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    @patch("os.path.exists")
    def test_convert_command_output_not_created_exits(
        self,
        mock_exists,
        mock_ffmpeg_in_path,
        mock_db_class,
        mock_get_filtered_content,
        mock_get_rb_pid,
        mock_convert,
        mock_logger,
        make_djmd_content_item,
        mock_db,
    ):
        """Exits with error when conversion succeeds but the output file is not created."""
        mock_get_rb_pid.return_value = None
        mock_ffmpeg_in_path.return_value = True
        mock_convert.return_value = True
        mock_exists.side_effect = lambda path: (
            "song.flac" in path
        )  # output never appears
        mock_db_class.return_value = mock_db

        mock_result = Mock()
        mock_result.scalars().all.return_value = [
            make_djmd_content_item(
                FileType=5,
                ID="AAA",
                FileNameL="song.flac",
                FolderPath="/music/song.flac",
            )
        ]
        mock_get_filtered_content.return_value = mock_result

        from click.testing import CliRunner

        result = CliRunner().invoke(convert_command, ["--yes"])

        assert result.exit_code == 1
        mock_logger.error.assert_any_call("  Output file not created. Aborting.")

    @patch("rekordbox_edit.commands.convert.update_database_record")
    @patch("rekordbox_edit.commands.convert.convert_to_lossless")
    @patch("rekordbox_edit.commands.convert.get_rekordbox_pid")
    @patch("rekordbox_edit.commands.convert.get_filtered_content")
    @patch("rekordbox_edit.commands.convert.Rekordbox6Database")
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    @patch("os.path.exists")
    def test_convert_command_db_update_fails_exits(
        self,
        mock_exists,
        mock_ffmpeg_in_path,
        mock_db_class,
        mock_get_filtered_content,
        mock_get_rb_pid,
        mock_convert,
        mock_update_db,
        mock_logger,
        make_djmd_content_item,
        mock_db,
    ):
        """Exits with error and rolls back when the database update fails."""
        mock_get_rb_pid.return_value = None
        mock_ffmpeg_in_path.return_value = True
        mock_convert.return_value = True
        mock_update_db.side_effect = Exception("DB write failed")
        mock_exists.side_effect = lambda path: (
            "song.flac" in path or (mock_convert.call_count > 0 and "song.aiff" in path)
        )
        mock_db_class.return_value = mock_db

        mock_result = Mock()
        mock_result.scalars().all.return_value = [
            make_djmd_content_item(
                FileType=5,
                ID="AAA",
                FileNameL="song.flac",
                FolderPath="/music/song.flac",
            )
        ]
        mock_get_filtered_content.return_value = mock_result

        from click.testing import CliRunner

        result = CliRunner().invoke(convert_command, ["--yes"])

        assert result.exit_code == 1
        mock_logger.error.assert_any_call("  Database update failed: DB write failed")

    @patch("rekordbox_edit.commands.convert.update_database_record")
    @patch("rekordbox_edit.commands.convert.convert_to_lossless")
    @patch("rekordbox_edit.commands.convert.get_rekordbox_pid")
    @patch("rekordbox_edit.commands.convert.get_filtered_content")
    @patch("rekordbox_edit.commands.convert.Rekordbox6Database")
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    @patch("os.path.exists")
    def test_convert_command_commit_fails_exits(
        self,
        mock_exists,
        mock_ffmpeg_in_path,
        mock_db_class,
        mock_get_filtered_content,
        mock_get_rb_pid,
        mock_convert,
        mock_update_db,
        mock_logger,
        make_djmd_content_item,
        mock_db,
    ):
        """Exits with error when the database commit fails after successful conversion."""
        mock_get_rb_pid.return_value = None
        mock_ffmpeg_in_path.return_value = True
        mock_convert.return_value = True
        mock_update_db.return_value = None
        mock_db.session.commit.side_effect = Exception("Commit failed")
        mock_exists.side_effect = lambda path: (
            "song.flac" in path or (mock_convert.call_count > 0 and "song.aiff" in path)
        )
        mock_db_class.return_value = mock_db

        mock_result = Mock()
        mock_result.scalars().all.return_value = [
            make_djmd_content_item(
                FileType=5,
                ID="AAA",
                FileNameL="song.flac",
                FolderPath="/music/song.flac",
            )
        ]
        mock_get_filtered_content.return_value = mock_result

        from click.testing import CliRunner

        result = CliRunner().invoke(convert_command, ["--yes"])

        assert result.exit_code == 1
        mock_logger.error.assert_any_call("Commit failed: Commit failed")


class TestConvertStdinPiping:
    """Test convert command reading track IDs from stdin when piped."""

    @patch("rekordbox_edit.commands.convert.get_rekordbox_pid")
    @patch("rekordbox_edit.commands.convert.get_filtered_content")
    @patch("rekordbox_edit.commands.convert.Rekordbox6Database")
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    def test_reads_track_ids_from_stdin_when_piped(
        self,
        mock_ffmpeg_in_path,
        mock_db_class,
        mock_get_filtered_content,
        mock_get_rb_pid,
    ):
        """When stdin is piped with no args, those IDs are used as the filter."""
        mock_get_rb_pid.return_value = None
        mock_ffmpeg_in_path.return_value = True

        mock_db = Mock()
        mock_db_class.return_value = mock_db
        mock_db.session = Mock()

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []
        mock_get_filtered_content.return_value = mock_result

        from click.testing import CliRunner

        runner = CliRunner()
        runner.invoke(
            convert_command,
            ["--dry-run"],
            input="190993005 108916663 59476253",
        )

        call_kwargs = mock_get_filtered_content.call_args.kwargs
        assert call_kwargs["track_id_args"] == ["190993005", "108916663", "59476253"]

    @patch("rekordbox_edit.commands.convert.get_rekordbox_pid")
    @patch("rekordbox_edit.commands.convert.get_filtered_content")
    @patch("rekordbox_edit.commands.convert.Rekordbox6Database")
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    def test_merges_stdin_ids_with_argument_ids(
        self,
        mock_ffmpeg_in_path,
        mock_db_class,
        mock_get_filtered_content,
        mock_get_rb_pid,
    ):
        """When both TRACK_IDS args and piped stdin are provided, they are combined."""
        mock_get_rb_pid.return_value = None
        mock_ffmpeg_in_path.return_value = True

        mock_db = Mock()
        mock_db_class.return_value = mock_db
        mock_db.session = Mock()

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []
        mock_get_filtered_content.return_value = mock_result

        from click.testing import CliRunner

        runner = CliRunner()
        runner.invoke(
            convert_command,
            ["--dry-run", "190993005", "108916663"],
            input="59476253 113475696",
        )

        call_kwargs = mock_get_filtered_content.call_args.kwargs
        assert call_kwargs["track_id_args"] == [
            "190993005",
            "108916663",
            "59476253",
            "113475696",
        ]

    def test_piped_stdin_without_yes_or_dry_run_errors(self):
        """Piping track IDs without --yes or --dry-run raises a UsageError."""
        from click.testing import CliRunner

        result = CliRunner().invoke(convert_command, [], input="190993005 108916663")

        assert result.exit_code != 0
        assert "requires --dry-run or --yes" in result.output

    @patch("rekordbox_edit.commands.convert.get_rekordbox_pid")
    @patch("rekordbox_edit.commands.convert.get_filtered_content")
    @patch("rekordbox_edit.commands.convert.Rekordbox6Database")
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    def test_empty_stdin_does_not_affect_track_ids(
        self,
        mock_ffmpeg_in_path,
        mock_db_class,
        mock_get_filtered_content,
        mock_get_rb_pid,
    ):
        """Whitespace-only piped stdin is ignored."""
        mock_get_rb_pid.return_value = None
        mock_ffmpeg_in_path.return_value = True

        mock_db = Mock()
        mock_db_class.return_value = mock_db
        mock_db.session = Mock()

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []
        mock_get_filtered_content.return_value = mock_result

        from click.testing import CliRunner

        runner = CliRunner()
        runner.invoke(convert_command, ["--dry-run"], input="   ")

        call_kwargs = mock_get_filtered_content.call_args.kwargs
        assert not call_kwargs["track_id_args"]
