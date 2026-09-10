"""Unit tests for utils module functionality."""

from unittest.mock import patch

import pytest

from rekordbox_edit.utils import (
    FILE_TYPES,
    get_audio_info,
    get_extension_for_format,
    get_file_type_codes_for_format,
    get_file_type_for_format,
    get_file_type_name,
    parse_star_rating,
    get_file_type_for_probe,
    probe_matches_file_type,
)


class TestFileTypeRegistry:
    def test_resolves_a_code_name_or_token(self):
        wav = FILE_TYPES[11]
        assert FILE_TYPES.get("WAV") is wav
        assert FILE_TYPES.get("wav") is wav

    def test_resolves_an_alias(self):
        # mutagen calls the class WAVE; the registry is what reconciles that
        # with the "WAV" this project displays.
        assert FILE_TYPES.get("WAVE") is FILE_TYPES[11]

    def test_unknown_key_returns_none(self):
        assert FILE_TYPES.get("OGG") is None

    def test_subscript_raises_for_an_unknown_key(self):
        with pytest.raises(KeyError, match="OGG"):
            FILE_TYPES["OGG"]


class TestGetFileTypeName:
    """Test file type name mapping."""

    def test_get_file_type_name_known_types(self):
        """Test get_file_type_name with known file type codes."""
        assert get_file_type_name(1) == "MP3"
        assert get_file_type_name(4) == "AAC"
        assert get_file_type_name(5) == "FLAC"
        assert get_file_type_name(6) == "ALAC"
        assert get_file_type_name(11) == "WAV"
        assert get_file_type_name(12) == "AIFF"

    def test_get_file_type_name_video_types(self):
        """Code 3 is the .mp4 container regardless of content; code 16
        covers every other video container (avi, m4v, mov, mpg)."""
        assert get_file_type_name(3) == "MP4"
        assert get_file_type_name(16) == "VIDEO"

    def test_get_file_type_name_invalid_type(self):
        """Code 0 means corrupt or empty content, independent of container."""
        assert get_file_type_name(0) == "INVALID"

    def test_get_file_type_name_unknown_types(self):
        """Unknown codes return None so callers pick their own fallback."""
        assert get_file_type_name(None) is None
        assert get_file_type_name(-1) is None
        assert get_file_type_name(99) is None


class TestGetFileTypeForFormat:
    def test_get_file_type_for_format_case_insensitive(self):
        """Output formats resolve to their unique code, case-insensitively."""
        assert get_file_type_for_format("MP3") == 1
        assert get_file_type_for_format("mp3") == 1
        assert get_file_type_for_format("Mp3") == 1
        assert get_file_type_for_format("FLAC") == 5
        assert get_file_type_for_format("flac") == 5
        assert get_file_type_for_format("wav") == 11
        assert get_file_type_for_format("AIFF") == 12

    def test_get_file_type_for_format_rejects_non_output_formats(self):
        """Tokens RBE cannot write as output are rejected."""
        with pytest.raises(ValueError, match="Unknown format"):
            get_file_type_for_format("aac")
        with pytest.raises(ValueError, match="Unknown format"):
            get_file_type_for_format("alac")
        with pytest.raises(ValueError, match="Unknown format"):
            get_file_type_for_format("mp4")
        with pytest.raises(ValueError, match="Unknown format"):
            get_file_type_for_format("video")
        with pytest.raises(ValueError, match="Unknown format"):
            get_file_type_for_format("invalid")

    def test_get_file_type_for_format_invalid(self):
        """Test get_file_type_for_format with invalid formats."""
        with pytest.raises(ValueError, match="Unknown format"):
            get_file_type_for_format("xyz")
        with pytest.raises(ValueError, match="cannot be empty"):
            get_file_type_for_format("")
        with pytest.raises(ValueError, match="cannot be empty"):
            get_file_type_for_format(None)  # ty: ignore[invalid-argument-type]


class TestGetFileTypeCodesForFormat:
    def test_single_code_tokens(self):
        assert get_file_type_codes_for_format("mp3") == {1}
        assert get_file_type_codes_for_format("flac") == {5}
        assert get_file_type_codes_for_format("WAV") == {11}
        assert get_file_type_codes_for_format("aiff") == {12}
        assert get_file_type_codes_for_format("aac") == {4}
        assert get_file_type_codes_for_format("alac") == {6}
        assert get_file_type_codes_for_format("mp4") == {3}
        assert get_file_type_codes_for_format("video") == {16}
        assert get_file_type_codes_for_format("invalid") == {0}

    def test_m4a_is_not_a_token(self):
        """Tokens mirror FileType values; the extension-level m4a token was
        removed, so callers filter AAC/ALAC directly or search by path."""
        with pytest.raises(ValueError, match="Unknown format"):
            get_file_type_codes_for_format("m4a")

    def test_invalid_raises(self):
        with pytest.raises(ValueError, match="Unknown format"):
            get_file_type_codes_for_format("xyz")
        with pytest.raises(ValueError, match="cannot be empty"):
            get_file_type_codes_for_format("")


