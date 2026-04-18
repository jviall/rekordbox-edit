"""Convert command for rekordbox-edit."""

import logging
import os
import signal
import sys
from pathlib import Path
from typing import List, Tuple

import click
import ffmpeg
from ffmpeg import Error as FfmpegError
from pyrekordbox import Rekordbox6Database
from pyrekordbox.utils import get_rekordbox_pid

from rekordbox_edit._click import (
    PrintChoice,
    add_click_options,
    global_click_filters,
    print_option,
    track_ids_argument,
)
from rekordbox_edit.logger import get_debug_file_path, set_level
from rekordbox_edit.query import get_filtered_content
from rekordbox_edit.utils import (
    OutputFormats,
    UserQuit,
    confirm,
    get_audio_info,
    get_extension_for_format,
    get_file_type_for_format,
    get_file_type_name,
    print_track_info,
)

logger = logging.getLogger(__name__)


def convert_to_lossless(input_path, output_path, output_format):
    """Convert lossless file to another lossless format, preserving bit depth."""
    from rekordbox_edit.utils import ffmpeg_in_path, get_ffmpeg_directions

    logger.debug(
        f"convert_to_lossless: {input_path} -> {output_path} (format={output_format.value})"
    )

    if not ffmpeg_in_path():
        raise Exception(f"FFmpeg not found in PATH.{get_ffmpeg_directions()}")

    audio_info = get_audio_info(input_path)
    bit_depth = audio_info["bit_depth"]
    logger.debug(
        f"Source audio: bit_depth={bit_depth}, sample_rate={audio_info.get('sample_rate')}, channels={audio_info.get('channels')}"
    )

    codec_maps = {
        "aiff": {16: "pcm_s16be", 24: "pcm_s24be", 32: "pcm_s32be"},
        "wav": {16: "pcm_s16le", 24: "pcm_s24le", 32: "pcm_s32le"},
        "flac": None,
    }

    if output_format.value not in codec_maps:
        raise Exception(f"Unsupported lossless format: {output_format}")

    codec_map = codec_maps[output_format.value]
    if codec_map is None:
        codec = output_format.value
    elif bit_depth in codec_map:
        codec = codec_map[bit_depth]
    else:
        codec = list(codec_map.values())[0]
        logger.debug(f"bit_depth={bit_depth} not in codec map, falling back to {codec}")

    logger.debug(f"Selected codec: {codec} (bit_depth={bit_depth})")

    output_options = {"acodec": codec, "map_metadata": 0, "write_id3v2": 1}
    logger.debug(f"Invoking ffmpeg with options: {output_options}")

    try:
        (
            ffmpeg.input(input_path)
            .output(output_path, **output_options)
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
        logger.debug(f"Conversion to {output_format.value} succeeded: {output_path}")
        return True
    except FfmpegError as e:
        logger.error(f"FFmpeg conversion failed for {input_path}: {e}")
        if e.stderr:
            stderr = e.stderr.decode() if isinstance(e.stderr, bytes) else e.stderr
            logger.debug(f"FFmpeg stderr:\n{stderr}")
        return False
    except Exception as e:
        logger.error(f"Conversion failed for {input_path}: {e}")
        raise e


def convert_to_mp3(input_path, mp3_path):
    """Convert lossless file to MP3 320kbps CBR."""
    from rekordbox_edit.utils import ffmpeg_in_path, get_ffmpeg_directions

    logger.debug(f"convert_to_mp3: {input_path} -> {mp3_path}")

    if not ffmpeg_in_path():
        raise Exception(f"FFmpeg not found in PATH.{get_ffmpeg_directions()}")

    try:
        acodec = "libmp3lame"
        audio_bitrate = "320k"
        map_metadata = 0
        write_id3v2 = 1

        logger.debug(
            f"Invoking ffmpeg with options: {acodec, audio_bitrate, map_metadata, write_id3v2}"
        )
        (
            ffmpeg.input(input_path)
            .output(
                mp3_path,
                acodec=acodec,
                audio_bitrate=audio_bitrate,
                map_metadata=map_metadata,
                write_id3v2=write_id3v2,
            )
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )

        logger.debug(f"Conversion to mp3 succeeded: {mp3_path}")
        return True
    except FfmpegError as e:
        logger.error(f"FFmpeg conversion failed for {input_path}: {e}")
        if e.stderr:
            stderr = e.stderr.decode() if isinstance(e.stderr, bytes) else e.stderr
            logger.debug(f"FFmpeg stderr:\n{stderr}")
        return False
    except Exception as e:
        logger.error(f"Conversion failed for {input_path}: {e}")
        raise e


def update_database_record(
    db, content_id, new_filename, new_folder, output_format
) -> None:
    """Update database record with new file information."""
    logger.debug(
        f"update_database_record: content_id={content_id}, new_filename={new_filename}, output_format={output_format}"
    )
    content = db.get_content().filter_by(ID=content_id).first()
    if not content:
        raise Exception(f"Content record with ID {content_id} not found")

    converted_full_path = os.path.join(new_folder, new_filename)
    logger.debug(f"Probing converted file: {converted_full_path}")
    converted_audio_info = get_audio_info(converted_full_path)
    converted_bitrate = converted_audio_info["bitrate"]

    if output_format.upper() == "MP3" and converted_bitrate is None:
        logger.debug("MP3 bitrate not found in probe, assuming 320kbps")
        converted_bitrate = 320

    file_type = get_file_type_for_format(output_format)
    if not file_type:
        raise Exception(f"Unsupported output format: {output_format}")

    if output_format.upper() in ["AIFF", "FLAC", "WAV"]:
        converted_bit_depth = converted_audio_info["bit_depth"]
        database_bit_depth = getattr(content, "BitDepth", None)
        logger.debug(
            f"Bit depth check: database={database_bit_depth}, file={converted_bit_depth}"
        )

        if (
            database_bit_depth
            and converted_bit_depth
            and converted_bit_depth != database_bit_depth
        ):
            raise Exception(
                f"Bit depth mismatch for lossless transcode: database={database_bit_depth}, file={converted_bit_depth}"
            )

    content.FileNameL = new_filename
    content.FolderPath = converted_full_path
    content.FileType = file_type

    # FLAC stores bitrate as 0 in Rekordbox to represent VBR
    if output_format.upper() == "FLAC":
        content.BitRate = 0
        logger.debug(
            f"Set FileType={file_type}, BitRate=0 (FLAC), FolderPath={converted_full_path}"
        )
    else:
        content.BitRate = converted_bitrate
        logger.debug(
            f"Set FileType={file_type}, BitRate={converted_bitrate}, FolderPath={converted_full_path}"
        )


def cleanup_converted_files(converted_files) -> None:
    """Clean up converted files on error or rollback."""
    logger.debug("Cleaning up converted files due to aborted conversion.")
    for file_info in converted_files:
        try:
            os.remove(file_info["output_path"])
            logger.debug(f"Cleaned up {file_info['output_path']}")
        except Exception:
            pass


def rollback_and_cleanup(db, converted_files) -> None:
    """Roll back the database session and clean up any converted files."""
    logger.debug("Attempting DB session rollback.")
    rollback_error = None
    if db and db.session:
        try:
            db.session.rollback()
        except Exception as e:
            logger.critical(f"Encountered error during session rollback: {e}")
            logger.critical(
                "Check the state of your rekordbox library and consider reverting to a backup database if something's not right"
            )
            rollback_error = e
    else:
        logger.debug("No DB session to rollback.")
    if converted_files:
        cleanup_converted_files(converted_files)
    if rollback_error:
        raise rollback_error


def get_output_path(content, output_format) -> Tuple[str, str, str]:
    """Calculate output path for a content item."""
    src_folder_path = os.path.normpath(content.FolderPath or "")
    src_file_name = content.FileNameL or ""
    src_dirname = os.path.dirname(src_folder_path)

    extension = get_extension_for_format(output_format.upper())
    output_filename = Path(src_file_name).stem + extension
    output_path = os.path.join(src_dirname, output_filename)
    return output_path, output_filename, src_dirname


@click.command(
    epilog=f"Debug logs for each run can be found at:\n{get_debug_file_path().parent}"
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be converted without making changes",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    help="Auto-confirm the batch conversion (skip confirmation prompt)",
)
@click.option(
    "--delete/--keep",
    default=None,
    help="Delete or keep original files after conversion (default: delete for lossless, keep for MP3)",
)
@click.option(
    "--overwrite",
    is_flag=True,
    help="Overwrite existing output files instead of skipping them",
)
@click.option(
    "--interactive",
    "-i",
    is_flag=True,
    help="Confirm each file individually before converting",
)
@click.option(
    "--format-out",
    type=click.Choice(["aiff", "flac", "wav", "alac", "mp3"], case_sensitive=False),
    default="aiff",
    help="Output format (default: aiff)",
)
@add_click_options([*global_click_filters, print_option, track_ids_argument])
def convert_command(
    dry_run,
    yes,
    delete,
    overwrite,
    interactive,
    format_out,
    track_id: List[str] | None,
    track_ids: List[str] | None,
    title: List[str] | None,
    exact_title: List[str] | None,
    album: List[str] | None,
    exact_album: List[str] | None,
    artist: List[str] | None,
    exact_artist: List[str] | None,
    playlist: List[str] | None,
    exact_playlist: List[str] | None,
    format: List[str] | None,
    match_all: bool,
    print_opt: PrintChoice | None,
):
    """Convert lossless audio files between formats and update RekordBox database.

    Supports conversion from any lossless format (FLAC, AIFF, WAV) to:
    AIFF, FLAC, WAV, ALAC, or MP3.

    Skips lossy formats and files already in the target format.
    """
    from rekordbox_edit.utils import ffmpeg_in_path, get_ffmpeg_directions

    set_level(print_opt)

    piped_stdin = not sys.stdin.isatty()
    if piped_stdin:
        stdin_data = sys.stdin.read().strip()
        if stdin_data:
            track_ids = list(track_ids or []) + stdin_data.split()

    # Validate --print option requirements
    scripting_mode = print_opt in (PrintChoice.IDS, PrintChoice.SILENT)
    if scripting_mode:
        if not (dry_run or yes):
            raise click.UsageError(
                "--print=ids or --print=silent requires --dry-run or --yes to (dangerously!) skip confirmation prompts"
            )

    if piped_stdin and not (dry_run or yes):
        raise click.UsageError(
            "Piping track IDs into convert requires --dry-run or --yes to (dangerously!) skip confirmation prompts"
        )

    # Determine delete behavior: smart default based on output format
    if delete is None:
        should_delete = format_out.upper() != "MP3"
        logger.debug(
            f"Delete originals: {should_delete} (default for {format_out.upper()})"
        )
    else:
        should_delete = delete
        logger.debug(
            f"Delete originals: {should_delete} (explicit --{'delete' if delete else 'keep'})"
        )

    db = None
    converted_files = []

    def signal_handler(_signum, frame):
        logger.info("\nInterrupted. Rolling back...")
        rollback_and_cleanup(db, converted_files)
        sys.exit(1)

    signal.signal(signal.SIGINT, signal_handler)

    try:
        # === PRECONDITIONS ===
        rekordbox_pid = get_rekordbox_pid()
        if rekordbox_pid:
            if scripting_mode:
                logger.error(
                    f"Rekordbox is running (PID {rekordbox_pid}). "
                    "Cannot proceed in scripting mode."
                )
                sys.exit(1)
            logger.warning(
                f"Rekordbox is running (PID {rekordbox_pid}). Modifying the database while Rekordbox is open can cause conflicts."
            )
            try:
                if not confirm("Continue anyway?", default=False):
                    return
            except UserQuit:
                return

        if not ffmpeg_in_path():
            logger.error("FFmpeg is required but not found in PATH")
            logger.error(get_ffmpeg_directions())
            sys.exit(1)

        logger.debug("Connecting to RekordBox database...")
        db = Rekordbox6Database()
        if not db.session:
            raise Exception("No database session available")
        logger.debug("Database connection established")

        # === QUERY & FILTER ===
        result = get_filtered_content(
            db,
            track_id_args=track_ids,
            track_ids=track_id,
            formats=format,
            playlists=playlist,
            exact_playlists=exact_playlist,
            artists=artist,
            exact_artists=exact_artist,
            albums=album,
            exact_albums=exact_album,
            titles=title,
            exact_titles=exact_title,
            match_all=match_all,
        )
        filtered_content = result.scalars().all()
        logger.debug(f"Query returned {len(filtered_content)} tracks")

        target_file_type = get_file_type_for_format(format_out)
        mp3_type = get_file_type_for_format("MP3")
        m4a_type = get_file_type_for_format("M4A")

        files_to_convert = [
            content
            for content in filtered_content
            if content.FileType != target_file_type
            and content.FileType != mp3_type
            and content.FileType != m4a_type
        ]

        logger.debug(
            f"After format filter: {len(files_to_convert)} tracks need conversion (skipped {len(filtered_content) - len(files_to_convert)} already in target format or lossy)"
        )

        if not files_to_convert:
            logger.info("No files need conversion.")
            return

        # === CONFLICT CHECK ===
        conflicts = []
        convertible = []
        for content in files_to_convert:
            output_path, _, _ = get_output_path(content, format_out)
            if os.path.exists(output_path):
                conflicts.append(content)
            else:
                convertible.append(content)

        if conflicts:
            if overwrite:
                logger.info(f"{len(conflicts)} output files exist (will overwrite)")
                convertible = files_to_convert
            elif yes:
                # Silent skip when --yes without --overwrite
                if not convertible:
                    return
            else:
                logger.warning(
                    f"Skipping {len(conflicts)} files (output exists, use --overwrite)"
                )
                if not convertible:
                    logger.info("No files to convert.")
                    return

        files_to_process = convertible if not overwrite else files_to_convert

        # === PREVIEW ===
        logger.info(
            f"Found {len(files_to_process)} files to convert to {format_out.upper()}"
        )
        print_track_info(files_to_process)

        if dry_run:
            if print_opt is PrintChoice.IDS:
                print(" ".join(str(c.ID) for c in files_to_process))
            return

        # === CONFIRM ===
        if not yes and not interactive:
            try:
                if not confirm(
                    f"Convert {len(files_to_process)} files to {format_out.upper()}?",
                    default=True,
                ):
                    logger.info("Cancelled.")
                    return
            except UserQuit:
                return

        # === CONVERT ===
        for i, content in enumerate(files_to_process, 1):
            src_folder_path = content.FolderPath or ""
            src_file_name = content.FileNameL or ""
            src_format = get_file_type_name(content.FileType)
            output_path, output_filename, src_dirname = get_output_path(
                content, format_out
            )

            logger.info(f"[{i}/{len(files_to_process)}] {src_file_name}")

            if interactive:
                try:
                    if not confirm(
                        f"  Convert {src_format} to {format_out.upper()}?", default=True
                    ):
                        continue
                except UserQuit:
                    logger.info("User quit. Rolling back...")
                    rollback_and_cleanup(db, converted_files)
                    return

            if not os.path.exists(src_folder_path):
                logger.error(f"  Source not found: {src_folder_path}")
                rollback_and_cleanup(db, converted_files)
                sys.exit(1)

            if os.path.exists(output_path) and not overwrite:
                logger.debug("  Skipping: output already exists")
                continue

            if format_out.upper() == "MP3":
                success = convert_to_mp3(src_folder_path, output_path)
            else:
                success = convert_to_lossless(
                    src_folder_path, output_path, OutputFormats(format_out.lower())
                )

            if not success:
                logger.error("  Conversion failed. Aborting.")
                rollback_and_cleanup(db, converted_files)
                sys.exit(1)

            if not os.path.exists(output_path):
                logger.error("  Output file not created. Aborting.")
                rollback_and_cleanup(db, converted_files)
                sys.exit(1)

            try:
                update_database_record(
                    db, content.ID, output_filename, src_dirname, format_out.upper()
                )
                converted_files.append(
                    {
                        "source_path": src_folder_path,
                        "output_path": output_path,
                        "content_id": content.ID,
                    }
                )
            except Exception as e:
                logger.error(f"  Database update failed: {e}")
                rollback_and_cleanup(db, converted_files)
                sys.exit(1)

        # === COMMIT ===
        if not converted_files:
            logger.info("No files were converted.")
            return

        try:
            db.session.commit()
            logger.info(
                f"\nConverted {len(converted_files)} files to {format_out.upper()}"
            )
        except Exception as e:
            logger.error(f"Commit failed: {e}")
            rollback_and_cleanup(db, converted_files)
            sys.exit(1)

        # === OUTPUT ===
        if print_opt is PrintChoice.IDS:
            print(" ".join(str(f["content_id"]) for f in converted_files))

        # === DELETE ORIGINALS ===
        if should_delete:
            deleted_count = 0
            for file_info in converted_files:
                try:
                    os.remove(file_info["source_path"])
                    deleted_count += 1
                except Exception as e:
                    logger.warning(f"Failed to delete {file_info['source_path']}: {e}")
            logger.info(f"Deleted {deleted_count} original files")

    except Exception as e:
        rollback_and_cleanup(db, converted_files)
        raise e
