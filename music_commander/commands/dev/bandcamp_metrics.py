"""Bandcamp match metrics viewer for CI and development analysis."""

from __future__ import annotations

import json
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from music_commander.cli import pass_context
from music_commander.commands.dev import cli as dev_cli
from music_commander.utils.output import error, info

METRICS_FILENAME = ".music-commander/match-metrics.jsonl"


@dev_cli.group("bandcamp-metrics")
def cli() -> None:
    """View and compare bandcamp match metrics.

    Metrics are recorded by running 'bandcamp match --record-metrics'.
    """
    pass


def _load_metrics(repo_path: Path) -> list[dict]:
    """Load all metrics entries from the JSONL file."""
    metrics_file = repo_path / METRICS_FILENAME
    if not metrics_file.exists():
        return []
    entries = []
    for line in metrics_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            entries.append(json.loads(line))
    return entries


@cli.command("show")
@click.option("--last", "-n", "last_n", type=int, default=20, help="Show last N entries.")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["table", "json", "csv"]),
    default="table",
    help="Output format.",
)
@pass_context
def show(ctx: object, last_n: int, fmt: str) -> None:
    """Display historical match metrics."""
    config = ctx.config  # type: ignore[attr-defined]
    entries = _load_metrics(config.music_repo)

    if not entries:
        error(f"No metrics found. Run 'bandcamp match --record-metrics' first.")
        return

    entries = entries[-last_n:]

    if fmt == "json":
        click.echo(json.dumps(entries, indent=2))
        return

    if fmt == "csv":
        keys = [
            "timestamp",
            "git_commit",
            "total_releases",
            "total_matched",
            "match_rate",
            "matched_comment",
            "matched_folder",
            "matched_global",
            "tier_exact",
            "tier_high",
            "tier_low",
            "unmatched",
            "threshold",
        ]
        click.echo(",".join(keys))
        for e in entries:
            click.echo(",".join(str(e.get(k, "")) for k in keys))
        return

    # Table format
    console = Console()
    table = Table(title=f"Bandcamp Match Metrics (last {len(entries)})")
    table.add_column("Timestamp", style="dim")
    table.add_column("Commit", style="cyan")
    table.add_column("Total", justify="right")
    table.add_column("Matched", justify="right", style="green")
    table.add_column("Rate", justify="right")
    table.add_column("Comment", justify="right")
    table.add_column("Folder", justify="right")
    table.add_column("Global", justify="right")
    table.add_column("Exact", justify="right", style="green")
    table.add_column("High", justify="right", style="yellow")
    table.add_column("Low", justify="right", style="orange3")
    table.add_column("Unmatched", justify="right", style="red")

    for e in entries:
        ts = e.get("timestamp", "")[:19].replace("T", " ")
        rate = e.get("match_rate", 0)
        table.add_row(
            ts,
            str(e.get("git_commit", "")),
            str(e.get("total_releases", "")),
            str(e.get("total_matched", "")),
            f"{rate:.1%}",
            str(e.get("matched_comment", "")),
            str(e.get("matched_folder", "")),
            str(e.get("matched_global", "")),
            str(e.get("tier_exact", "")),
            str(e.get("tier_high", "")),
            str(e.get("tier_low", "")),
            str(e.get("unmatched", "")),
        )

    console.print(table)


@cli.command("diff")
@pass_context
def diff(ctx: object) -> None:
    """Compare the last two metric entries and highlight changes."""
    config = ctx.config  # type: ignore[attr-defined]
    entries = _load_metrics(config.music_repo)

    if len(entries) < 2:
        error(
            "Need at least 2 metric entries to diff. Run 'bandcamp match --record-metrics' again."
        )
        return

    old, new = entries[-2], entries[-1]
    console = Console()

    console.print(
        f"\n[bold]Comparing:[/bold] {old.get('git_commit', '?')} "
        f"({old.get('timestamp', '')[:19]}) -> "
        f"{new.get('git_commit', '?')} ({new.get('timestamp', '')[:19]})\n"
    )

    fields = [
        ("Total Releases", "total_releases"),
        ("Total Matched", "total_matched"),
        ("Match Rate", "match_rate"),
        ("Comment", "matched_comment"),
        ("Folder", "matched_folder"),
        ("Global", "matched_global"),
        ("Exact", "tier_exact"),
        ("High", "tier_high"),
        ("Low", "tier_low"),
        ("Unmatched", "unmatched"),
    ]

    for label, key in fields:
        old_val = old.get(key, 0)
        new_val = new.get(key, 0)
        if key == "match_rate":
            old_str = f"{old_val:.1%}"
            new_str = f"{new_val:.1%}"
            delta = new_val - old_val
            delta_str = f"{delta:+.1%}"
        else:
            old_str = str(old_val)
            new_str = str(new_val)
            delta = new_val - old_val
            delta_str = f"{delta:+d}"

        if delta > 0:
            color = "green"
        elif delta < 0:
            color = "red"
        else:
            color = "dim"

        # For "unmatched", reverse the color logic (fewer is better)
        if key == "unmatched":
            if delta < 0:
                color = "green"
            elif delta > 0:
                color = "red"

        console.print(
            f"  {label:>16s}: {old_str:>8s} -> {new_str:>8s}  [{color}]{delta_str}[/{color}]"
        )

    console.print()
