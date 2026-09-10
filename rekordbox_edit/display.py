"""Rich-based rendering for rekordbox-edit.

All rich Console output should go through the module-level ``console`` and be
drained to the debug log immediately after printing:

    console.print(...)
    _logger.debug(console.export_text(clear=True))

Plain text output should continue to use ``_logger.info()``.
"""

import logging
import os
import re
from enum import Enum
from typing import Dict, Sequence

from rich import box
from rich.console import Console
from rich.highlighter import RegexHighlighter
from rich.table import Table
from rich.theme import Theme

from rekordbox_edit.models import Track
from rekordbox_edit.utils import FILE_TYPES, get_file_type_name

_logger = logging.getLogger(__name__)

#: Verbs that open a status line, e.g. "[1/49] converted foo.aiff" or
#: "Skipping 1 file(s): ...".
_ACTION_WORDS = (
    "converted",
    "skipping",
    "skipped",
    "deleted",
    "added",
    "applied",
    "kept",
    "cancelled",
    "placed",
)


def _format_words() -> tuple[str, ...]:
    """Every name/token/extension/alias the FileType registry answers to,
    so a format called out by any of its spellings ("FLAC", "flac",
    ".flac").

    Sorted longest-first so a shorter word (e.g. "AAC") can't shadow a
    longer one that starts with it in the alternation.
    """
    words: set[str] = set()
    for info in FILE_TYPES.items():
        words.add(info.name)
        words.add(info.token)
        words.update(ext.lstrip(".") for ext in info.extensions)
        words.update(info.aliases)
    return tuple(sorted(words, key=len, reverse=True))


#: Recognized output/target formats, called out separately from generic
#: filenames because they read as a choice ("to FLAC") rather than a path.
_FORMAT_WORDS = _format_words()


class RbeHighlighter(RegexHighlighter):
    """Highlights the things worth scanning for in rekordbox-edit's own
    console output: actions taken, files touched, CLI options, and progress
    counters. Replaces rich's default `ReprHighlighter`, which paints any
    number or path-shaped token regardless of what it means here.
    """

    base_style = "rbe."
    highlights = [
        # Anchor action words to the start of the line (or, since a message
        # can open with its own "\n", right after an embedded newline too),
        # or right after a "[n/m] " progress counter, so a track literally
        # named "Converted Soul.aiff" is never mistaken for the word.
        rf"(?:^|(?<=\n)|(?<=\]\s))(?P<action>(?i:{'|'.join(_ACTION_WORDS)}))\b",
        rf"(?P<path>(?:[\w.,()'&+-]+/)*[\w.,()'&+-]+\.(?:{'|'.join(ext for info in FILE_TYPES.items() for ext in info.extensions)}))\b",
        r"(?P<path>/(?:[^\s:]+/)+[^\s:]*)",
        r"(?P<option>--[a-zA-Z][\w-]*)",
        rf"\b(?P<option>(?i:{'|'.join(re.escape(w) for w in _FORMAT_WORDS)}))\b",
        r"(?P<count>\[\d+/\d+\])",
    ]


RBE_THEME = Theme(
    {
        "rbe.action": "bold cyan",
        "rbe.path": "green",
        "rbe.option": "magenta",
        "rbe.count": "dim",
        "logging.level.warning": "yellow",
        "logging.level.error": "red",
        "logging.level.critical": "bold red",
    }
)

console = Console(record=True, theme=RBE_THEME, highlighter=RbeHighlighter())


class PrintableField(Enum):
    """Track fields that can be printed in a table"""

    ID = "ID"
    FileNameL = "FileNameL"
    FolderPath = "FolderPath"
    FileType = "FileType"
    SampleRate = "SampleRate"
    BitDepth = "BitDepth"
    BitRate = "BitRate"
    ArtistName = "ArtistName"
    AlbumName = "AlbumName"
    Title = "Title"
    Comment = "Commnt"
    Rating = "Rating"
    Genre = "GenreName"
    Label = "LabelName"
    ComposerName = "ComposerName"
    ISRC = "ISRC"
    TrackNo = "TrackNo"
    DiscNo = "DiscNo"
    ReleaseYear = "ReleaseYear"


# Column headers shown in the rendered table
PRINT_HEADERS: Dict[PrintableField, str] = {
    PrintableField.ID: "ID",
    PrintableField.FileNameL: "File",
    PrintableField.Title: "Title",
    PrintableField.ArtistName: "Artist",
    PrintableField.AlbumName: "Album",
    PrintableField.FileType: "Type",
    PrintableField.SampleRate: "SampleRt",
    PrintableField.BitRate: "BitRt",
    PrintableField.BitDepth: "BitDp",
    PrintableField.FolderPath: "Folder",
    PrintableField.Comment: "Comment",
    PrintableField.Rating: "Rating",
    PrintableField.Genre: "Genre",
    PrintableField.Label: "Label",
    PrintableField.ComposerName: "Composer",
    PrintableField.ISRC: "ISRC",
    PrintableField.TrackNo: "Track",
    PrintableField.DiscNo: "Disc",
    PrintableField.ReleaseYear: "Year",
}

