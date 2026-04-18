# rekordbox-edit

[![Tests](https://img.shields.io/github/actions/workflow/status/jviall/rekordbox-edit/ci.yml?branch=main&logo=github&style=flat)](https://github.com/jviall/rekordbox-edit/blob/main/.github/workflows/ci.yml)
[![Coverage](https://codecov.io/gh/jviall/rekordbox-edit/graph/badge.svg?token=ILZ1XHE61V)](https://codecov.io/gh/jviall/rekordbox-edit)
[![Version](https://img.shields.io/pypi/v/rekordbox-edit?style=flat)](https://pypi.org/project/rekordbox-edit/)
[![Platforms](https://img.shields.io/badge/platform-win%20%7C%20osx-blue?style=flat)](https://pypi.org/project/rekordbox-edit/)
[![License](https://img.shields.io/pypi/l/rekordbox-edit?color=lightgrey)](https://github.com/jviall/rekordbox-edit/blob/main/LICENSE)

A command-line tool for bulk operations on your Rekordbox library. Convert audio formats, search tracks, and update your database while preserving all your cues, analysis, and metadata.

> [!CAUTION]
> This tool can modify your Rekordbox database and audio files. Always back up your data first.
> No warranty is provided--you assume all risk and liability of data loss in using this.
> See [Safety & Best Practices](#safety--best-practices)

## Installation

```bash
pip install rekordbox-edit
```

**Requirements:**

- Python 3.11+
- FFmpeg (for audio conversion)

## Quick Start

Search your library:

```bash
rekordbox-edit search --artist "Daft Punk" --format flac
rbe search --playlist "House Favorites"
```

Convert audio files:

```bash
# Preview what would be converted
rbe convert --artist "Daft Punk" --dry-run

# Convert all FLAC or WAV files to AIFF (default output format)
rbe convert --format flac --format wav --yes

# Convert all AIFF files in the playlist named 'ConvertMe' to MP3 without asking for confirmation
rbe convert --format AIFF --exact-playlist "ConvertMe" --match-all --out-format mp3 --yes
```

## Commands

### search

Find and display information on tracks in your Rekordbox database.

```bash
rbe search [OPTIONS]
```

**Examples:**

```bash
# Show all FLAC tracks by artist
rbe search --artist "Aphex Twin" --format flac

# Get all the track IDs in a playlist
rbe search --playlist "Techno" --print ids

# Find tracks matching ALL filters (AND logic)
rbe search --artist "Burial" --album "Untrue" --match-all
```

### convert

Convert audio files between formats and update the Rekordbox database. Your cues, analysis, beatgrids, and all metadata are preserved.

```bash
rbe convert [OPTIONS]
```

#### Supported formats

- Input: FLAC, AIFF, WAV
- Output: AIFF, FLAC, WAV, ALAC or MP3 (320kbps CBR)

#### options

- `--format-out [aiff|flac|wav|alac|mp3]`: Output format (default: aiff)
- `--dry-run`: Preview changes without converting.
- `--yes, -y`: Skip confirmation prompt
- `--interactive, -i`: Confirm each file individually
- `--delete`: Delete original files after conversion (default for lossless output)
- `--keep`: Keep original files after conversion (default for MP3 output)
- `--overwrite`: Replace existing output files instead of skipping

By default the original files will be kept when performing a lossy conversion to mp3, and deleted when performing a lossless conversion (since you can always convert back).
You can override this behavior with `--delete` or `--keep`.

**Examples:**

```bash
# Preview conversion
rbe convert --format-out aiff --format flac --dry-run

# Convert and skip confirmation
rbe convert --format-out wav --artist "Burial" --yes

# Convert to MP3 but delete originals
rbe convert --format-out mp3 --playlist "Export" --yes --delete

# Keep originals when converting to AIFF
rbe convert --format-out aiff --format flac --yes --keep

# Get just the IDs of files that would be converted
rbe convert --format-out aiff --format flac --print ids --dry-run

# Convert and get the IDs of converted tracks
rbe convert --format-out aiff --format flac --print ids --yes
```

## Filters & Options

Both commands support all filters. Multiple values create an OR filter unless `--match-all` is used.

**Track filters:**

- `--track-id ID`: Filter by database track ID
- `--title TEXT`: Track title contains TEXT
- `--exact-title TEXT`: Track title exactly matches TEXT
- `--artist TEXT`: Artist name contains TEXT
- `--exact-artist TEXT`: Artist name exactly matches TEXT
- `--album TEXT`: Album name contains TEXT
- `--exact-album TEXT`: Album name exactly matches TEXT
- `--playlist TEXT`: Playlist name contains TEXT
- `--exact-playlist TEXT`: Playlist name exactly matches TEXT
- `--format [mp3|flac|aiff|wav|m4a]`: File format matches
- `--match-all`: Use AND logic (all filters must match)
- `ids` args: Specifying any other input to a command that is not a defined option is interpreted as one or more Track IDs. This is useful for scripting.

**Examples:**

```bash
# Get tracks by multiple artists
rbe search --artist "Daft Punk" --artist "Justice"

# Get tracks matching artist AND format
rbe search --artist "Aphex Twin" --format flac --match-all

# Get all the songs in this playlist
rbe search --exact-playlist "Main Room 2024"

# Get all the songs in all my "house" or "disco" playlists
rbe search --playlist "house" --playlist "disco"

# Find all the songs in all my "house" or "disco" playlists
rbe search --playlist "house" --playlist "disco"

# Find all the songs in my library that aren't in any playlist
rbe search --playlist ""
```

## Output

All commands support all levels of output. These generally control how much information is printed out to the screen, and also offer some options useful for scripting.

Output levels are configured with the `--print` option:

- `--print [ids|silent|info|debug]`: Control output format

> [!NOTE]
> When specifying `--print silent` or `--print ids`, you must also explicitly provide either the `--yes` or the `--dry-run` flag, since any prompts would contradict the spirit of those print options.

### Scripting

The `--print ids` option is especially interesting when used in conjunction with the `ids` arguments. By specifying `--print ids` you can use the output of one `rbe` command as the input to a second, e.g.:

```bash
# Convert all of the items found by the initial search command
rbe search --artist "Lauren Hill" --print ids | rbe convert
```

This example is a bit contrived, but this method of piping can be used to combine OR and AND logic that couldn't otherwise be expressed in a single command:

**AND-narrowing** — pipe a broad OR result into a second command with `--match-all` to intersect:

```bash
# (Daft Punk OR Justice) AND flac
rbe search --artist "Daft Punk" --artist "Justice" --print ids \
  | rbe search --format flac --match-all
```

**OR between AND-groups** — merge results from two commands using a subshell:

```bash
# (Daft Punk AND flac) OR (Justice AND aiff)
{ rbe search --artist "Daft Punk" --format flac --match-all --print ids; \
  rbe search --artist "Justice" --format aiff --match-all --print ids; } \
  | rbe convert --format-out mp3 --dry-run
```

## Safety & Best Practices

**Before using this tool:**

1. **Back up your Rekordbox database**

   Rekordbox already keeps multiple backups. But every time you close it, it creates a fresh one and deletes the oldest, so repetitive exits will quickly make those backups fairly useless.

   You should make manual copies of RB's database backups before using this. You can usually find them in `~/Library/Pioneer/rekordbox/` on macOS or `%APPDATA%\Pioneer\rekordbox\` on Windows.

2. **Back up your music library**

   If you don't have a back up already it's a very worthwhile investment, even if you don't plan to use this tool! Find yourself a cheap external drive, you won't regret it.

And generally limit the potential impact of a mistake by using filters to target a few tracks at a time e.g. `--artist "Crazy Frog" --limit 5` before targeting a larger set, and always run with `--dry-run` first.

## AI Usage

I believe it's important to be aware of and to disclose AI usage. AI usage seems to be forced upon us without us having much choice in the matter, and I like many others find this to be a gross and oppressive experience.

I do also believe that it has its potential for good, and could be used for humanity's immense benefit if it weren't for capitalist greed.

This isn't a soapbox, but I want to share my perspective and disclose the fact that I have used generative AI to help me build this tool. I could have built it without AI, but it's not usually my preference to spend my free time coding in front of a computer, and using it has drastically reduced the time it would have taken me to build this.

I have nearly 10 years of professional experience as a Software Engineer, and while it will probably age poorly in the (hopefully far) future to say this, I don't think AI could have built this tool without me. You should of course validate the quality of this project yourself, as at the end of the day it's just code written by some stranger!

If it's any consolation, my main test subject has been my own 10,000+ track RekordBox library--a risk I do not take lightly!

## Credits

This project exists thanks to [@dylanjones](https://github.com/dylanjones), the creator of [pyrekordbox](https://github.com/dylanljones/pyrekordbox), which provides the Python API for Rekordbox databases.

I built this tool to help correct my own bad habits and misteps in managing and organizing my rekordbox library. If it helps you too, great! If you find issues or have ideas, contributions are welcome.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, testing, and contribution guidelines.
