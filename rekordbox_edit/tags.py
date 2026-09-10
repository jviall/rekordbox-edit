"""Read the tags Rekordbox reads when it imports a track.

The only module that imports mutagen. The per-format key tables mirror what
Rekordbox itself reads, derived in research/import-track-row-shape/: notably it
ignores the MP4 freeform key atom, and wraps MP4 ISRC inside the `xid ` atom.
"""

import logging
import os
from typing import TypedDict

import mutagen

from rekordbox_edit.utils import FILE_TYPES
from rekordbox_edit.errors import RekordboxEditError


_logger = logging.getLogger(__name__)


class UnreadableFile(RekordboxEditError):
    """Raised when a path is not audio mutagen can parse."""


class TrackTags(TypedDict):
    title: str | None
    artist: str | None
    album: str | None
    genre: str | None
    composer: str | None
    label: str | None
    isrc: str | None
    key: str | None
    comment: str | None
    track_no: int | None
    disc_no: int | None
    release_year: int | None
    length: int | None
    file_type: int | None
    sample_rate: int | None
    bit_depth: int | None
    bitrate: int | None


# Rekordbox FileType by mutagen's file class. MP4 splits on the codec because
# .m4a holds either ALAC or AAC and the extension cannot tell them apart.
_MP4_ALAC, _MP4_AAC = 6, 4

# Per-format tag keys, in priority order. Vorbis covers FLAC; ID3 covers MP3
# and the AIFF/WAV containers, whose mutagen tags are ID3 frames.
_VORBIS_KEYS: dict[str, tuple[str, ...]] = {
    "title": ("title",),
    "artist": ("artist",),
    "album": ("album",),
    "genre": ("genre",),
    "composer": ("composer",),
    "label": ("label", "organization"),
    "isrc": ("isrc",),
    "key": ("initialkey",),
    "comment": ("comment", "description"),
    "track_no": ("tracknumber",),
    "disc_no": ("discnumber",),
    "release_year": ("date", "originaldate"),
}
_ID3_KEYS: dict[str, tuple[str, ...]] = {
    "title": ("TIT2",),
    "artist": ("TPE1",),
    "album": ("TALB",),
    "genre": ("TCON",),
    "composer": ("TCOM",),
    "label": ("TPUB",),
    "isrc": ("TSRC",),
    "key": ("TKEY",),
    "comment": ("COMM::eng", "COMM"),
    "track_no": ("TRCK",),
    "disc_no": ("TPOS",),
    "release_year": ("TDRC", "TYER"),
}
# MP4 omits `key`: Rekordbox ignores the freeform initialkey atom, verified on
# 21 of 21 sampled files. `isrc` is handled separately, out of the `xid ` atom.
_MP4_KEYS: dict[str, tuple[str, ...]] = {
    "title": ("\xa9nam",),
    "artist": ("\xa9ART",),
    "album": ("\xa9alb",),
    "genre": ("\xa9gen",),
    "composer": ("\xa9wrt",),
    "comment": ("\xa9cmt",),
    "track_no": ("trkn",),
    "disc_no": ("disk",),
    "release_year": ("\xa9day",),
}


def _first(tags, keys) -> str | None:
    """The first non-empty value among `keys`, as a string.

    A literal "COMM" key is a fallback marker: mutagen keys ID3 comment
    frames as "COMM:<description>:<language>", and the description varies
    across taggers, so an exact "COMM" lookup never matches. Instead it
    triggers a scan for any tag key starting with "COMM:".
    """
    for key in keys:
        if key == "COMM":
            raw = next((tags[k] for k in tags.keys() if k.startswith("COMM:")), None)
            if raw is None:
                continue
        else:
            try:
                raw = tags[key]
            except (KeyError, TypeError):
                continue
        if isinstance(raw, list) and raw:
            value = raw[0]
        elif hasattr(raw, "text"):  # ID3 frame; .text holds its value(s)
            value = raw.text[0] if raw.text else ""
        else:
            value = raw
        if isinstance(value, tuple):  # MP4 trkn/disk are (number, total)
            value = value[0]
        if isinstance(value, (bytes, bytearray)):
            value = bytes(value).decode("utf-8", "replace")
        text = str(value).strip()
        if text:
            return text
    return None


def _leading_int(value: str | None) -> int | None:
    """The leading integer in a tag value. Handles '3/12' track numbers and
    'YYYY-MM-DD' dates, from which Rekordbox keeps only the year."""
    if not value:
        return None
    digits = ""
    for char in value.strip():
        if not char.isdigit():
            break
        digits += char
    return int(digits) if digits else None


def _mp4_isrc(tags) -> str | None:
    """The ISRC inside MP4's `xid ` atom, formatted `<vendor>:isrc:<value>`."""
    raw = _first(tags, ("xid ",))
    if raw and ":isrc:" in raw:
        return raw.split(":isrc:", 1)[1].strip() or None
    return None


def _file_type(audio) -> int | None:
    """The Rekordbox FileType code for a mutagen file object.

    mutagen names its classes after the format, so they resolve against
    FILE_TYPES directly (WAVE via that entry's alias). MP4 is the exception:
    one class covers both AAC and ALAC, which only the codec separates.
    """
    name: str = type(audio).__name__
    if name == "MP4":
        codec = getattr(audio.info, "codec", "") or ""
        return _MP4_ALAC if codec.startswith("alac") else _MP4_AAC
    file_type = FILE_TYPES.get(name)
    return file_type.code if file_type else None


def _kbps(bitrate: int | None) -> int | None:
    """A stream header's bits per second in the whole kilobits rekordbox stores."""
    return bitrate // 1000 if bitrate else None


def read_tags(path: str) -> TrackTags:
    """Read one file's tags and stream header.

    Raises UnreadableFile when the path is missing or is not audio mutagen
    can parse.
    """
    try:
        audio = mutagen.File(path)
    except Exception as e:
        raise UnreadableFile(f"Could not read {path}: {e}") from e
    if audio is None:
        raise UnreadableFile(f"Not a recognized audio file: {path}")

    name = type(audio).__name__
    keys: dict[str, tuple[str, ...]]
    if name == "MP4":
        keys = _MP4_KEYS
    elif name == "FLAC":
        keys = _VORBIS_KEYS
    else:
        keys = _ID3_KEYS

    tags = audio.tags or {}
    read = {field: _first(tags, tag_keys) for field, tag_keys in keys.items()}

    isrc = _mp4_isrc(tags) if name == "MP4" else read.get("isrc")
    info = audio.info
    length = getattr(info, "length", None)

    result: TrackTags = {
        "title": read.get("title") or os.path.splitext(os.path.basename(path))[0],
        "artist": read.get("artist"),
        "album": read.get("album"),
        "genre": read.get("genre"),
        "composer": read.get("composer"),
        "label": read.get("label"),
        "isrc": isrc,
        "key": read.get("key"),
        "comment": read.get("comment"),
        "track_no": _leading_int(read.get("track_no")),
        "disc_no": _leading_int(read.get("disc_no")),
        "release_year": _leading_int(read.get("release_year")),
        "length": int(length) if length is not None else None,
        "file_type": _file_type(audio),
        "sample_rate": getattr(info, "sample_rate", None),
        # MP3 and some MP4 headers report no depth; the caller supplies one.
        "bit_depth": getattr(info, "bits_per_sample", None) or None,
        "bitrate": _kbps(getattr(info, "bitrate", None)),
    }
    _logger.debug(f"read tags for {path}: file_type={result['file_type']}")
    return result
