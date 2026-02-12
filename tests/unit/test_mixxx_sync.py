"""Unit tests for Mixxx sync batching behavior."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from music_commander.commands import mixxx as mixxx_command
from music_commander.config import Config
from music_commander.db.models import SyncState, TrackMetadata


@contextmanager
def _fake_session() -> Generator[object]:
    yield object()


def _make_track(repo_path: Path, index: int) -> TrackMetadata:
    relative_path = Path("music") / f"track-{index}.flac"
    full_path = repo_path / relative_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_bytes(b"audio-data")

    return TrackMetadata(
        file_path=full_path,
        relative_path=relative_path,
        rating=5,
        bpm=145.0,
        color=None,
        key="Am",
        artist="Artist",
        title=f"Track {index}",
        album="Album",
        genre="Darkpsy",
        year="2026",
        tracknumber=str(index),
        comment=None,
        crates=[],
    )


def test_sync_tracks_commits_every_batch_size(temp_dir: Path) -> None:
    """Intermediate commit should run every N successful syncs."""
    repo_path = temp_dir / "repo"
    repo_path.mkdir()
    config = Config(
        mixxx_db=temp_dir / "mixxxdb.sqlite",
        music_repo=repo_path,
        colored_output=False,
    )
    tracks = [_make_track(repo_path, i) for i in range(1, 5)]

    fixed_now = datetime(2026, 2, 11, 12, 0, tzinfo=UTC)
    initial_state = SyncState(last_sync_timestamp=fixed_now, tracks_synced=10)

    batch = MagicMock()
    batch.__enter__.return_value = batch
    batch.__exit__.return_value = False
    batch.set_metadata.return_value = True

    with (
        patch(
            "music_commander.commands.mixxx.get_session",
            side_effect=lambda _mixxx_db: _fake_session(),
        ),
        patch("music_commander.commands.mixxx.get_all_tracks", return_value=tracks),
        patch("music_commander.commands.mixxx.read_sync_state", return_value=initial_state),
        patch("music_commander.commands.mixxx.write_sync_state") as write_sync_state_mock,
        patch(
            "music_commander.commands.mixxx.build_annex_fields",
            return_value={"artist": ["Artist"]},
        ),
        patch("music_commander.commands.mixxx.print_sync_summary"),
        patch("music_commander.commands.mixxx.track", side_effect=lambda items, **_kwargs: items),
        patch("music_commander.commands.mixxx.AnnexMetadataBatch", return_value=batch),
        patch("music_commander.commands.mixxx.now_utc", return_value=fixed_now),
    ):
        result = mixxx_command.sync_tracks(config, sync_all=True, batch_size=2)

    assert len(result.synced) == 4
    assert result.failed == []
    assert result.skipped == []
    assert batch.set_metadata.call_count == 4
    assert batch.commit.call_count == 2

    write_sync_state_mock.assert_called_once()
    assert write_sync_state_mock.call_args.args[0] == repo_path
    persisted_state = write_sync_state_mock.call_args.args[1]
    assert persisted_state.last_sync_timestamp == fixed_now
    assert persisted_state.tracks_synced == 14
