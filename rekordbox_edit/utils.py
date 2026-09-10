"""Shared utility functions for rekordbox-edit."""

import logging
import platform
import shutil
from dataclasses import dataclass
from enum import Enum
from typing import TypedDict

import ffmpeg

from rekordbox_edit.errors import DependencyMissingError, InputError

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FileTypeInfo:
    """One Rekordbox FileType code: how RBE names, filters, probes, and
    converts it. ``codecs`` are ffprobe codec_name prefixes and
    ``containers`` are format_name substrings; a probe must satisfy both
    (WAV and AIFF share PCM codecs, so their containers disambiguate).
    ``aliases`` are other names the format answers to, so a lookup keyed by
    another library's vocabulary still resolves. ``extensions`` are the
    suffixes RBE recognizes as this type, most canonical first; ``convertable``
    marks a valid conversion source, and OutputFormats names the valid
    targets."""

    code: int
    name: str
    token: str
    extensions: tuple[str, ...] = ()
    codecs: tuple[str, ...] = ()
    containers: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    convertable: bool = False


class FileTypeRegistry:
    def __init__(self, items: list[FileTypeInfo]) -> None:
        self._items: list[FileTypeInfo] = items
        self._by_code: dict[int, FileTypeInfo] = {i.code: i for i in items}
        self._by_name: dict[str, FileTypeInfo] = {i.name: i for i in items}
        self._by_token: dict[str, FileTypeInfo] = {i.token: i for i in items}
        self._by_alias: dict[str, FileTypeInfo] = {
            alias: i for i in items for alias in i.aliases
        }

    def get(self, key: int | str) -> FileTypeInfo | None:
        if isinstance(key, int):
            return self._by_code.get(key)
        return (
            self._by_name.get(key) or self._by_token.get(key) or self._by_alias.get(key)
        )

    def __getitem__(self, key: int | str) -> FileTypeInfo:
        result = self.get(key)
        if result is None:
            raise KeyError(f"FileTypeInfo not found for key: {key!r}")
        return result

    def items(self) -> list[FileTypeInfo]:
        return self._items


FILE_TYPES = FileTypeRegistry(
    [
        # Corrupt or empty content, independent of container.
        FileTypeInfo(code=0, name="INVALID", token="invalid"),
        FileTypeInfo(
            code=1, name="MP3", token="mp3", extensions=(".mp3",), codecs=("mp3",)
        ),
        # 3 is the .mp4 container regardless of content: audio-only AAC/ALAC
        # .mp4 files land here alongside video .mp4, so RBE never converts it.
        FileTypeInfo(code=3, name="MP4", token="mp4", extensions=(".mp4",)),
        FileTypeInfo(
            code=4,
            name="AAC",
            token="aac",
            extensions=(".aac", ".m4a"),
            codecs=("aac",),
        ),
        FileTypeInfo(
            code=5,
            name="FLAC",
            token="flac",
            extensions=(".flac",),
            codecs=("flac",),
            convertable=True,
        ),
        FileTypeInfo(
            code=6,
            name="ALAC",
            token="alac",
            extensions=(".m4a",),
            codecs=("alac",),
            convertable=True,
        ),
        FileTypeInfo(
            code=11,
            name="WAV",
            token="wav",
            extensions=(".wav",),
            codecs=("pcm_",),
            containers=("wav",),
            # The RIFF form type, and what mutagen calls the class.
            aliases=("WAVE",),
            convertable=True,
        ),
        FileTypeInfo(
            code=12,
            name="AIFF",
            token="aiff",
            extensions=(".aiff", ".aif"),
            codecs=("pcm_",),
            containers=("aiff",),
            convertable=True,
        ),
        # Catch-all for non-mp4 video containers (avi, m4v, mov, mpg). Its
        # extensions stay empty: the code is only ever read back from the
        # database, never inferred from a file RBE is asked to handle.
        FileTypeInfo(code=16, name="VIDEO", token="video"),
    ]
)


class OutputFormats(Enum):
    """The formats RBE can write. A FileTypeInfo carries extensions for every
    type RBE recognizes, including ones it only ever reads, so membership here
    is what gates an output format rather than the presence of an extension."""

    MP3 = "mp3"
    FLAC = "flac"
    AIFF = "aiff"
    WAV = "wav"


_OUTPUT_TOKENS = frozenset(f.value for f in OutputFormats)


def get_file_type_name(file_type_code: int | None) -> str | None:
    """Map a Rekordbox FileType code to a display name, or None if unmapped."""
    if file_type_code is None:
        return None
    info = FILE_TYPES.get(file_type_code)
    return info.name if info else None


def get_file_type_codes_for_format(format_name: str) -> set[int]:
    """All FileType codes a format token matches (case-insensitive).

    Tokens mirror FileType values one to one.
    """
    if not format_name:
        raise InputError("Format name cannot be empty or None")
    token = format_name.lower()
    codes = {info.code for info in FILE_TYPES.items() if token == info.token}
    if not codes:
        raise InputError(f"Unknown format: {format_name}")
    return codes


def get_file_type_for_format(format_name: str) -> int:
    """The FileType code Rekordbox records for files RBE writes in this
    output format (case-insensitive). Raises for non-output formats."""
    if not format_name:
        raise InputError("Format name cannot be empty or None")
    token = format_name.lower()
    if token not in _OUTPUT_TOKENS:
        raise InputError(f"Unknown format: {format_name}")
    return FILE_TYPES[token].code


def get_extension_for_format(format_name: str) -> str:
    """The extension RBE gives files it writes in this output format."""
    code = get_file_type_for_format(format_name)
    return FILE_TYPES[code].extensions[0]


