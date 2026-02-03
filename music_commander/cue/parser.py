"""CUE sheet parser.

Parses .cue files into structured dataclasses for use by the splitter
and other cue-related commands. Ported from /space/Music/bin/split-albums
with bug fixes and improvements.
"""

from __future__ import annotations

import logging
import re
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Characters unsafe for filenames
_UNSAFE_FILENAME_CHARS = re.compile(r'[/\\:*?"<>|]')

# CD audio constants
CD_SAMPLE_RATE = 44100
CD_FRAMES_PER_SECOND = 75
CD_SAMPLES_PER_FRAME = CD_SAMPLE_RATE // CD_FRAMES_PER_SECOND  # 588


@dataclass
class CueTrack:
    """A single track within a cue sheet."""

    track_num: int
    title: str = ""
    performer: str = "Unknown"
    songwriter: str | None = None
    isrc: str | None = None
    index: str = "00:00:00"
    start_samples: int = 0
    end_samples: int | None = None

    # Inherited from global context
    album: str = "Unknown"
    genre: str | None = None
    date: str | None = None
    disc_id: str | None = None
    file: str | None = None


@dataclass
class CueSheet:
    """A parsed cue sheet with global metadata and track list."""

    performer: str = "Unknown"
    album: str = "Unknown"
    genre: str | None = None
    date: str | None = None
    songwriter: str | None = None
    disc_id: str | None = None
    comment: str | None = None
    file: str | None = None
    tracks: list[CueTrack] = field(default_factory=list)


class CueParseError(Exception):
    """Raised when a cue sheet cannot be parsed."""