class TestGetExtensionForFormat:
    def test_get_extension_for_format_case_insensitive(self):
        """Test get_extension_for_format is case-insensitive."""
        assert get_extension_for_format("MP3") == ".mp3"
        assert get_extension_for_format("mp3") == ".mp3"
        assert get_extension_for_format("FLAC") == ".flac"
        assert get_extension_for_format("WAV") == ".wav"
        assert get_extension_for_format("aiff") == ".aiff"

    def test_get_extension_for_format_invalid(self):
        """Test get_extension_for_format with invalid formats."""
        with pytest.raises(ValueError, match="Unknown format"):
            get_extension_for_format("xyz")
        with pytest.raises(ValueError, match="cannot be empty"):
            get_extension_for_format("")
        with pytest.raises(ValueError, match="cannot be empty"):
            get_extension_for_format(None)  # ty: ignore[invalid-argument-type]


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
    def test_get_audio_info__duration_from_format(self, mock_probe, ffmpeg_exists):
        """Duration comes from the probe's format section."""
        mock_probe.return_value = {
            "streams": [
                {
                    "codec_type": "audio",
                    "bits_per_sample": 16,
                    "sample_rate": "44100",
                    "channels": 2,
                }
            ],
            "format": {"format_name": "wav", "duration": "214.398"},
        }

        result = get_audio_info("/path/to/audio.wav")

        assert result["duration"] == pytest.approx(214.398)

    @patch("rekordbox_edit.utils.ffmpeg.probe")
    def test_get_audio_info__duration_falls_back_to_stream(
        self, mock_probe, ffmpeg_exists
    ):
        """Stream duration is used when the format section has none."""
        mock_probe.return_value = {
            "streams": [
                {
                    "codec_type": "audio",
                    "bits_per_sample": 16,
                    "sample_rate": "44100",
                    "channels": 2,
                    "duration": "183.02",
                }
            ],
            "format": {"format_name": "flac"},
        }

        result = get_audio_info("/path/to/audio.flac")

        assert result["duration"] == pytest.approx(183.02)

    @patch("rekordbox_edit.utils.ffmpeg.probe")
    def test_get_audio_info__duration_missing_is_none(self, mock_probe, ffmpeg_exists):
        mock_probe.return_value = {
            "streams": [
                {
                    "codec_type": "audio",
                    "bits_per_sample": 16,
                    "sample_rate": "44100",
                    "channels": 2,
                }
            ]
        }

        result = get_audio_info("/path/to/audio.wav")

        assert result["duration"] is None

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

    @patch("rekordbox_edit.utils.ffmpeg.probe")
    def test_get_audio_info__codec_and_container(self, mock_probe, ffmpeg_exists):
        """The probe's codec_name and format_name pass through."""
        mock_probe.return_value = {
            "streams": [
                {
                    "codec_type": "audio",
                    "codec_name": "alac",
                    "bits_per_sample": 16,
                    "sample_rate": "44100",
                    "channels": 2,
                }
            ],
            "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2"},
        }

        result = get_audio_info("/path/to/audio.m4a")

        assert result["codec"] == "alac"
        assert result["container"] == "mov,mp4,m4a,3gp,3g2,mj2"

    @patch("rekordbox_edit.utils.ffmpeg.probe")
    def test_get_audio_info__missing_codec_fields_are_none(
        self, mock_probe, ffmpeg_exists
    ):
        """Probes without codec_name or a format section yield None fields."""
        mock_probe.return_value = {
            "streams": [
                {
                    "codec_type": "audio",
                    "bits_per_sample": 16,
                    "sample_rate": "44100",
                    "channels": 2,
                }
            ]
        }

        result = get_audio_info("/path/to/audio.wav")

        assert result["codec"] is None
        assert result["container"] is None


class TestProbeMatchesFileType:
    @pytest.mark.parametrize(
        "code,codec,container,expected",
        [
            (5, "flac", "flac", True),
            (6, "alac", "mov,mp4,m4a,3gp,3g2,mj2", True),
            (6, "aac", "mov,mp4,m4a,3gp,3g2,mj2", False),  # lossy posing as ALAC
            (4, "aac", "mov,mp4,m4a,3gp,3g2,mj2", True),
            (11, "pcm_s16le", "wav", True),
            (11, "pcm_s24le", "wav", True),
            (11, "flac", "wav", False),
            (11, "pcm_s16le", "aiff", False),  # container disambiguates PCM
            (12, "pcm_s16be", "aiff", True),
            (12, "pcm_s16le", "wav", False),
            (1, "mp3", "mp3", True),
            (1, "flac", "flac", False),
            (99, "flac", "flac", False),  # unknown codes never match
            (None, "flac", "flac", False),
            (5, None, None, False),
        ],
    )
    def test_matching(self, code, codec, container, expected):
        assert probe_matches_file_type(code, codec, container) is expected


class TestGetFileTypeForProbe:
    @pytest.mark.parametrize(
        "codec,container,expected",
        [
            ("flac", "flac", 5),
            ("alac", "mov,mp4,m4a,3gp,3g2,mj2", 6),
            ("aac", "mov,mp4,m4a,3gp,3g2,mj2", 4),
            ("pcm_s16le", "wav", 11),
            ("pcm_s16be", "aiff", 12),
            ("mp3", "mp3", 1),
            ("vorbis", "ogg", None),  # no Rekordbox FileType for this codec
            (None, None, None),
        ],
    )
    def test_mapping(self, codec, container, expected):
        assert get_file_type_for_probe(codec, container) == expected


@pytest.mark.parametrize("value,expected", [("0", 0), ("5", 5), (3, 3)])
def test_parse_star_rating_valid(value, expected):
    assert parse_star_rating(value) == expected


@pytest.mark.parametrize("value", ["6", "-1", "abc", "3.5"])
def test_parse_star_rating_invalid(value):
    with pytest.raises(ValueError):
        parse_star_rating(value)
