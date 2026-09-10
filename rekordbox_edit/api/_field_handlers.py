"""Per-field edit handlers.

Each field the `edit` command can change is one handler: it reads the field's
current value, computes the new value from the request, validates input, and
writes it. Simple columns use `StringField`; other fields subclass to add their
own encoding or relational lookup.
"""

import logging
import os
from typing import NamedTuple

from pyrekordbox import Rekordbox6Database
from pyrekordbox.db6 import tables as tb

from rekordbox_edit._tag_fields import TAG_FIELDS, TagField
from rekordbox_edit.api._relations import (
    RELATIONS,
    delete_if_orphaned,
    get_or_create,
)
from rekordbox_edit.api._utils import _sync_audio_columns, _update_anlz_paths
from rekordbox_edit.errors import DependencyMissingError
from rekordbox_edit.models import EditRequest, SkipReason
from rekordbox_edit.utils import (
    AudioInfo,
    get_audio_info,
    get_file_type_for_probe,
    parse_star_rating,
)

_logger = logging.getLogger(__name__)


class IncidentalRows(NamedTuple):
    """Rows a write touched besides the track itself.

    Rekordbox gives every row it writes a USN, so the caller stamps `created`
    and reserves one USN per row in `deleted`, which no longer exists to carry
    a stamp of its own.
    """

    created: tuple = ()
    deleted: int = 0


#: What a handler writing nothing but the track's own row returns.
NO_INCIDENTAL_ROWS = IncidentalRows()


class FieldHandler:
    """Read, compute, validate, and apply one editable field."""

    name: str
    supports_match: bool = True

    gated_skip_reasons: dict[SkipReason, str] = {}
    """Skip reasons validate_track returns that a request field authorizes,
    mapped to the name of that `EditRequest` field.

    Declared here so a caller offering to lift a gate does not keep its own
    copy of which gates exist or which flag lifts each one.
    """

    def validate_request(self, args: EditRequest) -> None:
        """Validate request-level input. Raise ValueError on bad input."""

    def validate_track(
        self, db: Rekordbox6Database, content, new_value: str, args: EditRequest
    ) -> SkipReason | None:
        """Per-track validation of a planned edit. Return a skip reason to
        exclude the track, or None to proceed."""
        return None

    def current_value(self, content) -> str | None:
        raise NotImplementedError  # pragma: no cover

    def compute_new_value(self, current: str | None, args: EditRequest) -> str | None:
        """New value as a string, or None to signal no change / skip."""
        raise NotImplementedError  # pragma: no cover

    def apply(self, db: Rekordbox6Database, content, new_value: str) -> IncidentalRows:
        """Write the new value, returning the rows the write added or removed
        alongside the track's own."""
        raise NotImplementedError  # pragma: no cover

    def post_commit(
        self, db: Rekordbox6Database, content, old_value: str | None
    ) -> None:
        """Called once per edited track after a successful commit, for work
        that must not run inside the transaction (e.g. file writes). Must not
        raise."""


def _replace(current: str | None, args: EditRequest) -> str | None:
    """Find/replace within the current value, or overwrite it wholesale.

    Plain replace assigns the value even to an empty field. Match mode needs
    existing text to search, so it skips an empty (None) field."""
    if args.match_pattern is not None:
        if current is None:
            return None
        return str(current).replace(args.match_pattern, args.replace_value)
    return args.replace_value


class StringField(FieldHandler):
    """A plain text column edited in place."""

    supports_match = True

    def __init__(self, name: str, column: str):
        self.name = name
        self.column = column

    def current_value(self, content):
        return getattr(content, self.column)

    def compute_new_value(self, current, args):
        return _replace(current, args)

    def apply(self, db, content, new_value):
        setattr(content, self.column, new_value)
        return NO_INCIDENTAL_ROWS


