## v0.13.1 (2026-09-10)


- fix(import): fill the audio columns from the file's stream header
- fix(edit): tell the user how to repair a stale analysis path
- fix(rating): use rekordbox's 0-5 scale, not the XML x51 encoding
- fix(display): keep the new value visible in a change preview
- The changed column rendered the old and new values into one cell that was
no-wrap with ellipsis overflow. For FolderPath the old value alone fills
the column at any ordinary terminal width, so the new value was truncated
away and --dry-run showed only what the row already held. A bulk repoint
was unverifiable from it; the new value first appeared around 600 columns.
- The column now wraps instead of ellipsising when it carries a preview, and
the new value renders beneath the struck-through old one.
- The existing test missed this by asserting against a 400-column console
with a single short column, which is not a width anyone runs.
- chore(deps): update dependency click to v8.5.0
- fix(edit): survive a row whose analysis directory is missing
- A row can carry an AnalysisDataPath naming a directory that was never
created. get_anlz_paths scans that directory, so it raises rather than
returning nothing, and the call sat outside the per-file guard.
- The rewrite runs in post_commit, after the whole edit has been committed,
so the raise aborted the loop with every FolderPath already written and
the remaining PPTH tags stale. A re-run could not repair it: the paths
match by then, no ops are planned, and post_commit never runs again.

## v0.13.0 (2026-09-08)


- fix: preserve unreadable ANLZ tags when rewriting a track's path
- The PPTH rewrite went through AnlzFile.save(), which rebuilds a file from
the tags pyrekordbox parsed and discards the rest. PVB2, the seek index
Rekordbox writes for every analysed FLAC, is one it has no structure for,
so every edit and convert that changed a filename dropped it. Across a
24,698-file library, 1,787 files lost an 8,032-byte PVB2, and 10 more
could not be parsed at all, leaving a stale path behind a successful write.
- _anlz.py rewrites the tag by splicing bytes and correcting len_file. Tags
are walked by declared length instead of being parsed, so a tag with no
reader here survives and an unparseable file is still rewritten. Each
analysis file is handled on its own, so one malformed file no longer
abandons the rest of a track's analysis.
- docs(research): investigate integrating rekordbox-edit with beets
- fix(edit): give the records an edit creates and collects their USNs
- An edit that reassigned a relational field left the record it created
unstamped and the one it collected outside the counter, so a syncing peer
never learned about either. import and remove already did both.
- feat(edit): support the remaining audio-tag columns
- Adds Genre, Label, ComposerName, ISRC, TrackNo, DiscNo, and ReleaseYear,
built from the tag registry so edit and import cover the same set. Key is
left out: Rekordbox derives it from analysis.
- refactor: name the audio tags import reads in one registry
- Which column a tag lands in was spread across _resolve_relations and the
add_content call; edit needs the same mapping to stay in step with import.
- refactor(api): gather shared-record handling behind _relations
- edit, import, and remove each carried their own copy of which table holds a
kind, which columns count as a reference to it, and how a new one is made.
- test(e2e): cover the remove command
- test(e2e): give the fixture rows a Rekordbox-shaped ImagePath
- The fixture audio carries no embedded art, so analysis left every row with
an empty ImagePath and no e2e case could reach the artwork cleanup.
- test(e2e): share the private-DB fixtures through conftest

## v0.12.0 (2026-09-07)