class CueParser:
    """Parses a .cue file into a CueSheet structure.

    Handles global metadata, per-track overrides, multi-FILE cue sheets,
    and sample-accurate position calculation for CD audio (44100Hz, 75fps).
    """

    def __init__(self, cue_file: str | Path, encoding: str | None = None):
        self._context_global: dict[str, str | None] = {
            "PERFORMER": "Unknown",
            "SONGWRITER": None,
            "ALBUM": "Unknown",
            "GENRE": None,
            "DATE": None,
            "FILE": None,
            "COMMENT": None,
            "DISCID": None,
        }
        self._context_tracks: list[dict[str, object]] = []
        self._current_context: dict[str, object] = self._context_global

        lines = self._read_file(Path(cue_file), encoding)

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            parts = stripped.split(" ", 1)
            command = parts[0]
            args = parts[1] if len(parts) > 1 else ""
            logger.debug("Command `%s`. Args: %s", command, args)
            method = getattr(self, "cmd_%s" % command.lower(), None)
            if method is not None:
                method(args)
            else:
                logger.warning("Unknown cue command `%s`. Skipping ...", command)

        # Calculate end positions: each track ends where the next begins,
        # but only within the same FILE block. The last track of each file
        # gets None as end position.
        for idx, track_data in enumerate(self._context_tracks):
            track_end_pos = None
            try:
                next_track = self._context_tracks[idx + 1]
                # Only use next track's start if it belongs to the same file
                if next_track.get("FILE") == track_data.get("FILE"):
                    track_end_pos = next_track["POS_START_SAMPLES"]
            except IndexError:
                pass
            track_data["POS_END_SAMPLES"] = track_end_pos

    @staticmethod
    def _read_file(path: Path, encoding: str | None) -> list[str]:
        """Read a cue file with encoding fallback."""
        if encoding is not None:
            try:
                return path.read_text(encoding=encoding).splitlines()
            except (UnicodeDecodeError, LookupError) as e:
                raise CueParseError(f"Cannot read {path} with encoding '{encoding}': {e}") from e

        # Fallback chain: UTF-8 → CP1252 → Latin-1
        # CP1252 is tried before Latin-1 because it's a superset that handles
        # Windows-generated cue files with smart quotes and other extended chars.
        # Latin-1 is last resort as it accepts any byte sequence.
        for enc in ("utf-8", "cp1252", "latin-1"):
            try:
                return path.read_text(encoding=enc).splitlines()
            except UnicodeDecodeError:
                continue

        raise CueParseError(
            f"Cannot read {path}: failed with UTF-8, CP1252, and Latin-1 encodings. "
            "Use --encoding to specify the correct encoding."
        )

    def get_cue_sheet(self) -> CueSheet:
        """Convert parsed data into a CueSheet with CueTrack instances."""
        g = self._context_global
        sheet = CueSheet(
            performer=str(g.get("PERFORMER") or "Unknown"),
            album=str(g.get("ALBUM") or "Unknown"),
            genre=_str_or_none(g.get("GENRE")),
            date=_str_or_none(g.get("DATE")),
            songwriter=_str_or_none(g.get("SONGWRITER")),
            disc_id=_str_or_none(g.get("DISCID")),
            comment=_str_or_none(g.get("COMMENT")),
            file=_str_or_none(g.get("FILE")),
        )

        for td in self._context_tracks:
            track = CueTrack(
                track_num=int(td.get("TRACK_NUM", 0)),
                title=str(td.get("TITLE", "")),
                performer=str(td.get("PERFORMER") or "Unknown"),
                songwriter=_str_or_none(td.get("SONGWRITER")),
                isrc=_str_or_none(td.get("ISRC")),
                index=str(td.get("INDEX", "00:00:00")),
                start_samples=int(td.get("POS_START_SAMPLES", 0)),
                end_samples=_int_or_none(td.get("POS_END_SAMPLES")),
                album=str(td.get("ALBUM") or "Unknown"),
                genre=_str_or_none(td.get("GENRE")),
                date=_str_or_none(td.get("DATE")),
                disc_id=_str_or_none(td.get("DISCID")),
                file=_str_or_none(td.get("FILE")),
            )
            sheet.tracks.append(track)

        return sheet

    def _unquote(self, in_str: str) -> str:
        return in_str.strip(' "')

    def _timestr_to_samples(self, timestr: str) -> int:
        """Convert mm:ss:ff time string to samples at 44100Hz.

        CD audio uses 75 frames per second. Format: MM:SS:FF
        where FF is frames (0-74).
        """
        parts = timestr.split(":")
        if len(parts) != 3:
            logger.warning("Invalid time string '%s', defaulting to 0", timestr)
            return 0
        minutes = int(parts[0])
        seconds = int(parts[1])
        frames = int(parts[2])
        total_seconds = minutes * 60 + seconds
        return total_seconds * CD_SAMPLE_RATE + frames * CD_SAMPLES_PER_FRAME

    def _in_global_context(self) -> bool:
        return self._current_context is self._context_global

    def cmd_rem(self, args: str) -> None:
        parts = args.split(" ", 1)
        if len(parts) < 2:
            return
        subcommand = parts[0].upper()
        subargs = parts[1]
        if subargs.startswith('"'):
            subargs = self._unquote(subargs)
        self._current_context[subcommand] = subargs

    def cmd_performer(self, args: str) -> None:
        self._current_context["PERFORMER"] = self._unquote(args)

    def cmd_title(self, args: str) -> None:
        unquoted = self._unquote(args)
        if self._in_global_context():
            self._current_context["ALBUM"] = unquoted
        else:
            self._current_context["TITLE"] = unquoted

    def cmd_file(self, args: str) -> None:
        # FILE "filename.flac" WAVE
        # FILE always updates the global context so subsequent tracks
        # inherit the correct source file reference.
        filename = self._unquote(args.rsplit(" ", 1)[0])
        self._context_global["FILE"] = filename

    def cmd_index(self, args: str) -> None:
        parts = args.split()
        if len(parts) < 2:
            return
        index_num = int(parts[0])
        timestr = parts[1]
        # Only use INDEX 01 (track start) for split points
        if index_num == 1:
            self._current_context["INDEX"] = timestr
            self._current_context["POS_START_SAMPLES"] = self._timestr_to_samples(timestr)

    def cmd_track(self, args: str) -> None:
        parts = args.split()
        num = int(parts[0])
        new_track_context = deepcopy(self._context_global)
        new_track_context["TRACK_NUM"] = num
        self._context_tracks.append(new_track_context)
        self._current_context = new_track_context

    def cmd_flags(self, args: str) -> None:
        pass

    def cmd_songwriter(self, args: str) -> None:
        self._current_context["SONGWRITER"] = self._unquote(args)

    def cmd_catalog(self, args: str) -> None:
        # UPC/EAN catalog number — store but not mapped to a tag
        pass

    def cmd_cdtextfile(self, args: str) -> None:
        pass

    def cmd_isrc(self, args: str) -> None:
        self._current_context["ISRC"] = self._unquote(args)


def _str_or_none(val: object) -> str | None:
    if val is None:
        return None
    s = str(val)
    return s if s else None


def _int_or_none(val: object) -> int | None:
    if val is None:
        return None
    return int(val)


def sanitize_filename(name: str) -> str:
    """Replace filesystem-unsafe characters in a filename."""
    result = _UNSAFE_FILENAME_CHARS.sub("_", name)
    # Collapse multiple underscores
    result = re.sub(r"_+", "_", result)
    # Strip leading/trailing whitespace and dots
    result = result.strip(" .")
    return result


def parse_cue(path: str | Path, encoding: str | None = None) -> CueSheet:
    """Parse a .cue file and return a CueSheet.

    Args:
        path: Path to the .cue file.
        encoding: Character encoding. If None, tries UTF-8 then Latin-1.

    Returns:
        CueSheet with global metadata and track list.

    Raises:
        CueParseError: If the file cannot be read or parsed.
    """
    parser = CueParser(path, encoding=encoding)
    return parser.get_cue_sheet()
