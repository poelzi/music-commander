"""CLI integration tests for view command."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from music_commander.cache.models import CacheBase, CacheState, CacheTrack, TrackCrate
from music_commander.cli import Context
from music_commander.commands.view import cli


def _create_mock_session() -> Session:
    """Create an in-memory session with test data."""
    engine = create_engine("sqlite:///:memory:")
    CacheBase.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    # Create FTS5 table
    session.execute(
        text("""
        CREATE VIRTUAL TABLE IF NOT EXISTS tracks_fts USING fts5(
            key, artist, title, album, genre, file
        )
    """)
    )

    session.add(
        CacheTrack(
            key="k1",
            file="darkpsy/Track.mp3",
            artist="TestArtist",
            title="TestTitle",
            album="TestAlbum",
            genre="Darkpsy",
            bpm=148.0,
            rating=5,
            key_musical="Am",
        )
    )
    session.add(
        CacheTrack(
            key="k2",
            file="ambient/Calm.mp3",
            artist="AmbientArtist",
            title="CalmTitle",
            album="CalmAlbum",
            genre="Ambient",
            bpm=80.0,
            rating=3,
            key_musical="C",
        )
    )
    session.add(CacheState(id=1, annex_branch_commit="abc123", track_count=2))
    session.commit()

    session.execute(
        text("""
        INSERT INTO tracks_fts(key, artist, title, album, genre, file)
        SELECT key, artist, title, album, genre, file FROM tracks
    """)
    )
    session.commit()

    return session


def _make_ctx(tmp_path: Path) -> Context:
    """Create a real Context with a mock config."""
    ctx = Context()
    mock_config = MagicMock()
    mock_config.music_repo = tmp_path
    ctx.config = mock_config
    return ctx


@contextmanager
def _fake_cache_session(session: Session):
    """A fake context manager that yields the pre-built session."""
    yield session


class TestViewCLI:
    @patch("music_commander.commands.view.get_cache_session")
    @patch("music_commander.commands.view.refresh_cache")
    def test_basic_view(self, mock_refresh, mock_get_session, tmp_path: Path) -> None:
        session = _create_mock_session()
        mock_get_session.return_value = _fake_cache_session(session)
        mock_refresh.return_value = None

        # Create fake source files so symlinks have targets
        (tmp_path / "darkpsy").mkdir()
        (tmp_path / "darkpsy" / "Track.mp3").touch()

        output_dir = tmp_path / "views"

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "artist:TestArtist",
                "--pattern",
                "{{ artist }} - {{ title }}",
                "--output",
                str(output_dir),
            ],
            obj=_make_ctx(tmp_path),
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "Created 1 symlinks" in result.output
        # Verify symlink exists
        expected = output_dir / "TestArtist - TestTitle.mp3"
        assert expected.is_symlink()

    @patch("music_commander.commands.view.get_cache_session")
    @patch("music_commander.commands.view.refresh_cache")
    def test_no_results(self, mock_refresh, mock_get_session, tmp_path: Path) -> None:
        session = _create_mock_session()
        mock_get_session.return_value = _fake_cache_session(session)
        mock_refresh.return_value = None

        output_dir = tmp_path / "views"

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "artist:NonExistent",
                "--pattern",
                "{{ artist }} - {{ title }}",
                "--output",
                str(output_dir),
            ],
            obj=_make_ctx(tmp_path),
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "No results" in result.output

    @patch("music_commander.commands.view.get_cache_session")
    @patch("music_commander.commands.view.refresh_cache")
    def test_invalid_template(self, mock_refresh, mock_get_session, tmp_path: Path) -> None:
        session = _create_mock_session()
        mock_get_session.return_value = _fake_cache_session(session)
        mock_refresh.return_value = None

        output_dir = tmp_path / "views"

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "artist:TestArtist",
                "--pattern",
                "{{ unclosed",
                "--output",
                str(output_dir),
            ],
            obj=_make_ctx(tmp_path),
            catch_exceptions=False,
        )
        assert result.exit_code == 2  # EXIT_TEMPLATE_ERROR

    @patch("music_commander.commands.view.get_cache_session")
    @patch("music_commander.commands.view.refresh_cache")
    def test_directory_structure(self, mock_refresh, mock_get_session, tmp_path: Path) -> None:
        session = _create_mock_session()
        mock_get_session.return_value = _fake_cache_session(session)
        mock_refresh.return_value = None

        # Create fake source files
        (tmp_path / "darkpsy").mkdir()
        (tmp_path / "darkpsy" / "Track.mp3").touch()
        (tmp_path / "ambient").mkdir()
        (tmp_path / "ambient" / "Calm.mp3").touch()

        output_dir = tmp_path / "views"

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "genre:Darkpsy",
                "OR",
                "genre:Ambient",
                "--pattern",
                "{{ genre }}/{{ artist }} - {{ title }}",
                "--output",
                str(output_dir),
            ],
            obj=_make_ctx(tmp_path),
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "Created 2 symlinks" in result.output
        assert (output_dir / "Darkpsy" / "TestArtist - TestTitle.mp3").is_symlink()
        assert (output_dir / "Ambient" / "AmbientArtist - CalmTitle.mp3").is_symlink()