class RatingField(FieldHandler):
    """A 0-5 star rating, stored as the star count itself. `--match` does not
    apply."""

    name = "Rating"
    supports_match = False

    def validate_request(self, args):
        if args.match_pattern is not None:
            _logger.warning(
                "--match does not apply to Rating; setting the value directly"
            )
        parse_star_rating(args.replace_value)  # raises ValueError on bad input

    def current_value(self, content):
        stored = content.Rating
        return None if stored is None else str(stored)

    def compute_new_value(self, current, args):
        return str(parse_star_rating(args.replace_value))

    def apply(self, db, content, new_value):
        content.Rating = int(new_value)
        return NO_INCIDENTAL_ROWS


class IntegerField(FieldHandler):
    """A whole-number column: track number, disc number, or release year.

    `--match` does not apply, so the value is validated once per request
    rather than per track. A cleared value writes 0, the value an import
    stores for a tag the file does not carry.
    """

    supports_match = False

    def __init__(self, name: str, column: str):
        self.name = name
        self.column = column

    def validate_request(self, args):
        if args.match_pattern is not None:
            _logger.warning(
                f"--match does not apply to {self.name}; setting the value directly"
            )
        self._parse(args.replace_value)  # raises ValueError on bad input

    def _parse(self, value: str) -> int:
        if value == "":
            return 0
        try:
            return int(value)
        except ValueError:
            raise ValueError(
                f"{self.name} must be a whole number, got {value!r}"
            ) from None

    def current_value(self, content):
        stored = getattr(content, self.column)
        return None if stored is None else str(stored)

    def compute_new_value(self, current, args):
        return str(self._parse(args.replace_value))

    def apply(self, db, content, new_value):
        setattr(content, self.column, int(new_value))
        return NO_INCIDENTAL_ROWS


class RelationalField(FieldHandler):
    """A shared record reached through a foreign key: artist, album, genre, or
    label.

    Setting the value reuses an existing record with the same name or creates
    one, then repoints the track. A record left with no references is deleted,
    matching Rekordbox. Reusing an album leaves its album-artist untouched, and
    new albums are created without one.
    """

    supports_match = True

    def __init__(self, name: str, fk_column: str, name_attr: str, kind: str):
        self.name = name
        self.fk_column = fk_column
        self.name_attr = name_attr
        self.kind = kind

    def current_value(self, content):
        return getattr(content, self.name_attr)

    def compute_new_value(self, current, args):
        return _replace(current, args)

    def apply(self, db, content, new_value):
        old_id = getattr(content, self.fk_column)
        created: list = []
        if new_value == "":
            setattr(content, self.fk_column, RELATIONS[self.kind].empty_value)
        else:
            record = get_or_create(db, self.kind, new_value, created)
            setattr(content, self.fk_column, record.ID)
        db.session.flush()
        collected = delete_if_orphaned(db, self.kind, old_id)
        return IncidentalRows(tuple(created), collected)


