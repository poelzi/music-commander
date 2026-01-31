"""Audio file integrity checking utilities.

This module provides tools for checking audio file integrity using format-specific
checkers (flac, mp3val, ogginfo, shntool, sox) with ffmpeg as a fallback for
audio files with unrecognized extensions. Non-audio files are skipped.

File type detection uses extension-based lookup first (fast path), falling back
to MIME type detection via libmagic for unknown extensions.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from music_commander.utils.output import verbose

if TYPE_CHECKING:
    import magic as magic_mod


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ToolResult:
    """Result from running a single checker tool."""

    tool: str
    success: bool
    exit_code: int
    output: str


@dataclass
class CheckResult:
    """Result of checking a single file."""

    file: str  # Relative path from repo root
    status: str  # "ok" | "warning" | "error" | "not_present" | "checker_missing" | "skipped"
    tools: list[str]
    errors: list[ToolResult]
    warnings: list[ToolResult] = field(default_factory=list)


@dataclass
class CheckReport:
    """Complete integrity check report."""

    version: int  # Always 1
    timestamp: str  # ISO 8601
    duration_seconds: float
    repository: str
    arguments: list[str]
    summary: dict  # {total, ok, warning, error, not_present, checker_missing, skipped}
    results: list[CheckResult]


@dataclass
class CheckerSpec:
    """Specification for a file checker tool."""

    name: str
    command: list[str]
    parse_fn: Callable[[subprocess.CompletedProcess], ToolResult]
    file_arg_position: str = "append"  # "append" | "middle"
    file_arg_index: int | None = None  # For middle insertion


@dataclass(frozen=True)
class CheckerGroup:
    """A group of checkers that apply to a set of file types.

    Files are matched by extension first, then by MIME type as fallback.
    """

    extensions: frozenset[str]
    mimetypes: frozenset[str]
    checkers: list[CheckerSpec] = field(default_factory=list)
    internal_validator: str | None = None  # Name of internal validator (e.g. "cue")


# ---------------------------------------------------------------------------
# Tool availability cache
# ---------------------------------------------------------------------------

_tool_cache: dict[str, bool] = {}


def check_tool_available(tool_name: str) -> bool:
    """Check if a tool is available on PATH, with caching."""
    if tool_name not in _tool_cache:
        _tool_cache[tool_name] = shutil.which(tool_name) is not None
    return _tool_cache[tool_name]


# ---------------------------------------------------------------------------
# Tool-specific result parsers
# ---------------------------------------------------------------------------


def _parse_flac_result(proc: subprocess.CompletedProcess) -> ToolResult:
    """Parse flac test result. Success = exit code 0."""
    return ToolResult(
        tool="flac",
        success=proc.returncode == 0,
        exit_code=proc.returncode,
        output=proc.stderr,
    )


def _parse_mp3val_result(proc: subprocess.CompletedProcess) -> ToolResult:
    """Parse mp3val result. Success = no WARNING/PROBLEM lines in stdout.

    mp3val exit code is unreliable (always 0), must parse stdout.
    """
    output = proc.stdout
    has_problems = any(line.startswith(("WARNING", "PROBLEM")) for line in output.splitlines())
    return ToolResult(
        tool="mp3val",
        success=not has_problems,
        exit_code=proc.returncode,
        output=output,
    )


def _parse_ffmpeg_result(proc: subprocess.CompletedProcess) -> ToolResult:
    """Parse ffmpeg result. Success = exit code 0 AND empty stderr."""
    return ToolResult(
        tool="ffmpeg",
        success=proc.returncode == 0 and not proc.stderr.strip(),
        exit_code=proc.returncode,
        output=proc.stderr,
    )


def _parse_shntool_result(proc: subprocess.CompletedProcess) -> ToolResult:
    """Parse shntool len result. Success = all problem indicators are '-'.

    Problem indicators: t (truncated), j (junk), i (inconsistent),
    a (not aligned), h (non-canonical header)
    """
    output = proc.stdout
    lines = output.splitlines()

    has_problems = False
    for line in lines:
        if "problems" in line.lower() or line.strip() == "---" or not line.strip():
            continue

        parts = line.split()
        if len(parts) >= 5:
            problems_field = parts[4]
            if problems_field != "-" and any(c in problems_field for c in "tijah"):
                has_problems = True
                break

    return ToolResult(
        tool="shntool",
        success=not has_problems and proc.returncode == 0,
        exit_code=proc.returncode,
        output=output,
    )


def _parse_sox_result(proc: subprocess.CompletedProcess) -> ToolResult:
    """Parse sox result. Success = exit code 0."""
    return ToolResult(
        tool="sox",
        success=proc.returncode == 0,
        exit_code=proc.returncode,
        output=proc.stderr,
    )


def _parse_ogginfo_result(proc: subprocess.CompletedProcess) -> ToolResult:
    """Parse ogginfo result. Success = exit code 0."""
    return ToolResult(
        tool="ogginfo",
        success=proc.returncode == 0,
        exit_code=proc.returncode,
        output=proc.stdout + proc.stderr,
    )


# ---------------------------------------------------------------------------
# Shared checker spec constants (DRY)
# ---------------------------------------------------------------------------

_FFMPEG_CHECKER = CheckerSpec(
    name="ffmpeg",
    command=["ffmpeg", "-v", "error", "-i"],
    parse_fn=_parse_ffmpeg_result,
    file_arg_position="middle",
    file_arg_index=4,
)

_SOX_CHECKER = CheckerSpec(
    name="sox",
    command=["sox"],
    parse_fn=_parse_sox_result,
    file_arg_position="middle",
    file_arg_index=1,
)

_MP3VAL_CHECKER = CheckerSpec(
    name="mp3val",
    command=["mp3val"],
    parse_fn=_parse_mp3val_result,
)

_OGGINFO_CHECKER = CheckerSpec(
    name="ogginfo",
    command=["ogginfo"],
    parse_fn=_parse_ogginfo_result,
)

_SHNTOOL_CHECKER = CheckerSpec(
    name="shntool",
    command=["shntool", "len"],
    parse_fn=_parse_shntool_result,
)

_FLAC_CHECKER = CheckerSpec(
    name="flac",
    command=["flac", "-t", "-s", "-w"],
    parse_fn=_parse_flac_result,
)

# ---------------------------------------------------------------------------
# Checker group registry
# ---------------------------------------------------------------------------

CHECKER_GROUPS: list[CheckerGroup] = [
    CheckerGroup(
        extensions=frozenset({".flac"}),
        mimetypes=frozenset({"audio/flac", "audio/x-flac"}),
        checkers=[_FLAC_CHECKER],
    ),
    CheckerGroup(
        extensions=frozenset({".mp3"}),
        mimetypes=frozenset({"audio/mpeg", "audio/mp3"}),
        checkers=[_MP3VAL_CHECKER, _FFMPEG_CHECKER],
    ),
    CheckerGroup(
        extensions=frozenset({".ogg", ".oga"}),
        mimetypes=frozenset({"audio/ogg", "audio/x-vorbis+ogg", "audio/x-ogg"}),
        checkers=[_OGGINFO_CHECKER, _FFMPEG_CHECKER],
    ),
    CheckerGroup(
        extensions=frozenset({".wav"}),
        mimetypes=frozenset({"audio/wav", "audio/x-wav", "audio/wave"}),
        checkers=[_SHNTOOL_CHECKER, _SOX_CHECKER],
    ),
    CheckerGroup(
        extensions=frozenset({".aiff", ".aif"}),
        mimetypes=frozenset({"audio/aiff", "audio/x-aiff"}),
        checkers=[_SOX_CHECKER],
    ),
    CheckerGroup(
        extensions=frozenset({".m4a", ".aac"}),
        mimetypes=frozenset({"audio/mp4", "audio/x-m4a", "audio/aac"}),
        checkers=[_FFMPEG_CHECKER],
    ),
    CheckerGroup(
        extensions=frozenset({".opus"}),
        mimetypes=frozenset({"audio/opus", "audio/ogg; codecs=opus"}),
        checkers=[_FFMPEG_CHECKER],
    ),
    CheckerGroup(
        extensions=frozenset({".wma"}),
        mimetypes=frozenset({"audio/x-ms-wma"}),
        checkers=[_FFMPEG_CHECKER],
    ),
    CheckerGroup(
        extensions=frozenset({".cue"}),
        mimetypes=frozenset({"application/x-cuesheet", "text/x-cue"}),
        checkers=[],
        internal_validator="cue",
    ),
]

# Audio fallback: applies to any audio/* MIME type not matched above
AUDIO_FALLBACK_GROUP = CheckerGroup(
    extensions=frozenset(),
    mimetypes=frozenset({"audio/*"}),
    checkers=[_FFMPEG_CHECKER],
)

# ---------------------------------------------------------------------------
# Lookup indexes (built at module load time)
# ---------------------------------------------------------------------------

_EXT_INDEX: dict[str, CheckerGroup] = {}
_MIME_INDEX: dict[str, CheckerGroup] = {}

for _group in CHECKER_GROUPS:
    for _ext in _group.extensions:
        _EXT_INDEX[_ext] = _group
    for _mime in _group.mimetypes:
        _MIME_INDEX[_mime] = _group

# Backward-compat: flat extension -> checkers dict used by some callers
CHECKER_REGISTRY: dict[str, list[CheckerSpec]] = {
    ext: group.checkers for ext, group in _EXT_INDEX.items()
}

# ---------------------------------------------------------------------------
# MIME type detection
# ---------------------------------------------------------------------------

_magic_instance: magic_mod.Magic | None = None


def _detect_mimetype(file_path: Path) -> str | None:
    """Detect MIME type using libmagic. Lazily initializes the Magic instance."""
    global _magic_instance
    if _magic_instance is None:
        import magic

        _magic_instance = magic.Magic(mime=True)
    try:
        return _magic_instance.from_file(str(file_path))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# File -> checker lookup
# ---------------------------------------------------------------------------


def get_checkers_for_file(file_path: Path) -> tuple[CheckerGroup | None, str]:
    """Return (checker_group, status_hint) for a file.

    Lookup order:
    1. Extension match in _EXT_INDEX (fast path, no I/O)
    2. MIME type exact match in _MIME_INDEX via python-magic
    3. MIME type prefix match against audio/* -> AUDIO_FALLBACK_GROUP
    4. Not audio -> return (None, "skipped")

    Returns:
        Tuple of (CheckerGroup or None, status_hint).
        status_hint is "check" if the file should be checked, "skipped" otherwise.
    """
    ext = file_path.suffix.lower()

    # 1. Extension match (fast path)
    if ext in _EXT_INDEX:
        return _EXT_INDEX[ext], "check"

    # 2. MIME detection (only for unknown extensions)
    mimetype = _detect_mimetype(file_path)
    if mimetype:
        # Exact MIME match
        if mimetype in _MIME_INDEX:
            return _MIME_INDEX[mimetype], "check"
        # Wildcard audio/* fallback
        if mimetype.startswith("audio/"):
            return AUDIO_FALLBACK_GROUP, "check"

    # 4. Not a recognized media file
    return None, "skipped"


def get_checkers_for_extension(extension: str) -> list[CheckerSpec]:
    """Return checker specs for a file extension.

    Backward-compatible function. For extension-only lookup (e.g. dry-run display).
    Returns empty list for unknown extensions (no longer falls back to ffmpeg).
    """
    group = _EXT_INDEX.get(extension.lower())
    if group is not None:
        return group.checkers
    return []


# ---------------------------------------------------------------------------
# Internal validators
# ---------------------------------------------------------------------------


def _validate_cue_file(file_path: Path, rel_path: str) -> CheckResult:
    """Validate a .cue sheet file.

    Checks that the file is readable text (UTF-8 or Latin-1) and contains
    the required FILE and TRACK directives.
    """
    text = None
    for encoding in ("utf-8", "latin-1"):
        try:
            text = file_path.read_text(encoding=encoding)
            break
        except UnicodeDecodeError:
            continue

    if text is None:
        return CheckResult(
            file=rel_path,
            status="error",
            tools=["cue-validator"],
            errors=[
                ToolResult(
                    tool="cue-validator",
                    success=False,
                    exit_code=1,
                    output="Cannot decode file as UTF-8 or Latin-1",
                )
            ],
        )

    lines = text.splitlines()
    has_file = any(line.strip().startswith("FILE ") for line in lines)
    has_track = any(line.strip().startswith("TRACK ") for line in lines)

    if not has_file or not has_track:
        missing = []
        if not has_file:
            missing.append("FILE")
        if not has_track:
            missing.append("TRACK")
        return CheckResult(
            file=rel_path,
            status="error",
            tools=["cue-validator"],
            errors=[
                ToolResult(
                    tool="cue-validator",
                    success=False,
                    exit_code=1,
                    output=f"Missing required directives: {', '.join(missing)}",
                )
            ],
        )

    return CheckResult(
        file=rel_path,
        status="ok",
        tools=["cue-validator"],
        errors=[],
    )


_INTERNAL_VALIDATORS: dict[str, Callable[[Path, str], CheckResult]] = {
    "cue": _validate_cue_file,
}


# ---------------------------------------------------------------------------
# Optional post-checks (warnings)
# ---------------------------------------------------------------------------


def _check_flac_multichannel(file_path: Path) -> ToolResult | None:
    """Check if a stereo FLAC file has the WAVEFORMATEXTENSIBLE_CHANNEL_MASK tag.

    Pioneer DJ players have playback issues with stereo FLAC files that carry
    a multichannel bit (WAVEFORMATEXTENSIBLE_CHANNEL_MASK vorbis comment).
    Pure stereo files should not need this tag.

    Returns a warning ToolResult if the issue is detected, None otherwise.
    Requires ``metaflac`` on PATH.
    """
    if not check_tool_available("metaflac"):
        return None

    # 1. Check channel count — only flag stereo files
    try:
        proc_channels = subprocess.run(
            ["metaflac", "--show-channels", str(file_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, Exception):
        return None

    if proc_channels.returncode != 0:
        return None

    try:
        channels = int(proc_channels.stdout.strip())
    except ValueError:
        return None

    if channels != 2:
        return None

    # 2. Check for WAVEFORMATEXTENSIBLE_CHANNEL_MASK tag
    try:
        proc_tag = subprocess.run(
            ["metaflac", "--show-tag=WAVEFORMATEXTENSIBLE_CHANNEL_MASK", str(file_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, Exception):
        return None

    if proc_tag.returncode != 0:
        return None

    mask_output = proc_tag.stdout.strip()
    if not mask_output:
        return None

    # Extract the value after '='
    mask_value = mask_output.split("=", 1)[-1] if "=" in mask_output else mask_output

    return ToolResult(
        tool="flac-multichannel",
        success=True,  # Not a failure, just a warning
        exit_code=0,
        output=(
            f"Stereo file has WAVEFORMATEXTENSIBLE_CHANNEL_MASK={mask_value}. "
            f"This causes playback issues on Pioneer players."
        ),
    )


# ---------------------------------------------------------------------------
# Main check function
# ---------------------------------------------------------------------------


def check_file(
    file_path: Path,
    repo_path: Path,
    *,
    verbose_output: bool = False,
    flac_multichannel_check: bool = False,
) -> CheckResult:
    """Check a single file for integrity issues.

    Uses extension-based lookup first, then MIME type detection for unknown
    extensions. Non-audio files are skipped. Files with internal validators
    (e.g. .cue) use Python-native validation instead of external tools.

    Args:
        file_path: Absolute path to the file to check
        repo_path: Repository root path (for relative path calculation)
        verbose_output: If True, log checker commands and output
        flac_multichannel_check: If True, warn on stereo FLAC files with
            WAVEFORMATEXTENSIBLE_CHANNEL_MASK (Pioneer compatibility issue)

    Returns:
        CheckResult with status and any errors found
    """
    try:
        rel_path = str(file_path.relative_to(repo_path))
    except ValueError:
        rel_path = str(file_path)

    # Check if file exists
    if not file_path.exists():
        return CheckResult(
            file=rel_path,
            status="not_present",
            tools=[],
            errors=[],
        )

    # Look up checkers for this file
    group, status_hint = get_checkers_for_file(file_path)

    if status_hint == "skipped":
        return CheckResult(
            file=rel_path,
            status="skipped",
            tools=[],
            errors=[],
        )

    # Internal validator (e.g. .cue files)
    if group is not None and group.internal_validator:
        validator_fn = _INTERNAL_VALIDATORS.get(group.internal_validator)
        if validator_fn:
            return validator_fn(file_path, rel_path)

    checker_specs = group.checkers if group is not None else []

    tools_used: list[str] = []
    all_results: list[ToolResult] = []
    failed_results: list[ToolResult] = []
    missing_tools: list[str] = []

    for spec in checker_specs:
        tool_name = spec.command[0]
        if not check_tool_available(tool_name):
            missing_tools.append(tool_name)
            continue

        # Build command with file path
        if spec.file_arg_position == "middle":
            cmd = spec.command.copy()
            if spec.file_arg_index is None:
                raise ValueError("file_arg_index required for middle insertion")
            cmd.insert(spec.file_arg_index, str(file_path))
            if spec.name == "ffmpeg":
                cmd.extend(["-f", "null", "-"])
            elif spec.name == "sox":
                cmd.extend(["-n", "stat"])
        else:
            cmd = spec.command + [str(file_path)]

        if verbose_output:
            verbose(f"Running checker: {' '.join(cmd)}")

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=repo_path,
                timeout=600,
            )
            if verbose_output:
                output_text = (
                    f"{getattr(proc, 'stdout', '') or ''}{getattr(proc, 'stderr', '') or ''}"
                ).rstrip()
                if output_text:
                    verbose(f"Output ({spec.name}):\n{output_text}")
                else:
                    verbose(f"Output ({spec.name}): <no output>")

            result = spec.parse_fn(proc)
            tools_used.append(spec.name)
            all_results.append(result)
            if not result.success:
                failed_results.append(result)

        except subprocess.TimeoutExpired:
            result = ToolResult(
                tool=spec.name,
                success=False,
                exit_code=-1,
                output="Checker timed out after 300 seconds",
            )
            tools_used.append(spec.name)
            all_results.append(result)
            failed_results.append(result)
        except Exception as e:
            result = ToolResult(
                tool=spec.name,
                success=False,
                exit_code=-1,
                output=f"Exception running checker: {e}",
            )
            tools_used.append(spec.name)
            all_results.append(result)
            failed_results.append(result)

    if not tools_used and missing_tools:
        return CheckResult(
            file=rel_path,
            status="checker_missing",
            tools=sorted(set(missing_tools)),
            errors=[],
        )

    # Optional post-check warnings (only when integrity checks passed)
    warning_results: list[ToolResult] = []

    if flac_multichannel_check and file_path.suffix.lower() == ".flac" and not failed_results:
        mc_warning = _check_flac_multichannel(file_path)
        if mc_warning is not None:
            warning_results.append(mc_warning)
            if "flac-multichannel" not in tools_used:
                tools_used.append("flac-multichannel")

    # Determine status
    if failed_results:
        status = "error"
    elif warning_results:
        status = "warning"
    else:
        status = "ok"

    return CheckResult(
        file=rel_path,
        status=status,
        tools=tools_used,
        errors=failed_results,
        warnings=warning_results,
    )


# ---------------------------------------------------------------------------
# Report writing
# ---------------------------------------------------------------------------


def write_report(report: CheckReport, output_path: Path) -> None:
    """Write a CheckReport to JSON file atomically."""
    report_dict = asdict(report)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        mode="w",
        dir=output_path.parent,
        prefix=".tmp_",
        suffix=".json",
        delete=False,
    ) as tmp:
        tmp_path = Path(tmp.name)
        try:
            json.dump(report_dict, tmp, indent=2)
            tmp.flush()
            tmp_path.rename(output_path)
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink()
            raise
