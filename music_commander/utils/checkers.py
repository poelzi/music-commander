"""Audio file integrity checking utilities.

This module provides tools for checking audio file integrity using format-specific
checkers (flac, mp3val, ogginfo, shntool, sox) with ffmpeg as a fallback.
"""

import json
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from music_commander.utils.output import verbose


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
    status: str  # "ok" | "error" | "not_present" | "checker_missing"
    tools: list[str]
    errors: list[ToolResult]


@dataclass
class CheckReport:
    """Complete integrity check report."""

    version: int  # Always 1
    timestamp: str  # ISO 8601
    duration_seconds: float
    repository: str
    arguments: list[str]
    summary: dict  # {total, ok, error, not_present, checker_missing}
    results: list[CheckResult]


@dataclass
class CheckerSpec:
    """Specification for a file checker tool."""

    name: str
    command: list[str]
    parse_fn: Callable[[subprocess.CompletedProcess], ToolResult]
    file_arg_position: str = "append"  # "append" | "middle"
    file_arg_index: int | None = None  # For middle insertion


# Cache for tool availability checks
_tool_cache: dict[str, bool] = {}


def check_tool_available(tool_name: str) -> bool:
    """Check if a tool is available on PATH, with caching."""
    if tool_name not in _tool_cache:
        _tool_cache[tool_name] = shutil.which(tool_name) is not None
    return _tool_cache[tool_name]


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

    Output format:
    length   expanded size   cdr  WAVE problems  fmt   ratio  filename
    ---
      5:30.00  35820000  -  -  -  fmt16  1.000  test.wav

    The problems field is the 5th column (index 4).
    """
    output = proc.stdout
    lines = output.splitlines()

    has_problems = False
    for line in lines:
        # Skip header and separator lines
        if "problems" in line.lower() or line.strip() == "---" or not line.strip():
            continue

        # Data line - split by whitespace
        parts = line.split()
        # Format: length, expanded_size, cdr, WAVE, problems, fmt, ratio, filename
        # Need at least 8 parts for valid data line
        if len(parts) >= 5:
            # Problems field is 5th column (index 4)
            problems_field = parts[4]
            # If problems field is NOT just "-", we have problems
            # Valid problem indicators: t, j, i, a, h
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


# Checker registry: maps file extensions to checker specifications
CHECKER_REGISTRY: dict[str, list[CheckerSpec]] = {
    ".flac": [
        CheckerSpec(
            name="flac",
            command=["flac", "-t", "-s", "-w"],
            parse_fn=_parse_flac_result,
        ),
    ],
    ".mp3": [
        CheckerSpec(
            name="mp3val",
            command=["mp3val"],
            parse_fn=_parse_mp3val_result,
        ),
        CheckerSpec(
            name="ffmpeg",
            command=["ffmpeg", "-v", "error", "-i"],
            parse_fn=_parse_ffmpeg_result,
            file_arg_position="middle",
            file_arg_index=4,  # After -i
        ),
    ],
    ".ogg": [
        CheckerSpec(
            name="ogginfo",
            command=["ogginfo"],
            parse_fn=_parse_ogginfo_result,
        ),
        CheckerSpec(
            name="ffmpeg",
            command=["ffmpeg", "-v", "error", "-i"],
            parse_fn=_parse_ffmpeg_result,
            file_arg_position="middle",
            file_arg_index=4,
        ),
    ],
    ".wav": [
        CheckerSpec(
            name="shntool",
            command=["shntool", "len"],
            parse_fn=_parse_shntool_result,
        ),
        CheckerSpec(
            name="sox",
            command=["sox"],
            parse_fn=_parse_sox_result,
            file_arg_position="middle",
            file_arg_index=1,
        ),
    ],
    ".aiff": [
        CheckerSpec(
            name="sox",
            command=["sox"],
            parse_fn=_parse_sox_result,
            file_arg_position="middle",
            file_arg_index=1,
        ),
    ],
    ".aif": [
        CheckerSpec(
            name="sox",
            command=["sox"],
            parse_fn=_parse_sox_result,
            file_arg_position="middle",
            file_arg_index=1,
        ),
    ],
    ".m4a": [
        CheckerSpec(
            name="ffmpeg",
            command=["ffmpeg", "-v", "error", "-i"],
            parse_fn=_parse_ffmpeg_result,
            file_arg_position="middle",
            file_arg_index=4,
        ),
    ],
}

# Ffmpeg fallback for unknown extensions
FFMPEG_FALLBACK = CheckerSpec(
    name="ffmpeg",
    command=["ffmpeg", "-v", "error", "-i"],
    parse_fn=_parse_ffmpeg_result,
    file_arg_position="middle",
    file_arg_index=4,
)


def get_checkers_for_extension(extension: str) -> list[CheckerSpec]:
    """Return checker specs for a file extension.

    Falls back to ffmpeg when extension is not registered.
    """
    return CHECKER_REGISTRY.get(extension.lower(), [FFMPEG_FALLBACK])


def check_file(file_path: Path, repo_path: Path, *, verbose_output: bool = False) -> CheckResult:
    """Check a single audio file for integrity issues.

    Args:
        file_path: Absolute path to the file to check
        repo_path: Repository root path (for relative path calculation)

    Returns:
        CheckResult with status and any errors found
    """
    # Calculate relative path for reporting
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

    # Get file extension and look up checkers
    ext = file_path.suffix.lower()
    checker_specs = get_checkers_for_extension(ext)

    tools_used = []
    all_results = []
    failed_results = []

    missing_tools = []

    for spec in checker_specs:
        # Check if tool is available
        tool_name = spec.command[0]
        if not check_tool_available(tool_name):
            missing_tools.append(tool_name)
            continue

        # Build command with file path
        if spec.file_arg_position == "append":
            cmd = spec.command + [str(file_path)]
        elif spec.file_arg_position == "middle":
            cmd = spec.command.copy()
            if spec.file_arg_index is None:
                raise ValueError("file_arg_index required for middle insertion")
            cmd.insert(spec.file_arg_index, str(file_path))
            # For ffmpeg and sox, add trailing arguments
            if spec.name == "ffmpeg":
                cmd.extend(["-f", "null", "-"])
            elif spec.name == "sox":
                cmd.extend(["-n", "stat"])
        else:
            cmd = spec.command + [str(file_path)]

        # Run the checker
        if verbose_output:
            verbose(f"Running checker: {' '.join(cmd)}")

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=repo_path,
                timeout=300,  # 5 minute timeout
            )
            if verbose_output:
                output_text = f"{getattr(proc, 'stdout', '') or ''}{getattr(proc, 'stderr', '') or ''}".rstrip()
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
            # Treat timeout as a failure
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
            # Treat any other exception as a failure
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

    # Determine overall status
    if failed_results:
        status = "error"
    else:
        status = "ok"

    return CheckResult(
        file=rel_path,
        status=status,
        tools=tools_used,
        errors=failed_results,
    )


def write_report(report: CheckReport, output_path: Path) -> None:
    """Write a CheckReport to JSON file atomically.

    Args:
        report: The report to write
        output_path: Path to write the JSON file
    """
    # Convert dataclasses to dict
    report_dict = asdict(report)

    # Write atomically via temp file + rename
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
            # Clean up temp file on error
            if tmp_path.exists():
                tmp_path.unlink()
            raise