- refactor(api)!: gather the public surface behind rekordbox_edit.api
- The errors a command raises on purpose now all live in
rekordbox_edit.errors, which docs/api.md documents as the error surface,
rather than three of them hiding in modules that are now private.
ConvertProgress appears in convert()'s signature, so the package
re-exports it, and remove() joins the package's own re-exports.
- The API reference gains a Progress section for ConvertProgress, moves
Errors below what it serves, and renders each mkdocstrings block one
level under its section heading instead of beside it.
- BREAKING CHANGE: ConvertAborted, ImportInputError, and
DirectoryConfirmationRequired import from rekordbox_edit.errors.
- refactor(api): make every implementation module private
- search, import_, and field_handlers were reachable as public modules,
which put their internals — the module logger among them — in the
documented API surface. The public surface is the five functions
rekordbox_edit.api re-exports.
- refactor: make each module's logger private
- A module's logger was part of its public surface, and mkdocstrings
documented it as such.
- refactor(api): rename the submodules the re-exports shadowed
- edit, convert, and remove each shared a name with the function
api/__init__.py re-exports, which rebound the package attribute and left
the module unreachable by attribute access or dotted string. Closes #212.
- feat!: require at least one filter on write commands
- An unfiltered edit, convert, or remove matched every track in the
library, and with --yes it ran without a prompt. Closes #215.
- BREAKING CHANGE: EditRequest, ConvertRequest, and RemoveRequest now
reject a request with no selection filter.
- chore(deps): update dependency ruff to v0.16.6 (#217)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- feat: add the remove command
- Deletes a track from the library: its DjmdContent row, every child row
keyed by ContentID, its analysis and artwork files, and any artist,
album, genre, or label the removal leaves unreferenced. The source audio
file is kept unless --delete-source is passed, which unlinks it
permanently rather than moving it to the trash.
- Child tables are found by reflecting over the mapped metadata rather than
from a list, which is how the two cloud-sync tables stay covered.
- Two deliberate divergences from rekordbox, both recorded in
research/remove-track-impact/decisions/remove-command-behavior.md: the
orphan sweep repeats until nothing new becomes unreferenced, where
rekordbox sweeps once and strands an artist; and the emptied artwork
directory is removed, where rekordbox leaves it in place.
- File deletion is guarded four ways. Empty AnalysisDataPath and ImagePath
values are refused before any path resolves, since they resolve to the
share root and the directory above it. Every path must resolve under the
share directory, and each directory must sit at its expected depth, so a
malformed column value cannot reach an ancestor tier. Artwork directories
are removed with rmdir, so anything unexpected inside halts the cleanup.
- The removal confirmation defaults to yes, matching edit and convert. The
source-file prompt defaults to no and is answered up front by
--delete-source, matching convert's --overwrite.
- refactor(api): split USN reservation out of stamping
- A deleted row cannot be stamped, but the library counter must still
advance past it. `reserve_usns` claims a block without writing stamps;
`stamp_usns` calls it and is otherwise unchanged.
- refactor!: derive response tracks from the ops that carry them
- Each op now carries the track it operated on, and the top-level `tracks`
is derived from the ops rather than stored beside them. This removes the
parallel arrays the CLI paired by index, and their alignment validators.
- `tracks` means what a command actually did, so it is empty for a dry run;
the ops carry the planned state. Each write result gains `dry_run`, which
also lets a `--print json` consumer tell a dry run from a real one.
- Fixes two cases where `tracks` reported the wrong rows: `import` never
refreshed an op's track after commit, so `--print ids` returned empty IDs,
and `edit` and `convert` snapshotted the row before mutating it, so they
reported pre-write values.
- BREAKING CHANGE: `result.skipped[].id` is replaced by
`result.skipped[].track`. Read `.result.skipped[].track.ID` instead.
`tracks` is empty for a dry run; read `result.edits[].track` and its
equivalents for planned state.
- docs(research): measure what rekordbox does when a track is removed
- Six arms against ten purpose-built subjects in a rekordbox 7 library,
covering the database rows, the analysis and artwork files, orphan
collection, USN accounting, and when artwork is extracted. Records the
decisions the remove command rests on, so none of them are inferred.
- chore(deps): update pre-commit hook astral-sh/ruff-pre-commit to v0.16.6 (#218)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency ty to v0.0.78 (#213)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency filelock to v3.32.5 (#210)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency pydantic to v2.13.5 (#208)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency ty to v0.0.77 (#209)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency platformdirs to v4.11.7 (#207)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update softprops/action-gh-release digest to efb3536 (#206)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>

## v0.11.0 (2026-09-02)


- feat(convert)!: require --format-out
- BREAKING CHANGE: --format-out and ConvertRequest.format_out no longer
default to aiff. A run that picked its own target format was a guess at
what the caller wanted.
- docs: state what --yes means in one place
- The rule is that --yes takes the default answer to every prompt, and that a
gate's default is no. Each command page now links to it rather than
restating it.
- feat(convert): ask before overwriting existing output files
- Existing output files were skipped with only a warning count, so a run could
pass over them without the user noticing. The prompt defaults to no, and
--overwrite answers it up front.
- feat(convert)!: default --delete-originals to none
- BREAKING CHANGE: the default changes from lossless to none. Deleting a
source file now takes an explicit --delete-originals on the command line,
so `rbe convert --yes` no longer removes originals nobody asked it to.
- feat(edit)!: replace --force with --allow-missing and --allow-mismatch
- BREAKING CHANGE: --force and EditRequest.force are replaced by one flag per
gate, --allow-missing and --allow-mismatch, so authorizing a path with no
file behind it no longer also authorizes cues landing misaligned.
FieldHandler.forceable_skip_reasons becomes gated_skip_reasons, mapping each
reason to the request field that lifts it.
- refactor(edit)!: drop --multi
- BREAKING CHANGE: --multi is removed, along with EditRequest.multi and the
API guard behind it. --yes alone authorizes an edit across every matched
track, and an API caller has dry_run to inspect a plan first.
- docs: rewordings
- docs: reword the write guards and skip reasons
- One skip message was keyed on "length_mismatch (override with --force)",
which no SkippedTrack.reason can equal, so that reason went unreported. The
suffix belongs in the message. A test now asserts every key is a SkipReason.
- refactor(cli): move _click into the cli package
- Only cli modules imported it, but it sat at the package root. PrintChoice
went to logger.py, whose set_level is its real consumer and which is not a
click construct, so no root module now imports click or the cli package.
- fix(edit): report the tracks it passed over
- edit named skipped tracks in no code path: the held-back message sat after
the --yes branch had already returned, and _print_edit_result counted only
what it applied. A filter matching 30 tracks and editing 4 looked like it
found 4. convert and import already did this.
- feat(import): add --interactive, and let --dry-run walk directories
- import was the only write command without per-item confirmation. Its walk
gate also treated --dry-run as unauthorized, so previewing a directory was
refused even though it writes nothing and previewing is how you inspect what
a walk covers.
- A newly created track placed in a playlist stays one op, so it asks once.
- docs: match the guard and multi-flag changes
- The refusal now fires where the write happens rather than before the
preview, and --multi is only required of an unattended run, so the examples
that paired it with --dry-run or an interactive run no longer need it.
- fix(cli): reject --interactive alongside --yes or --dry-run
- Both commands branched on `yes or dry_run` and returned before reading
interactive, so the flag was discarded without a word. The scripting-mode
error compounded it by advising --yes, which is what threw it away.
- fix(edit): scope the multi guard to the unattended path
- A dry run writes nothing, so refusing to preview a bulk edit contradicted
the guard's own advice to inspect with one first, and it blocked
--interactive: that path previews before prompting, so it could never reach
the per-track confirmation it exists for. --yes and a one-shot edit() still
need multi.
- feat(api): guard writes in the API rather than the CLI
- The refusal to write while Rekordbox is open, and the single-writer lock,
were both CLI-only: any Python caller wrote underneath a running Rekordbox
and could interleave with another process. Each write function now enters
through writing(), and the advisory lock is re-entrant so the CLI's
whole-run lock still nests around it.
- A preview reaches neither check, so an interactive run refuses at the apply
pass instead of before the preview.
- fix(convert): report a missing FFmpeg as a missing dependency
- convert() raised a bare RuntimeError, so main() logged it as an unhandled
exception and asked the user to file a bug for an empty PATH. The edit path
failed differently: FolderPathField swallowed the probe error and reported
every track as unknown_file_type. Both now reach require_ffmpeg, the single
presence check.
- refactor(errors): give the API one exception hierarchy
- Bad input, a missing dependency, and an aborted write each had their own
unrelated base, so a caller could not catch one type and every command
repeated its own translation. with_database now owns the mapping to exit
codes, and confirm/UserQuit move to the CLI, leaving the shared layer free
of click.
- docs: note that the write pass applies only the previewed ops
- test(query): cover find_content_by_ids
- feat(import): import the ops the user approved
- The write pass re-walked every requested directory, so a file created
during the confirmation prompt was imported having never been previewed.
It now takes the previewed ops, which also retires the second directory
gate. _narrow_to_track_ids goes with it, unused now that interactive
selection filters the op list directly.
- feat(convert): convert the ops the user approved
- The apply pass re-ran the filter and classifier, so a track that started
matching during the confirmation prompt joined the batch unpreviewed. It
now takes the previewed ops and re-checks each op's source and output
paths, reporting a change as filesystem_changed.
- feat(edit): apply the ops the user approved
- The apply pass took the filter args and re-ran the query and classifier,
so a row that started matching during the confirmation prompt joined the
edit unpreviewed. It now takes the previewed ops, loads those rows by ID,
and reports an op whose file changed as filesystem_changed.
- fix(edit): guard the apply pass against usage errors and stale probes
- The --multi guard can fire on the apply pass, where it reached the
unhandled-exception handler. FolderPathField's probe cache is a
module-scope singleton's state and outlived its request.
- refactor(api): name the reserved USN block's upper bound
- docs: update docs on USN reservation
- fix(cli): refuse to write while Rekordbox is running
- Rekordbox holds rows in memory and can write its own copy back over
ours, so the "Continue anyway?" prompt offered a choice nobody can make
safely. Dry runs still run: they write nothing.
- fix: stamp all edited/converted/imported rows with a USN
- - convert: per-file commits mean per-file stamps, so an interrupted batch leaves
  every committed row correctly stamped.
- - import: Artist, album, genre, and label rows created along the way take one
  each. They are collected as they are made: add_content flushes, which
  moves them out of session.new first.
- fix(api): add USN stamping, wired to nothing yet
- Reserves a block of counter values in one expression UPDATE rather than
reading the counter and writing it back. Rekordbox writes to the same
counter, so the naive shape loses increments silently.
- chore(cli): Add thematic colors to console output
- feat(convert): show a live progress display while encoding
- A line per file in flight, capped by --threads, above an overall bar.
Files spin rather than fill: ffmpeg reports twice a second and a track
encodes in about two, so a per-file percentage would show three frames.
Suppressed in scripting modes and when stdout is not a terminal.
- refactor(logger): route console output through rich
- Log lines and rich tables now share one renderer. Markup is disabled
because rich reads a bracketed run as a style tag: a track named
"Set [b].wav" would otherwise log as "Set .wav".
- fix(convert): print the batch summary once
- Both the API and the CLI logged "Converted N files to X", so an
interactive run showed it twice. The API keeps its debug line; the
user-facing summary belongs to the caller.
- fix(convert): keep ffmpeg off the terminal with -nostdin
- ffmpeg puts the tty in non-canonical mode to watch for keys like "q".
Concurrent encodes race on saving and restoring that state, and the loser
restores raw mode, leaving the shell echoing ^M instead of accepting
Enter. One encode never showed it; four reproduce it every time.
- docs: measure how convert scales across output formats
- Uncompressed output is not disk-bound as assumed. ffmpeg already threads
the decode, so the gain from --threads is the spare cores divided by
those a single conversion already uses.
- chore: update codecov config
- docs(convert): document --threads and the result ordering
- feat(convert): print progress on completion and report an interrupt
- With several encodes in flight, a line printed at dispatch names a file
that is not the one being worked on next. Ctrl-C now says what it kept.
- feat(convert): add --threads to encode files concurrently
- Defaults to min(4, cpu_count): MP3 and FLAC output scale well across
files, while WAV and AIFF output is close to pure I/O and can get slower
under concurrency on the external drives DJs keep libraries on.
- refactor(convert): drain encodes through a thread pool
- Fixed at one worker, so behavior is unchanged. Results are drained in
submission order rather than completion order, and only as many jobs run
ahead of the drain point as the pool is wide, so an abort cannot burn the
whole batch's CPU first.
- refactor(convert): snapshot each encode's inputs into a plain job
- The encode half now takes values copied off the content row rather than
the row itself, so it can move onto a worker thread without reaching
back into a session that is not thread-safe.
- docs: record how master.db behaves under concurrent access
- Covers WAL mode, why a read opens no transaction, and how the identity
map hides fresh data, then applies it to the plan-apply window and to
maintaining the USN counter. Includes a glossary of the database terms.
- refactor(cli): pass confirmation flags to the scripting guard directly
- The guard read them off an object, so every caller built a throwaway class
to carry two booleans it already had as locals.
- refactor(convert): drop the record-update wrapper
- The probe and apply halves are called directly. The wrapper only chained
them and rebuilt a path the caller already had.
- docs(convert): describe what an interrupted run leaves behind
- feat(convert): report converted, failed, and unattempted counts on abort
- A stopped batch leaves real committed work, so it exits through a plain
error naming the failed file rather than through the crash handler.
- feat(convert): commit each conversion in its own transaction
- An interrupted run now leaves the database describing exactly the files
that converted, and each original is deleted right after its own commit,
so peak disk stays flat instead of doubling. ConvertAborted carries the
converted, failed, and not-attempted counts to the caller.
- feat(convert): encode to a temp file and move it into place
- A hard kill now leaves a recognizable orphan rather than a truncated file
at the path the database points at. Each run sweeps the destination
directories it is about to write to.
- refactor(convert): split the record update into probe and apply halves
- The probe half reads the converted file without touching the session, so
it can move onto a worker thread when encoding goes parallel. Passing the
content row in retires a redundant re-query.
- fix(locking): raise the scripted lock wait to 30 seconds
- Also corrects the FAQ, which read as a blanket block on concurrent runs.
- feat(cli): serialize write commands behind a single-writer lock
- Write commands hold an advisory file lock on the database directory for
their whole run. Interactive runs fail immediately when it is held;
--yes runs wait five seconds. Dry runs and search never take it.
- Also sets PRAGMA busy_timeout so a write contended by Rekordbox itself
waits rather than raising OperationalError.
- chore(deps): update dependency platformdirs to v4.11.5 (#193)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>

## v0.10.0 (2026-08-30)


- docs: document the import command
- test(e2e): assert an imported row matches rekordbox's import shape
- feat(cli): add the import command
- - a directory argument prompts interactively and needs --directory otherwise
- an ImportInputError becomes a usage error; a write failure stays a crash
- feat(import): add the import_tracks() API
- - creates DjmdContent rows matching rekordbox's own import shape
- an existing track is only placed in the requested playlist
- ImportInputError marks bad input, keeping write failures distinct
- FolderPath is rewritten forward-slashed, which add_content backslashes on windows
- test(query): cover CollectionQuery.execute
- feat(query): add case-folded path lookup and playlist name search
- feat(models): add the import request, op, and response models
- - ImportRequest selects paths on disk, so it does not extend FilterArgs
- ImportOp records whether a track was created or only placed in a playlist
- feat(tags): read the tags rekordbox reads at import
- - per-format raw key tables for vorbis, ID3, and MP4
- mutagen replaces an ffprobe call at ~200x the speed
- MP4 ISRC comes from the xid atom; initialkey is ignored, as rekordbox does
- refactor(utils): resolve file types through a FileTypeRegistry
- - lookups key on a code, name, token, or alias
- WAV answers to WAVE, the name mutagen uses
- every type carries its extensions; OutputFormats gates what RBE writes
- docs: research the shape of a rekordbox import row
- - census of 906 un-analyzed rows
- import vs. analysis column boundary
- per-format tag key mapping
- chore(deps): update dependency ruff to v0.16.5 (#192)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency ty to v0.0.75 (#190)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency click to v8.5.0 (#189)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency platformdirs to v4.11.4 (#187)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update re-actors/alls-green digest to b5b5b37 (#186)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- docs: guard mkdocs-click blocks from prettier
- Prettier strips the leading indentation from the option lines, which
mkdocs-click requires (its parser matches ^\s+:key:), breaking the
strict build.
- test(edit): cover FolderPath probe fallbacks and gated-prompt exits
- Fixes _response() treating an explicit empty edits list as a request for
the default non-empty one, which left the empty-result path untested.
- chore: bump ruff-pre-commit to v0.16.5
- ci: validate the docs build
- restores the mkdocs-click option indentation in search.md that broke it
- test(e2e): cover FolderPath relocation, repoint, and missing-file skip
- docs(edit): document the FolderPath field and --force
- feat(cli): add --force and a held-back-track prompt to edit
- refactor(convert): reuse shared audio-column sync
- feat(edit): add FolderPath field with file-existence and length gates
- refactor(api): share ANLZ path rewrite and add probe-to-FileType lookup
- feat(utils): report duration in audio probe
- chore: ignore worktrees folder

## v0.9.0 (2026-08-27)


- chore(deps): update dependency ty to v0.0.73 (#180)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency commitizen to v4.17.1 (#178)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency platformdirs to v4.11.3 (#179)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- docs(filtering): document grouped default and --match-any
- test(e2e): cover grouped default and --match-any against the fixture DB
- Locks in the original bug report (--title + --format now intersect
instead of union) plus the new --match-any flat-OR escape hatch.
- feat(query): add --match-any flat-OR mode
- Grouped mode is now the default (previous commit), so --match-all's
old job — flattening everything into one OR-vs-AND switch — needs an
explicit OR counterpart for anyone who still wants the old fully-broad
search. match_all and match_any are mutually exclusive.
- feat(query)!: group filter conditions by kind, OR within a kind and AND across kinds
- CollectionQuery previously combined every condition in one flat list
with a single OR/AND switch, so combining two different filters (e.g.
--title and --format) matched their union instead of their
intersection. Conditions now bucket by filter kind (title, artist,
album, playlist, format, path, track_id); the default groups OR
within a bucket and ANDs across buckets. match_all()/match_any() still
flatten everything into one AND/OR, unchanged in meaning.
- chore(deps): update pre-commit hook astral-sh/ruff-pre-commit to v0.16.4 (#184)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update pre-commit hook commitizen-tools/commitizen to v4.18.0 (#183)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update pre-commit hook commitizen-tools/commitizen to v4.17.1 (#181)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- docs: add research directory with reverse-engineering findings
- Promote the durable Rekordbox behavior research out of the ignored ai-docs
tree into a committed, per-investigation research/ directory. Each folder is
self-contained (summary write-ups, scripts, evidence, decisions), with shared
tooling in research/shared/scripts. Repoint the decision-records convention
and document the research write-up structure in AGENTS.md; exclude research/
from the whitespace, end-of-file, and large-file pre-commit hooks.
- feat(edit): support editing Rating
- feat(edit): support editing Comment
- feat(edit): support editing AlbumName
- feat(edit): support editing ArtistName
- refactor(edit): dispatch fields through a handler registry
- chore: ignore .superpowers SDD scratch
- chore(deps): update astral-sh/setup-uv action to v10
- chore(deps): update dependency ruff to v0.16.3 (#174)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update pre-commit hook astral-sh/ruff-pre-commit to v0.16.3 (#175)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency ty to v0.0.71 (#173)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update linters (#170)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency platformdirs to v4.11.2 (#168)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update pre-commit hook astral-sh/ruff-pre-commit to v0.16.2 (#171)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency pre-commit to v4.6.2 (#169)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency ty to v0.0.69 (#167)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency ty to v0.0.68 (#166)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency ty to v0.0.67 (#165)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency ty to v0.0.66 (#164)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency ruff to v0.16.1 (#162)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update pre-commit hook astral-sh/ruff-pre-commit to v0.16.1 (#163)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency ty to v0.0.65 (#161)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>

## v0.8.0 (2026-08-01)


- chore(deps): update dependency commitizen to v4.17.0 (#158)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- feat!: replace --exact-path with case-insensitive --resolved-path
- Path filters now always match case-insensitively, mirroring how NTFS
and APFS treat paths. --resolved-path makes its argument absolute by
pure string math instead of Path.resolve(), so results no longer
depend on mounted drives, on-disk casing, or symlinks.
- chore(deps): update pre-commit hook commitizen-tools/commitizen to v4.17.0 (#159)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore: reduce renovate schedule to weekends
- docs: add FAQ about converts impact on USB exports
- chore(deps): update github actions (#151)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- ci: optimize the build_release_notes script

## v0.7.0 (2026-07-31)


- ci: more precise changelogs on releases
- chore: update AGENTS.md
- docs: pave FAQ page based on convert + analysis research
- feat(convert): verify source codec against FileType before converting
- test(cli): mock rekordbox pid check in edit CLI tests
- feat: add probe/file-type matcher and codec_mismatch skip reason
- feat(utils): probe codec and container in get_audio_info
- feat: adds display and filtering support for all rekordbox file types
- - creates a FileTypeInfo registry to map all the different dimensions of
  FileType under one database code
- adds AAC and ALAC .m4a FileTypes (4 and 6)
- adds .mp4 FileType (3)
- adds video FileType (16)
- chore(deps): update dependency ty to v0.0.64 (#152)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update pre-commit hook astral-sh/ruff-pre-commit to v0.16.0 (#149)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update linters (#148)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency platformdirs to v4.11.0 (#147)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency ty to v0.0.62 (#145)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update pre-commit hooks (#146)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency pre-commit to v4.6.1 (#144)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update fkirc/skip-duplicate-actions digest to a09bf67 (#143)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency ty to v0.0.61 (#142)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update actions/checkout action to v7.0.1 (#141)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency platformdirs to v4.10.1 (#140)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency mkdocs-material to v9.7.7 (#139)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency commitizen to v4.16.5 (#138)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update pypa/gh-action-pypi-publish digest to ba38be9 (#137)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update fkirc/skip-duplicate-actions digest to b974a93 (#136)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore: ignore research/decision docs
- fix(convert): update FileSize, OrgFilePath cols; PPTH ANLZ tag
- refactor(convert): merge shared logic of ffmpeg helpers
- Replace _convert_to_hi_res and _convert_to_mp3 with a single _run_ffmpeg
runner and two pure output-kwargs builders.
- fix(convert): skip unsupported source formats via input whitelist
- Previously we were skipping via a blacklist, which allowed
unknown/unsupported formats to create undefined behavior.
- refactor(convert): change get_file_type_name a simple display map
- chore(deps): update dependency ty to v0.0.59 (#134)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency syrupy to v5.5.3 (#133)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency mkdocstrings to v1.0.6 (#132)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency mkdocstrings to v1.0.5 (#131)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update softprops/action-gh-release digest to 3d0d988 (#130)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update linters (#128)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update pre-commit hook astral-sh/ruff-pre-commit to v0.15.21 (#129)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency syrupy to v5.5.2 (#127)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update astral-sh/setup-uv action to v8.3.2 (#126)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update astral-sh/setup-uv action to v8.3.1 (#125)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency syrupy to v5.5.1 (#124)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update astral-sh/setup-uv action to v8.3.0 (#123)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency syrupy to v5.4.0 (#122)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency ty to v0.0.56 (#121)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update actions/checkout action to v7
- chore(deps): update dependency ty to v0.0.55 (#120)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency syrupy to v5.3.4 (#119)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update linters (#117)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update pre-commit hook astral-sh/ruff-pre-commit to v0.15.20 (#118)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency syrupy to v5.3.3 (#116)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency ty to v0.0.53 (#115)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency click to v8.4.2 (#114)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency ruff to v0.15.19 (#112)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update pre-commit hooks (#113)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency ty to v0.0.52 (#111)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency commitizen to v4.16.4 (#110)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update github actions (#109)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update testing (#108)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update linters to v0.15.18 (#106)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update pre-commit hooks to v0.15.18 (#107)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update linters to v0.0.50 (#104)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update github actions to 718ea10 (#103)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update testing to v9.1.0 (#102)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update linters to v0.15.17 (#100)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update pre-commit hooks to v0.15.17 (#101)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update linters to v0.0.48 (#99)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency syrupy to v5.3.2 (#97)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update linters to v0.0.46 (#98)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore: ruff formatting
- fix(convert): encode MP3 at the target bit depth and sample rate
- Pass ar=44100 and sample_fmt=s16p to libmp3lame instead of inheriting
the source rate, so MP3 output always matches the 16-bit/44.1 kHz
conversion target. MP3 ConvertOps report the target instead of None.
- fix(convert): update MP3 bit depth and sample rate in database
- Converting to MP3 left the source values (e.g. 24-bit/96 kHz) on the
record. Rekordbox stores MP3s as 16-bit with the real sample rate, per
the e2e database fixtures, so write those after conversion.
- feat(convert): report audio properties on ConvertOp
- Add source/output file type, bit depth, and sample rate fields so
dry-run previews and JSON output describe each conversion fully.
Source fields mirror the database record, the output sample rate
clamps to the source, and MP3 output leaves bit depth and sample rate
to the encoder.
- fix(convert): respect bit depth and sample rate between hi-res formats
- Hi-res conversions now explicitly target 16-bit/44.1 kHz. The target
sample rate clamps to the source so nothing is ever up-sampled,
down-sampled conversions count as lossy so --delete-originals lossless
keeps those originals, and the database record is updated with the
converted file's bit depth and sample rate.
- Fixes #92
- BREAKING(convert): replace --delete/--keep with --delete-originals enum
- The tri-state boolean becomes an explicit mode: 'none' never deletes,
'all' always deletes, 'lossless' (default) deletes only for hi-res
output formats. Also drops the unsupported 'alac' --format-out choice,
which crashed at conversion time.

## v0.6.0 (2026-06-12)


- chore(deps): update dependency mkdocstrings to v1
- ci: setup python via setup-uv to fix cache key collisions
- ci: validate conventional commits always, check PR titles
- docs: clean up documentation
- chore(deps): update linters to v0.0.45 (#90)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- refactor: rename CommandArgs types to CommandRequest
- docs: open external links in a new tab with an icon
- docs: render signatures and model fields in api reference
- docs: add api reference page
- docs: add convert command page
- docs: add edit command page
- docs: add search command page
- docs: add filtering page
- docs: configure read the docs build
- docs: scaffold mkdocs material site
- docs: trim README to overview and quick start
- chore: add docs dependency group
- feat: add --last filter to return only the last N results
- feat: add --first filter to return only the first N results
- test(e2e): update windows snapshot with unicode representation
- test(e2e): force utf-8 encoding of stdout
- test(e2e): align TZ to UTC
- test(ci): parameterize the db version as an env var
- ci(e2e): add windows-latest to the e2e matrix
- test: add windows snapshots for e2e journey
- test(e2e): parameterize snapshots by fixture DB
- Routes the two contract snapshots through SNAPSHOT_KEY (macos/windows)
so the Windows fixture can land its own snapshot alongside the macOS
one. Docker reuses the macOS DB and therefore the macos key.
Renames the existing snapshot entries to the [macos] variant.
- test: adds 6.8.6 db fixture for windows
- test(e2e): pretty-print JSON snapshots via JSONSnapshotExtension
- The single-line raw CLI output made snapshot diffs unreadable when a contract
field changed. Use syrupy's JSONSnapshotExtension for the search-json test:
the parsed payload is dumped as indented JSON to its own .json file under
__snapshots__/test_journey/, so post-update diffs land per-field.
- The IDs snapshot stays on AmberExtension; it's already one short line.
- ci(e2e): add macos-latest e2e job to the matrix and require it
- Adds a new e2e-tests job to ci.yml matrix'd over macos-latest × Python
{3.11, 3.14}, wiring it into the all-green aggregate so branch protection
gates on it. Windows joins in a follow-up PR once a windows master.db
fixture exists.
- The composite action at .github/actions/e2e/ installs ffmpeg on the runner,
sets RBE_RUN_E2E=1, and runs pytest against tests/e2e directly.
- test(e2e): add docker leg and make targets
- Local e2e validation runs through a Linux container; the conftest refuses to
run on bare macOS/Windows. `make test-e2e-docker` builds the image (Python
3.14 + ffmpeg + uv-synced project) and runs the journey suite;
`make test-e2e-snapshot-update` regenerates snapshots inside the container so
the host's working tree picks them up via the volume mount.
- `make test-e2e` runs the suite directly with uv; useful inside the container
itself or in CI runners where the platform check passes.
- test(e2e): add journey suite, conftest, and macOS snapshots
- A single ordered file walks search → edit → convert against the committed
macOS master.6.8.6.db, exercising filter narrowing, dry-run safety, stdin-pipe
edits, unicode metadata, and the convert row-swap. Snapshots lock the JSON
and IDs print contracts for `search`.
- The conftest gates the suite behind RBE_RUN_E2E=1 and refuses to run on
macOS/Windows outside CI, pointing local users at the Docker leg. The
canonical staging path is /private/tmp/rbedit-e2e/music — macOS resolves
/tmp through that symlink, so the DB stores the canonical form.
- Excludes tests/e2e/__snapshots__/ from the trailing-whitespace and
end-of-file pre-commit hooks; syrupy-generated whitespace is meaningful.
- test(e2e): register marker, exclude from default collection, add syrupy
- Adds the `e2e` pytest marker, sets `norecursedirs` so default `make test` runs
do not collect the suite, and pins syrupy>=5 for snapshot assertions.
- test: add macos 6.8.6 db fixture
- test(e2e): rename audio fixtures to property-encoded scheme
- Filenames now describe the audio's discriminating properties
(NN-<codec>-<rate>-<depth-or-bitrate>[-encmode].<ext>) so each file's purpose
is obvious in a directory listing and in test code. Codec stays in the name
even for unambiguous extensions to keep the convention uniform and to
disambiguate ALAC vs AAC inside .m4a.
- Required before Phase 3 (Rekordbox import) so master.db references the new
paths. Generator script and library table updated in gist
https://gist.github.com/jviall/18107ca35e0e7f38cf02ba50e3b9cc77
- test(e2e): add 10-track audio fixture for end-to-end suite
- Synthesized sine-wave audio covering FLAC (16/24-bit), ALAC, AIFF, WAV,
MP3 (CBR + VBR), AAC, and a unicode-tagged FLAC. Used by the e2e journey
suite (search/edit/convert) against the committed master.db fixtures.
- Bumps pre-commit's check-added-large-files threshold to 1 MB to admit the
WAV fixture (563 KB at 96 kHz / 24-bit / 2 s mono).
- Generator script and Phase 3 (Rekordbox import) instructions:
https://gist.github.com/jviall/18107ca35e0e7f38cf02ba50e3b9cc77
- fix(query): order results by folder, then ID, for stable output
- feat: adds global --database-path argument
- chore(deps): update linters to v0.0.44 (#79)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- test: restore coverage lost during api/cli redesign
- Restore tests for ffmpeg conversion internals, post-commit/rollback
paths, and the CLI preview-confirm-commit default flow that the
single-function API redesign dropped. Coverage recovers from 87% to
97% (baseline pre-redesign was 98%) and the test count from 200 to
238.
- refactor: privatize module-internal helpers and unify cli print helpers
- - api/convert.py: prefix module-private helpers with underscore
  (_convert_to_lossless, _convert_to_mp3, _update_database_record,
  _cleanup_converted_files, _rollback_and_cleanup, _get_output_path)
- cli/{edit,convert}.py: rename _render_*_response to _print_*_result
- fix(api,cli): fixups post refactor
- - convert(): on post-commit re-query failure, fall back to pre-mutation
  snapshot tracks instead of an empty list, so the response validator
  doesn't raise after a successful commit
- cli/convert.py: remove duplicate "Deleted N" log in the default flow
- cli/edit.py: log "No changes to make." in --yes path when no edits
- Adds a regression test for the post-commit re-query fallback.
- feat(api,cli)!: redesign around single-function commands
- Replace the plan/execute split with one function per command that takes
an optional dry_run kwarg. Each command (search, edit, convert) now
returns a typed response envelope with tracks plus a command-specific
result. CLI restructured to preview-then-commit by default and to call
the API exactly once when --yes or --dry-run is given.
- BREAKING CHANGE: drops plan_edit/plan_convert. The public API surface is
now search/edit/convert; old EditPlanArgs/ConvertPlanArgs types removed.
- feat: add new `--print json` option
- refactor: Allow extra columns to ride with Track instances
- chore(deps): update linters to v0.15.16 (#76)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- fix: handle stdin BOM character on windows
- chore(deps): update linters to v0.0.43 (#73)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update github actions to v8.2.0 (#74)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>

## v0.5.0 (2026-06-06)


- ci: use workflow token
- chore(deps): update github actions (#71)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- ci: fix canary release increment
- test: add tests to cover new modules
- test: add back convert tests that got dropped
- refactor: rename args.py to models.py
- feat: wire public API and delete legacy commands/
- - feat: expose public API from rekordbox_edit.__init__
- chore: remove tests/commands/ (replaced by tests/cli/)
- chore: remove commands/ and cli.py (replaced by api/ and cli/)
- fix: resolve typecheck and lint errors in api layer and tests
- feat: add api/ and cli/ packages
- - feat: add api/_utils.py with _track_from_content
- feat: update display.py to accept Track instead of DjmdContent
- refactor(display): remove redundant setup comments in tests
- feat: add api/search.py
- feat: add api/edit.py with plan_edit and edit
- feat: add api/convert.py with plan_convert and convert
- fix(convert): remove unused get_file_type_name import
- feat: add api/__init__.py re-exports
- feat: add cli/main.py and cli/__init__.py
- feat: add cli/_utils.py with shared confirmation helpers
- feat: add cli/search.py
- feat: add cli/edit.py
- feat: add cli/convert.py
- refactor: restructure args.py with Track model and API arg types
- - refactor: add Track model and EditPlanArgs/ConvertPlanArgs to args.py
- refactor: correct docstring layer count and strengthen test assertions
- feat!: drop support for python 3.10

## v0.4.0 (2026-06-05)


- Revert "bump: version 0.3.1 → 0.4.0"
- This reverts commit c353b3ae6b24793c6911a153b021267a16473d87.
- ci: improve canary release naming and skip duplicates
- ci: use same changelog config in both release types
- ci: fix releases
- bump: version 0.3.1 → 0.4.0
- chore(deps): update crazy-max/ghaction-import-gpg action to v7
- chore(deps): update github artifact actions
- chore(deps): update softprops/action-gh-release action to v3
- chore(deps): update testing
- fix(deps): update dependency rich to v15
- fix(display): Add min-width to print columns
- refactor(args): compose command args via Pydantic model   inheritance
- refactor(args): adopt Pydantic for component arg types
- refactor(commands): group command-specific args into EditArgs and ConvertArgs dataclasses
- refactor(commands): group confirmation flags into ConfirmationArgs dataclass
- docs: update README.md
- refactor(query): group filter args into FilterArgs dataclass
- refactor(cli): extract convert-specific options into convert_click_options
- refactor(cli): extract edit-specific options into edit_click_options
- refactor(cli): extract shared confirmation flags into global_click_confirmations
- chore(deps): update linters to v0.0.42 (#58)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- fix(display): Don't crash on unknown file type during print_track_info
- chore(deps): update commit tooling to v4.16.3 (#54)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update pre-commit hooks to v4.16.3 (#55)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency platformdirs to v4.10.0 (#53)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency ruff to v0.15.15 (#50)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update pre-commit hook astral-sh/ruff-pre-commit to v0.15.15 (#51)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency ty to v0.0.40 (#49)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update astral-sh/setup-uv action to v8
- chore(deps): update actions/setup-python action to v6
- ci: clean up job skipping
- chore: add more groups to renovate config
- chore: exclude-newer for uv resolution to match renovate minimum age
- chore(deps): update dependency pre-commit to v4.6.0 (#39)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency commitizen to v4.16.2 (#38)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update pre-commit hook astral-sh/ruff-pre-commit to v0.15.14 (#37)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency click to v8.4.0 (#36)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency ty to v0.0.38 (#35)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency ruff to v0.15.13 (#34)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): pin dependencies (#33)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore: correct renovate config
- fix(display): split up the unified Location column into FolderPath and FileName
- docs: update AGENTS.md
- feat(display): add before/after change preview to print_track_info
- refactor(display): render print_track_info with rich.table.Table
- Replace the fixed-width f-string loop with a rich Table so column widths
adapt to content and embedded ANSI sequences no longer skew alignment.
PRINT_HEADERS becomes plain column labels (rich handles padding). Drain
the recorded output to the debug log after each render.
- refactor(display): extract print_track_info into display module
- Add rich dependency and move PrintableField, PRINT_WIDTHS, PRINT_HEADERS,
truncate_field, and print_track_info from utils to a new display module
with a module-level Console for upcoming rich-based rendering. Update
edit, convert, and search command imports. Move associated tests from
test_utils.py to test_display.py. Pure move; no behavior change.
- chore(deps): update pre-commit hooks (#29)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- feat(edit): add --multi to allow batch edits past single-track guard
- feat(edit): add --match for literal find/replace within field value
- Introduces a _compute_new_value helper and --match option so that
rbe edit can replace a substring of the current field value instead of
performing a wholesale replacement; None current values and non-matching
patterns are treated as no-ops.
- chore: add max-complexity lint rule
- docs: update AGENTS.md
- test: add coverage for --interactive + --yes skipping all confirms
- feat: adds edit command
- Adds an `edit` subcommand to the CLI with:
- Title field support via a required FIELD argument and --replace option
- Single-track safety guard that aborts when >1 track would be modified
- --dry-run mode that previews changes without writing to the database
- --yes flag to skip confirmation, --interactive to confirm per-track
- Scripting mode (--print=ids) requiring --yes or --dry-run
- Piped stdin rejection without --yes or --dry-run
- All global filter flags forwarded to get_filtered_content
- docs: add AGENTS.md with project conventions and CLAUDE.md symlink
- chore: add renovate config
- feat: Add --path and --exact-path search filters
- chore: add pytest-watcher and watch task in Make
- feat(CollectionQuery): add by_path query filter

## v0.3.1 (2026-04-17)


- chore: version bump 0.3.1
- ci: allow dispatching of publish workflow
- chore: big 'ol project rename cause it was too long
- docs: update readme and contributing
- chore: change commitizen config and providers to work with uv
- ci: skip CI and CD when no code-impacting changes have occurred
- docs: update readme

## v0.3.0 (2026-04-09)


- ci: add windows-latest + python 3.14 to CI matrix
- ci: Add typechecking with astral/ty
- ci: switch from poetry to uv cause I like shiny things
- tests: cover more edge cases and error paths
- fix: merge track_ids filter with other specified filters.
- - Also adds missing test cases for CollectionQuery and
  get_filtered_content
- documents scripting examples and adds AI disclaimer
- fix: improved debug logs
- fix: require --dry-run or --yes when piping track_ids
- feat: Add support for track_id arguments via STDIN for scripting
- refactor: Drop custom logger class
- feat: add debug as a PrintChoice option
- fix: drop unreachable code
- fix: match_all incorrectly set to method during query copy
- fix: add debug log folder to help output
- fix: normalize output paths
- docs: update readme
- feat(convert): add support for the print flag
- feat: refactor convert command to not suck and use the query class
- Big refactor. Huge. The convert command was some vibe-coded bs. Now it's
some vibe-coded nice stuff. Logs are much better. Way less nested
conditions, better inversion of control. Way less annoying UX.
- fix: verbose log query filters
- feat: create --print flag to specify program output preference
- feat: Add rbe command alias, update readme, and update deps
- feat: replace Read command with Search command using the CollectionQuery class
- refactor: print_track_info and related funcs
- refactor: pave new CollectionQuery class
- intended to act as a universal query builder that enables a unified set
of filters for all commands
- fix(deps): upgrade and pin pyrekordbox to 0.4.4
- fix: drop support for python 3.9
- ci: fix mismatched version of checkout action
- ci: continuously publish canary releases, selectivly publish stable releases
- ci: cleanup unused action input

## v0.2.7 (2025-08-19)


- ci: fix broken version-bump.yml
- ci: add codecov.yml config
- ci: fix codecov publishing
- fix: use a logger to separate log levels and output a log file to system user data folder
- ci: one final typo in publish.yml
- ci: don't validate empty commit ranges on main
- ci: Customize commit convention and validate during CI
- ci: fix publish workflow
- chore: fix version-bump workflow typo
- chore: add re-actors/alls-green action for easier status checks
- chore: fix workflows

## v0.2.6 (2025-08-10)

### Fix

- no default return on get_audio_info

## v0.2.5 (2025-08-02)

### Fix

- bug where convert command was trying to call .get on a function. Add happy path test cases for convert command
- use getter functions for the file type and extension maps

### Refactor

- drop psutils in favor of pyrekordbox.utils

## v0.2.4 (2025-08-01)

### Fix

- Filter out all m4a and mp3 targets

## v0.2.3 (2025-08-01)

### Fix

- Check if ffmpeg exists and if not point to installation.

## v0.2.2 (2025-08-01)

### Fix

- Attempt to fix broken paths on windows

## v0.2.1 (2025-07-31)

### Fix

- Add unit tests for utils and convert. Make is_rekordbox_running() more specific. Fix bad Error handling on ffmpeg

### Refactor

- clean up variables

## v0.2.0 (2025-07-31)

### Feat

- Add support for all audio types in read command, and converting between all lossless types in convert command
- Add support for all audio types in read command, and converting between all lossless types in convert command
- Add support for converting to MP3 320 CBR
- Convert project into a package
- Support confirmation message at each confirmation, and wait till end of program to commit changes
- rename rekordbox_reader.py to reader.py and add support for single file ID argument with get_track_info()
- Adds convert command to convert from FLAC to AIFF
- fuzzy match column names that may be relevant to file format
- read out all FLAC files with basic info
- hello world

### Fix

- Allow for output file to already exist but confirm to use
- Update bitrate after conversion from FLAC to AIFF
