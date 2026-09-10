import shutil
from pathlib import Path

import pytest
from mutagen.flac import FLAC
from mutagen.id3 import COMM, TCOM, TCON, TDRC, TKEY, TPOS, TPUB, TRCK, TSRC
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4FreeForm

from rekordbox_edit.tags import UnreadableFile, _first, read_tags

FIXTURES = Path(__file__).resolve().parent / "e2e/fixtures/audio"


def _copy(tmp_path: Path, name: str) -> str:
    """A writable copy of a committed fixture, since the originals are
    read-only and shared across the test session."""
    dst = tmp_path / name
    shutil.copy(FIXTURES / name, dst)
    return str(dst)


class TestFileType:
    """FileType comes from the detected codec, never the extension: both .m4a
    fixtures share a suffix but differ in Rekordbox FileType."""

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("01-flac-44_1k-16b.flac", 5),
            ("05-aiff-44_1k-16b.aiff", 12),
            ("06-wav-96k-24b.wav", 11),
            ("07-mp3-44_1k-320cbr.mp3", 1),
            ("03-alac-44_1k-16b.m4a", 6),
            ("09-aac-44_1k-256kbps.m4a", 4),
        ],
    )
    def test_maps_codec_to_rekordbox_file_type(self, name, expected):
        assert read_tags(str(FIXTURES / name))["file_type"] == expected


class TestScalarTags:
    def test_reads_vorbis_tags(self):
        tags = read_tags(str(FIXTURES / "01-flac-44_1k-16b.flac"))
        assert tags["title"] == "Wave Alpha"
        assert tags["artist"] == "Alpha"
        assert tags["album"] == "Lossless Vol 1"

    def test_falls_back_to_filename_stem_when_untagged(self):
        # The AIFF fixture carries no tags at all.
        tags = read_tags(str(FIXTURES / "05-aiff-44_1k-16b.aiff"))
        assert tags["title"] == "05-aiff-44_1k-16b"
        assert tags["artist"] is None

    @pytest.mark.parametrize(
        "name,sample_rate,bit_depth,bitrate",
        [
            ("01-flac-44_1k-16b.flac", 44100, 16, 96),
            ("05-aiff-44_1k-16b.aiff", 44100, 16, 705),
            ("06-wav-96k-24b.wav", 96000, 24, 2304),
            # MP3 carries no bit depth; the import conventions supply one.
            ("07-mp3-44_1k-320cbr.mp3", 44100, None, 320),
            # ALAC reports the PCM-equivalent rate, which is what Rekordbox
            # stores. An ffmpeg probe reports the compressed rate instead.
            ("03-alac-44_1k-16b.m4a", 44100, 16, 705),
            ("09-aac-44_1k-256kbps.m4a", 44100, 16, 132),
        ],
    )
    def test_reads_the_stream_header_numbers(
        self, name, sample_rate, bit_depth, bitrate
    ):
        tags = read_tags(str(FIXTURES / name))

        assert tags["sample_rate"] == sample_rate
        assert tags["bit_depth"] == bit_depth
        assert tags["bitrate"] == bitrate

    def test_reads_length_as_whole_seconds(self):
        assert read_tags(str(FIXTURES / "01-flac-44_1k-16b.flac"))["length"] == 2


class TestUnreadable:
    def test_raises_for_a_non_audio_file(self, tmp_path):
        junk = tmp_path / "notes.txt"
        junk.write_text("not audio")
        with pytest.raises(UnreadableFile):
            read_tags(str(junk))

    def test_raises_for_a_missing_file(self, tmp_path):
        with pytest.raises(UnreadableFile):
            read_tags(str(tmp_path / "absent.flac"))


class TestMP4Tags:
    """The .m4a fixtures carry no genre/composer/isrc/initialkey tags, so
    these write tags onto a writable copy before reading them back."""

    def test_reads_isrc_from_the_xid_atom_stripping_the_vendor_prefix(self, tmp_path):
        path = _copy(tmp_path, "09-aac-44_1k-256kbps.m4a")
        audio = MP4(path)
        audio["xid "] = ["Universal:isrc:USQY51374467"]
        audio.save()

        assert read_tags(path)["isrc"] == "USQY51374467"

    def test_ignores_the_freeform_initialkey_atom(self, tmp_path):
        """Rekordbox itself ignores this atom, verified on 21 of 21 sampled
        files. A future refactor that "helpfully" reads it must fail here."""
        path = _copy(tmp_path, "09-aac-44_1k-256kbps.m4a")
        audio = MP4(path)
        audio["----:com.apple.iTunes:initialkey"] = [MP4FreeForm(b"Dm")]
        audio.save()

        assert read_tags(path)["key"] is None


class TestReleaseYear:
    """release_year keeps only the leading year out of a full YYYY-MM-DD
    date, on every format that stores one."""

    def test_from_a_vorbis_date_tag(self, tmp_path):
        path = _copy(tmp_path, "01-flac-44_1k-16b.flac")
        audio = FLAC(path)
        audio["date"] = ["2022-07-26"]
        audio.save()

        assert read_tags(path)["release_year"] == 2022

    def test_from_an_id3_tdrc_frame(self, tmp_path):
        path = _copy(tmp_path, "07-mp3-44_1k-320cbr.mp3")
        audio = MP3(path)
        assert audio.tags is not None
        audio.tags.add(TDRC(encoding=3, text=["2022-07-26"]))
        audio.save()

        assert read_tags(path)["release_year"] == 2022