# Per-column add_column kwargs. min_width guarantees a column is never collapsed
# to nothing; ratio distributes remaining terminal width among wide text columns.
_COLUMN_CONFIG: Dict[PrintableField, dict] = {
    PrintableField.ID: {"justify": "right", "min_width": 4, "style": "dim"},
    PrintableField.Title: {"min_width": 5, "ratio": 1},
    PrintableField.ArtistName: {"min_width": 5, "ratio": 1},
    PrintableField.AlbumName: {"min_width": 5, "ratio": 1},
    PrintableField.FileType: {"min_width": 4, "style": "rbe.option"},
    PrintableField.SampleRate: {"min_width": 6},
    PrintableField.BitRate: {"min_width": 5},
    PrintableField.BitDepth: {"min_width": 4},
    PrintableField.FolderPath: {"min_width": 5, "ratio": 1, "style": "rbe.path"},
    PrintableField.FileNameL: {"min_width": 5, "ratio": 1, "style": "rbe.path"},
    PrintableField.Comment: {"min_width": 5, "ratio": 1},
    PrintableField.Rating: {"justify": "right", "min_width": 3, "style": "dim"},
    PrintableField.Genre: {"min_width": 5, "ratio": 1},
    PrintableField.Label: {"min_width": 5, "ratio": 1},
    PrintableField.ComposerName: {"min_width": 5, "ratio": 1},
    PrintableField.ISRC: {"min_width": 12},
    PrintableField.TrackNo: {"justify": "right", "min_width": 3, "style": "dim"},
    PrintableField.DiscNo: {"justify": "right", "min_width": 3, "style": "dim"},
    PrintableField.ReleaseYear: {"justify": "right", "min_width": 4, "style": "dim"},
}


def _cell_value(track: Track, column: PrintableField) -> str:
    """Render a single Track field as a string for a table cell."""
    if column is PrintableField.ID:
        return str(track.ID)
    if column is PrintableField.FileType:
        if track.FileType is None:
            return ""
        name = get_file_type_name(track.FileType)
        if name is None:
            _logger.warning(
                f"Unexpected FileType [{track.FileType}] for track ID [{track.ID}]"
            )
            return "UNKNOWN"
        return name
    if column is PrintableField.FolderPath:
        return os.path.dirname(track.FolderPath or "")
    if column is PrintableField.Rating:
        return "" if track.Rating is None else str(track.Rating)
    value = getattr(track, column.value, None)
    return "" if value is None else str(value)


def print_track_info(
    content_list: Sequence[Track],
    print_columns: Sequence[PrintableField] | None = None,
    changed_field: PrintableField | None = None,
    new_values: Sequence[str] | None = None,
):
    """Print formatted track information.

    When ``changed_field`` and ``new_values`` are both provided, the matching
    column renders each row as a before/after preview: the old value struck
    through, the new value beneath it. That column wraps rather than
    ellipsising, since both values have to stay readable at ordinary terminal
    widths.
    """
    if (changed_field is None) != (new_values is None):
        raise ValueError("changed_field and new_values must be provided together")
    if new_values is not None and len(new_values) != len(content_list):
        raise ValueError(
            f"new_values length ({len(new_values)}) must match content_list length ({len(content_list)})"
        )

    if not content_list:
        return

    print_columns = print_columns or [
        PrintableField.ID,
        PrintableField.Title,
        PrintableField.FileType,
        PrintableField.SampleRate,
        PrintableField.BitDepth,
        PrintableField.FolderPath,
        PrintableField.FileNameL,
    ]
    if changed_field is not None and changed_field not in print_columns:
        print_columns = [*print_columns, changed_field]

    table = Table(show_header=True, box=box.SIMPLE, expand=True)
    table.add_column("#", justify="right", min_width=1, no_wrap=True)
    for column in print_columns:
        cfg = _COLUMN_CONFIG.get(column, {"min_width": 5})
        # The changed column carries both values, so it needs roughly twice the
        # width of any other. Ellipsised at a real terminal width it shows the
        # old value and truncates the new one away, which is the half nobody
        # can check.
        previewing = column is changed_field and new_values is not None
        table.add_column(
            PRINT_HEADERS[column],
            no_wrap=not previewing,
            overflow="fold" if previewing else "ellipsis",
            **cfg,
        )

    for i, track in enumerate(content_list, 1):
        cells = []
        for col in print_columns:
            old = _cell_value(track, col)
            if col is changed_field and new_values is not None:
                cells.append(
                    f"[strike]{old}[/strike]\n[bold]{new_values[i - 1]}[/bold]"
                )
            else:
                cells.append(old)
        table.add_row(str(i), *cells)

    console.print(table)
    _logger.debug(console.export_text(clear=True))