def probe_matches_file_type(
    file_type_code: int | None, codec: str | None, container: str | None
) -> bool:
    """Whether a probed codec/container is consistent with a Rekordbox
    FileType code. Unknown codes never match, so callers treat them as
    mismatches instead of converting blind."""
    if file_type_code is None:
        return False
    info = FILE_TYPES.get(file_type_code)
    if info is None:
        return False
    if info.codecs and not (codec or "").startswith(info.codecs):
        return False
    if info.containers:
        if not container or not any(c in container for c in info.containers):
            return False
    return True


def get_file_type_for_probe(codec: str | None, container: str | None) -> int | None:
    """The Rekordbox FileType code for a probed codec/container, or None when
    no code matches. Only codes with declared codecs are candidates, so the
    catch-all codes (INVALID, MP4, VIDEO) are never inferred from a probe."""
    for info in FILE_TYPES.items():
        if info.codecs and probe_matches_file_type(info.code, codec, container):
            return info.code
    return None


def ffmpeg_in_path():
    """Check availability of ffmpeg program via which command"""
    return shutil.which("ffmpeg") is not None


def require_ffmpeg() -> None:
    """Raise DependencyMissingError unless ffmpeg is on PATH.

    The single presence check. Callers that probe or encode call this first so
    a missing install is reported as a missing install, rather than surfacing
    as whatever the failed probe happened to look like.
    """
    if ffmpeg_in_path():
        return
    raise DependencyMissingError(
        f"FFmpeg is required but not found in PATH.{get_ffmpeg_directions()}"
    )


def get_ffmpeg_directions():
    """How to install ffmpeg on this platform."""
    if platform.system() == "Windows":
        return """
Install it from https://ffmpeg.org/download.html
"""
    return """
Install it with `brew install ffmpeg`, or from https://ffmpeg.org/download.html
"""


class AudioInfo(TypedDict):
    """Fields extracted from an ffmpeg probe of one audio file."""

    bit_depth: int | None
    sample_rate: int
    channels: int
    bitrate: int | None
    codec: str | None
    container: str | None
    duration: float | None


def get_audio_info(file_path) -> AudioInfo:
    """Get audio information from file using ffmpeg probe.

    Returns None for any field that cannot be determined from the probe data.
    Callers are responsible for handling None values and applying
    format-specific assumptions (e.g. MP3 has no true bit depth). ``codec``
    is the stream's codec_name and ``container`` the probe's format_name.
    """
    require_ffmpeg()
    try:
        probe = ffmpeg.probe(file_path)
        audio_stream = next(
            (stream for stream in probe["streams"] if stream["codec_type"] == "audio"),
            None,
        )
        if not audio_stream:
            raise Exception(f"No audio stream found in {file_path}")

        # Try multiple ways to get bit depth
        bit_depth = None

        # Method 1: bits_per_sample
        if "bits_per_sample" in audio_stream and audio_stream["bits_per_sample"] != 0:
            bit_depth = int(audio_stream["bits_per_sample"])
        # Method 2: bits_per_raw_sample
        elif (
            "bits_per_raw_sample" in audio_stream
            and audio_stream["bits_per_raw_sample"] != 0
        ):
            bit_depth = int(audio_stream["bits_per_raw_sample"])
        # Method 3: parse from sample_fmt (e.g., "s16", "s24", "s32")
        elif "sample_fmt" in audio_stream:
            sample_fmt = audio_stream["sample_fmt"]
            if "16" in sample_fmt:
                bit_depth = 16
            elif "24" in sample_fmt:
                bit_depth = 24
            elif "32" in sample_fmt:
                bit_depth = 32

        if bit_depth is None:
            _logger.debug(f"Could not determine bit depth for {file_path}")

        # Get bitrate from stream, or calculate from audio properties if available
        bitrate = None
        if "bit_rate" in audio_stream and audio_stream["bit_rate"]:
            bitrate = int(audio_stream["bit_rate"]) // 1000  # Convert to kbps
        elif bit_depth is not None:
            _logger.debug(
                "Calculating bit rate from sample_rate * bit_depth * channels"
            )
            sample_rate = int(audio_stream.get("sample_rate", 0))
            channels = int(audio_stream.get("channels", 1))
            if sample_rate > 0:
                bitrate = (sample_rate * bit_depth * channels) // 1000

        if bitrate is None:
            _logger.debug(f"Could not determine bitrate for {file_path}")

        duration = None
        raw_duration = probe.get("format", {}).get("duration") or audio_stream.get(
            "duration"
        )
        if raw_duration is not None:
            duration = float(raw_duration)
        else:
            _logger.debug(f"Could not determine duration for {file_path}")

        return {
            "bit_depth": bit_depth,
            "sample_rate": int(audio_stream.get("sample_rate", 44100)),
            "channels": int(audio_stream.get("channels", 2)),
            "bitrate": bitrate,
            "codec": audio_stream.get("codec_name"),
            "container": probe.get("format", {}).get("format_name"),
            "duration": duration,
        }
    except Exception as e:
        _logger.error(f"Failed to get audio info for {file_path}: {e}")
        _logger.debug("Full traceback:", exc_info=True)
        raise e


#: DjmdContent.Rating holds the star count itself, 0-5. rekordbox's XML export
#: encodes the same rating as 0/51/102/153/204/255, which is a property of that
#: file format and not of this column.
_RATING_STARS_MAX = 5


def parse_star_rating(value: "str | int") -> int:
    """Parse a 0-5 star rating. Raise InputError if not an integer in range."""
    try:
        stars = int(value)
    except (TypeError, ValueError):
        raise InputError(
            f"Rating must be an integer 0-{_RATING_STARS_MAX}, got {value!r}"
        )
    if not 0 <= stars <= _RATING_STARS_MAX:
        raise InputError(
            f"Rating must be between 0 and {_RATING_STARS_MAX}, got {stars}"
        )
    return stars