class TestVorbisTags:
    """Genre through disc_no: none of these appear on the committed fixtures,
    so this writes them onto a FLAC copy first."""

    def test_reads_the_full_set_of_vorbis_fields(self, tmp_path):
        path = _copy(tmp_path, "01-flac-44_1k-16b.flac")
        audio = FLAC(path)
        audio["genre"] = ["Techno"]
        audio["composer"] = ["Some Composer"]
        audio["label"] = ["Some Label"]
        audio["isrc"] = ["USRC17607839"]
        audio["initialkey"] = ["Fm"]
        audio["comment"] = ["a nice track"]
        audio["tracknumber"] = ["3/12"]
        audio["discnumber"] = ["1"]
        audio.save()

        tags = read_tags(path)
        assert tags["genre"] == "Techno"
        assert tags["composer"] == "Some Composer"
        assert tags["label"] == "Some Label"
        assert tags["isrc"] == "USRC17607839"
        assert tags["key"] == "Fm"
        assert tags["comment"] == "a nice track"
        assert tags["track_no"] == 3
        assert tags["disc_no"] == 1


class TestID3Tags:
    """genre through disc_no plus comment: none of these appear on the
    committed fixtures, so this writes ID3 frames onto an MP3 copy first."""

    def test_reads_the_full_set_of_id3_fields(self, tmp_path):
        path = _copy(tmp_path, "07-mp3-44_1k-320cbr.mp3")

        audio = MP3(path)
        assert audio.tags is not None
        audio.tags.add(TCON(encoding=3, text=["Techno"]))
        audio.tags.add(TCOM(encoding=3, text=["Some Composer"]))
        audio.tags.add(TPUB(encoding=3, text=["Some Label"]))
        audio.tags.add(TSRC(encoding=3, text=["USRC17607839"]))
        audio.tags.add(TKEY(encoding=3, text=["Fm"]))
        audio.tags.add(TRCK(encoding=3, text=["3/12"]))
        audio.tags.add(TPOS(encoding=3, text=["1"]))
        audio.tags.add(COMM(encoding=3, lang="eng", desc="", text=["a nice track"]))
        audio.save()

        tags = read_tags(path)
        assert tags["genre"] == "Techno"
        assert tags["composer"] == "Some Composer"
        assert tags["label"] == "Some Label"
        assert tags["isrc"] == "USRC17607839"
        assert tags["key"] == "Fm"
        assert tags["comment"] == "a nice track"
        assert tags["track_no"] == 3
        assert tags["disc_no"] == 1

    def test_falls_back_to_a_comment_frame_under_a_different_description(
        self, tmp_path
    ):
        """mutagen keys COMM frames as "COMM:<description>:<language>"; a
        comment stored under a non-empty description (e.g. "ID3v1 Comment",
        as seen in the sampled library) must still be found."""
        path = _copy(tmp_path, "07-mp3-44_1k-320cbr.mp3")

        audio = MP3(path)
        assert audio.tags is not None
        audio.tags.add(
            COMM(encoding=3, lang="eng", desc="ID3v1 Comment", text=["legacy note"])
        )
        audio.save()

        assert read_tags(path)["comment"] == "legacy note"

    def test_takes_the_first_value_of_a_multi_value_text_frame(self, tmp_path):
        """A text frame may legally carry multiple values (e.g. two genres
        in one TCON). Stringifying the whole frame joins them with a NUL
        byte; read_tags must take only the first value instead."""
        path = _copy(tmp_path, "07-mp3-44_1k-320cbr.mp3")

        audio = MP3(path)
        assert audio.tags is not None
        audio.tags.add(TCON(encoding=3, text=["Trance", "Progressive House"]))
        audio.save()

        assert read_tags(path)["genre"] == "Trance"


class TestFirst:
    """Value shapes mutagen returns that the fixture files do not produce."""

    def test_unwraps_an_mp4_number_total_tuple(self):
        # MP4 stores trkn and disk as [(number, total)]; Rekordbox keeps the
        # number.
        assert _first({"trkn": [(3, 12)]}, ("trkn",)) == "3"

    def test_decodes_a_bytes_value(self):
        # MP4 freeform atoms hold raw bytes rather than text.
        assert _first({"isrc": [b"USRC17607839"]}, ("isrc",)) == "USRC17607839"

    def test_replaces_undecodable_bytes_rather_than_raising(self):
        assert _first({"title": [b"caf\xe9"]}, ("title",)) == "caf\ufffd"

    def test_accepts_a_bare_scalar_value(self):
        assert _first({"title": 1994}, ("title",)) == "1994"

    def test_skips_an_empty_value_and_takes_the_next_key(self):
        assert (
            _first(
                {"label": ["  "], "organization": ["Warp"]}, ("label", "organization")
            )
            == "Warp"
        )

    def test_returns_none_when_every_key_is_empty(self):
        assert _first({"label": [""]}, ("label", "organization")) is None
