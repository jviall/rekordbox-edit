# edit

Bulk-edit a metadata field on tracks in your Rekordbox database.

```bash
rbe edit [OPTIONS] [TRACK-IDS]... FIELD
```

`FIELD` specifies the [DjmdContent](https://pyrekordbox.readthedocs.io/en/latest/formats/db6.html#djmdcontent) column to change:

| Field | What it changes |
| --- | --- |
| `Title` | The track title. |
| `Comment` | The comment column (`Commnt`). |
| `ArtistName` | The artist, through the shared `DjmdArtist` record. |
| `AlbumName` | The album, through the shared `DjmdAlbum` record. |
| `ComposerName` | The composer, which shares the `DjmdArtist` table with the artist. |
| `Genre` | The genre, through the shared `DjmdGenre` record. |
| `Label` | The record label, through the shared `DjmdLabel` record. |
| `ISRC` | The recording's ISRC. |
| `TrackNo` | The track number. |
| `DiscNo` | The disc number. |
| `ReleaseYear` | The release year. `ReleaseDate` is left as it is. |
| `Rating` | The 0-5 star rating. |
| `FolderPath` | The audio file the track points at. See [FolderPath](#folderpath). |

Every field above except `Rating` and `FolderPath` also comes from an audio tag, and [`import`](import.md) reads the same set. Musical key is the one tag `edit` does not offer: Rekordbox derives it from its own analysis, which would overwrite whatever you set.

`Rating`, `TrackNo`, `DiscNo`, and `ReleaseYear` hold numbers, so `--match` does not apply to them; passing it warns and sets the value directly.

## Relational fields

`ArtistName`, `AlbumName`, `ComposerName`, `Genre`, and `Label` do not live on the track's own row. Each names a record in a shared table that many tracks point at, so editing one works the way it does in Rekordbox: the track is reassigned to a record with the new name, reusing an existing one or creating it, and every other track keeps the record it had. `--replace ""` clears the field. A record nothing references any more is deleted, again matching Rekordbox.

One deliberate difference: reusing an existing album leaves that album's album-artist alone, where Rekordbox blanks it for every track on the album.

`--replace` supplies the new value. On its own it overwrites the whole field; add `--match PATTERN` to find that literal text within the field and replace only that portion:

```bash
# Rename one track outright
rbe edit --exact-title "Untitled 3" Title --replace "Acid Rain"

# Fix a typo across many titles (substring replacement)
rbe edit --title "Teh" Title --match "Teh" --replace "The"
```

## FolderPath

`FolderPath` repoints a track at an audio file on disk. Because several other columns are implicitly based on this path and other file metadata, the edit keeps these dependent columns consistent:

- `FileNameL` always matches the new path's file name, and `OrgFolderPath` is updated when it matched the old path.
- When the new file's size differs from the recorded `FileSize`, the file is probed and all of `FileType`, `SampleRate`, `BitDepth`, `BitRate`, `FileSize`, and `Length` are rewritten to match it.
- When the file name changes, the `PPTH` path tag inside the track's analysis (ANLZ) files is rewritten to match. All other analysis data is left alone.

A `--replace` path is resolved just like [`import`](import.md) does. It resolves to an absolute path, follows any symlinks, and normalizes to forward-slashes.

By default edits will be skipped in the following cases:

- The new path's file does not exist.
- The new path points to a file whose duration doesn't match what's in rekordbox _and_ the track has cues or an analysis, since those are time-indexed and would land misaligned.
- The file's format is one Rekordbox doesn't support--this is always skipped.

Each of the first two cases is a gate with its own flag, and `edit` lists the tracks it holds back and asks about it separately: `--allow-missing` writes a path with no file behind it, updating only the path columns, and `--allow-mismatch` accepts a duration that contradicts the stored length. Passing a flag answers its question up front, so no prompt appears. `--yes` takes the default answer to every prompt, and a gate's default is no, so `--yes` on its own leaves the held-back tracks skipped and reports them.

```bash
# Relocate a library folder in bulk
rbe edit FolderPath --match "/Volumes/OldDrive/Music" --replace "/Volumes/NewDrive/Music"

# Point one track at a replacement file
rbe edit --exact-title "Acid Rain" FolderPath --replace "/Users/me/Music/acid-rain-remaster.flac"
```

## Checks

- Without flags, `edit` shows every planned change and asks once before applying. See [Confirmations](../filtering.md#confirmations) for how `--dry-run`, `--interactive`, and `--yes` change that.
- `edit` writes exactly the tracks the preview showed. If in between the time you're prompted and later confirm a new track lands in your library that matches your filters, it won't be included. A track whose file changed in that window is skipped rather than written with stale metadata.
- **Rekordbox running:** writing while Rekordbox is open risks losing your changes, so `edit` will refuse to perform any writes. `--dry-run` is unaffected.

## Examples

```bash
# Preview a cleanup without touching the database
rbe edit --title "(Original Mix)" Title --match " (Original Mix)" --replace "" --dry-run

# Apply it, confirming each track
rbe edit --title "(Original Mix)" Title --match " (Original Mix)" --replace "" --interactive

# Pipe a search result in and edit those exact tracks
rbe search --playlist "Mislabeled" --print ids | rbe edit Title --match "  " --replace " " --yes
```

See [Filtering](../filtering.md) for the full filter language.

## Reference

<!-- prettier-ignore -->
::: mkdocs-click
    :module: rekordbox_edit.cli.edit
    :command: edit_command
    :prog_name: rbe edit
    :depth: 1
