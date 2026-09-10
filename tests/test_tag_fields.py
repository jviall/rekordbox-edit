"""Parity checks between the tag registry and everything reading it.

The registry only earns its keep if drift fails loudly, so these assert that
`tags.TrackTags`, `DjmdContent`, the relation kinds, the edit handlers, and
the print columns all still agree with it.
"""

from typing import get_type_hints

from pyrekordbox.db6 import tables as tb

from rekordbox_edit._tag_fields import TAG_FIELDS
from rekordbox_edit.api._field_handlers import FIELD_HANDLERS
from rekordbox_edit.api._relations import RELATIONS
from rekordbox_edit.display import PrintableField
from rekordbox_edit.tags import TrackTags

#: TrackTags keys read off the audio stream rather than a tag, so they have no
#: registry row: `import` derives them all and none is editable.
_STREAM_KEYS = {"length", "file_type", "sample_rate", "bit_depth", "bitrate"}

#: Fields `edit` offers that are not audio tags at all.
_NON_TAG_FIELDS = {"Rating", "FolderPath"}


def test_every_registry_tag_is_a_track_tags_key():
    keys = set(get_type_hints(TrackTags))
    assert {f.tag for f in TAG_FIELDS} <= keys


def test_every_track_tags_key_has_a_registry_row():
    keys = set(get_type_hints(TrackTags)) - _STREAM_KEYS
    assert keys == {f.tag for f in TAG_FIELDS}


def test_every_registry_column_exists_on_content():
    columns = {c.key for c in tb.DjmdContent.__table__.columns}
    for field in TAG_FIELDS:
        assert field.column in columns, field.tag


def test_relational_rows_name_a_known_kind_and_proxy():
    for field in TAG_FIELDS:
        if field.relation is None:
            assert field.proxy is None, field.tag
            continue
        assert field.relation in RELATIONS, field.tag
        assert field.proxy is not None, field.tag
        assert hasattr(tb.DjmdContent, field.proxy), field.tag


def test_every_editable_tag_has_a_handler():
    for field in TAG_FIELDS:
        if field.edit_field is not None:
            assert field.edit_field in FIELD_HANDLERS, field.tag


def test_edit_offers_nothing_beyond_the_registry_and_the_non_tag_fields():
    from_registry = {f.edit_field for f in TAG_FIELDS if f.edit_field is not None}
    assert set(FIELD_HANDLERS) == from_registry | _NON_TAG_FIELDS


def test_key_is_the_only_tag_edit_does_not_offer():
    """Rekordbox derives KeyID from its own analysis, which would overwrite a
    user-supplied key."""
    assert [f.tag for f in TAG_FIELDS if f.edit_field is None] == ["key"]


def test_every_editable_field_can_be_printed():
    """The edit CLI renders its preview through PrintableField[field], so a
    field missing here raises KeyError at the moment it is used."""
    for field in FIELD_HANDLERS:
        assert field in PrintableField.__members__