class FolderPathField(FieldHandler):
    """The track's audio file path. Repoints the row at a file on disk and
    keeps the columns describing that file in sync.

    Validation stats the target: a missing file skips the track (or, under
    allow_missing, writes the path without any metadata sync), a byte-identical
    file needs no probe or sync, and a changed file is probed. A probed duration
    contradicting the stored Length gates tracks whose cues or analysis are
    time-indexed, since those would land misaligned; allow_mismatch lifts that
    gate. A probe no Rekordbox FileType matches always skips."""

    name = "FolderPath"
    supports_match = True
    gated_skip_reasons = {
        "file_not_found": "allow_missing",
        "length_mismatch": "allow_mismatch",
    }

    _LENGTH_TOLERANCE_SECONDS = 1.0

    def __init__(self):
        self._probes: dict[tuple[str, str], AudioInfo] = {}

    def validate_request(self, args):
        # This handler is a module-scope singleton in FIELD_HANDLERS, so probes
        # from an earlier request would otherwise outlive it.
        self._probes.clear()

    def current_value(self, content):
        return content.FolderPath

    def compute_new_value(self, current, args):
        new_value = _replace(current, args)
        if new_value is None:
            return None
        return new_value.replace("\\", "/")

    def validate_track(self, db, content, new_value, args):
        if not os.path.exists(new_value):
            if args.allow_missing:
                _logger.warning(
                    f"{new_value} does not exist; writing the path without "
                    "syncing audio metadata"
                )
                return None
            return "file_not_found"
        if os.path.getsize(new_value) == content.FileSize:
            return None  # byte-identical file: nothing to probe or sync
        try:
            probe = get_audio_info(new_value)
        except DependencyMissingError:
            # A missing install is not a property of this track
            # Re-raise up to the handler so that we can prompt for install
            raise
        except Exception:
            return "unknown_file_type"
        if get_file_type_for_probe(probe["codec"], probe["container"]) is None:
            _logger.debug(
                f"skip candidate id={content.ID}: probe of {new_value} "
                f"(codec={probe['codec']!r}, container={probe['container']!r}) "
                "matches no Rekordbox file type"
            )
            return "unknown_file_type"
        self._probes[(str(content.ID), new_value)] = probe
        duration = probe["duration"]
        if (
            duration is not None
            and content.Length is not None
            and abs(duration - content.Length) > self._LENGTH_TOLERANCE_SECONDS
        ):
            mismatch = (
                f"{new_value} runs {duration:.1f}s but the track's stored "
                f"length is {content.Length}s"
            )
            if args.allow_mismatch:
                _logger.warning(f"{mismatch}; cues and beat grid may be misaligned")
            elif self._has_time_indexed_analysis(db, content):
                return "length_mismatch"
            else:
                _logger.warning(mismatch)
        return None

    def apply(self, db, content, new_value):
        old_path = content.FolderPath
        if content.OrgFolderPath == old_path:
            content.OrgFolderPath = new_value
        content.FolderPath = new_value
        content.FileNameL = new_value.rsplit("/", 1)[-1]
        self._sync_from_file(content, new_value)
        return NO_INCIDENTAL_ROWS

    def _sync_from_file(self, content, new_value) -> None:
        """Rewrite the columns describing the audio file, when there is a
        changed file to read them from."""
        if not os.path.exists(new_value):
            return
        file_size = os.path.getsize(new_value)
        if file_size == content.FileSize:
            return
        probe = self._probes.get((str(content.ID), new_value))
        if probe is None:
            probe = get_audio_info(new_value)
        file_type = get_file_type_for_probe(probe["codec"], probe["container"])
        if file_type is None:
            return  # validate_track skips these; unreachable in the pipeline
        _sync_audio_columns(content, probe, file_type, file_size)
        if probe["duration"] is not None:
            content.Length = int(probe["duration"])

    def post_commit(self, db, content, old_value):
        old_name = (old_value or "").rsplit("/", 1)[-1]
        if content.FileNameL == old_name:
            return  # PPTH stores only ?/<name>; a directory move leaves it valid
        try:
            _update_anlz_paths(db, content, content.FileNameL)
        except Exception as e:
            _logger.warning(
                f"Failed to update ANLZ path tags for {content.FileNameL}: {e}"
            )

    def _has_time_indexed_analysis(self, db, content) -> bool:
        if content.AnalysisDataPath:
            return True
        cue = db.session.query(tb.DjmdCue).filter_by(ContentID=content.ID).first()
        return cue is not None


def _handler_for(tag_field: TagField) -> FieldHandler:
    """The handler for one editable tag, chosen by how its column stores the
    value: through a foreign key, as a number, or as text."""
    name = tag_field.edit_field
    assert name is not None and tag_field.column is not None
    if tag_field.relation is not None:
        assert tag_field.proxy is not None
        return RelationalField(
            name, tag_field.column, tag_field.proxy, tag_field.relation
        )
    if isinstance(tag_field.default, int):
        return IntegerField(name, tag_field.column)
    return StringField(name, tag_field.column)


#: Every field `edit` can change. The tag-backed ones come from TAG_FIELDS so
#: `edit` and `import` cannot drift apart; Rating and FolderPath are not audio
#: tags and are declared here.
FIELD_HANDLERS: dict[str, FieldHandler] = {
    handler.name: handler
    for handler in (
        *(_handler_for(f) for f in TAG_FIELDS if f.edit_field is not None),
        RatingField(),
        FolderPathField(),
    )
}
