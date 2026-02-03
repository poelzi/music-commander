"""Mirror releases from the Anomalistic Dark Psy Portal."""

from __future__ import annotations

import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import click

from music_commander.anomalistic.category import (
    CategoryType,
    classify_categories,
    get_release_genres,
    get_release_labels,
)
from music_commander.anomalistic.client import AnomaListicClient
from music_commander.anomalistic.converter import (
    convert_release,
    render_output_path,
    write_meta_json,
)
from music_commander.anomalistic.dedup import check_duplicate, load_local_albums
from music_commander.anomalistic.downloader import (
    discover_audio_files,
    download_archive,
    extract_archive,
)
from music_commander.anomalistic.parser import parse_release_content
from music_commander.cache.models import AnomaListicRelease
from music_commander.cache.session import get_cache_session
from music_commander.cli import pass_context
from music_commander.commands.mirror import EXIT_MIRROR_ERROR, EXIT_SUCCESS, cli
from music_commander.utils.encoder import PRESETS
from music_commander.utils.output import error, info, success, verbose, warning

logger = logging.getLogger(__name__)


@cli.command("anomalistic")
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Re-download all releases, bypassing duplicate detection.",
)
@pass_context
def anomalistic(ctx: object, force: bool) -> None:
    """Mirror releases from the Anomalistic Dark Psy Portal.

    Downloads free releases from darkpsyportal.anomalisticrecords.com,
    converts audio to the configured format (default: FLAC), embeds the
    release URL as a comment tag, and organizes files using the configured
    output pattern.

    By default, previously downloaded releases are skipped. Use --force
    to re-download everything.

    Examples:

        mirror anomalistic

        mirror anomalistic --force
    """
    config = ctx.config  # type: ignore[attr-defined]

    # Resolve output directory
    output_dir = config.anomalistic_output_dir
    if output_dir is None:
        output_dir = config.music_repo / "Anomalistic"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Resolve format preset
    format_name = config.anomalistic_format
    preset = PRESETS.get(format_name)
    if preset is None:
        error(f"Unknown format preset: {format_name}")
        error(f"Available presets: {', '.join(sorted(PRESETS.keys()))}")
        raise SystemExit(EXIT_MIRROR_ERROR)

    source_pref = config.anomalistic_download_source
    output_pattern = config.anomalistic_output_pattern

    # Phase 1: Fetch catalog
    client = AnomaListicClient()

    info("Fetching categories...")
    try:
        raw_categories = client.fetch_categories()
    except Exception as e:
        error(f"Failed to fetch categories: {e}")
        raise SystemExit(EXIT_MIRROR_ERROR)

    categories = classify_categories(raw_categories)
    genre_count = sum(1 for c in categories.values() if c.type == CategoryType.GENRE)
    label_count = sum(1 for c in categories.values() if c.type == CategoryType.LABEL)
    verbose(f"Found {genre_count} genres, {label_count} labels")

    info("Fetching releases...")
    try:
        releases = list(client.iter_releases())
    except Exception as e:
        error(f"Failed to fetch releases: {e}")
        raise SystemExit(EXIT_MIRROR_ERROR)

    info(f"Found {len(releases)} releases")

    # Phase 2: Process each release
    stats = {"downloaded": 0, "skipped": 0, "failed": 0}
    failures: list[str] = []

    try:
        with get_cache_session(config.music_repo) as session:
            # Pre-load local albums for fuzzy matching
            local_albums = load_local_albums(session) if not force else []

            for i, post in enumerate(releases, 1):
                artist = "Unknown"
                album = "Unknown"
                try:
                    parsed = parse_release_content(post)
                    artist = parsed.artist
                    album = parsed.album
                    release_url = post.get("link", "")

                    verbose(f"[{i}/{len(releases)}] {artist} - {album}")

                    # Genre/label classification
                    post_categories = post.get("categories", [])
                    genre_names = get_release_genres(post_categories, categories)
                    label_names = get_release_labels(post_categories, categories)
                    primary_genre = genre_names[0] if genre_names else "Unknown"
                    primary_label = label_names[0] if label_names else ""

                    # Dedup check (unless --force)
                    if not force:
                        dedup = check_duplicate(
                            session,
                            release_url,
                            artist,
                            album,
                            local_albums=local_albums,
                        )
                        if dedup.should_skip:
                            verbose(
                                f"  Skipping: {dedup.reason}"
                                + (f" ({dedup.match_details})" if dedup.match_details else "")
                            )
                            stats["skipped"] += 1
                            continue

                    # Select download URL
                    download_url = parsed.download_urls.get(source_pref)
                    if download_url is None:
                        download_url = next(iter(parsed.download_urls.values()), None)
                    if not download_url:
                        warning(f"  No download URL for {artist} - {album}")
                        stats["failed"] += 1
                        failures.append(f"{artist} - {album}: no download URL")
                        continue

                    # Use temp directory for download and extraction
                    with tempfile.TemporaryDirectory() as tmp_dir:
                        tmp_path = Path(tmp_dir)

                        # Download archive
                        verbose(f"  Downloading: {download_url}")
                        archive_path = download_archive(download_url, tmp_path)

                        # Extract
                        extract_dir = tmp_path / "extracted"
                        extract_archive(archive_path, extract_dir)

                        # Discover audio files
                        audio_files = discover_audio_files(extract_dir)
                        if not audio_files:
                            warning(f"  No audio files found in archive for {artist} - {album}")
                            stats["failed"] += 1
                            failures.append(f"{artist} - {album}: no audio files in archive")
                            continue

                        verbose(f"  Found {len(audio_files)} audio files")

                        # Render output path
                        year = post.get("date", "")[:4]
                        rel_path = render_output_path(
                            output_pattern,
                            genre=primary_genre,
                            label=primary_label,
                            artist=artist,
                            album=album,
                            year=year,
                        )
                        final_dir = output_dir / rel_path
                        final_dir.mkdir(parents=True, exist_ok=True)

                        # Convert
                        converted = convert_release(
                            audio_files,
                            final_dir,
                            preset,
                            release_url,
                            cover_art_url=parsed.cover_art_url,
                            extract_dir=extract_dir,
                        )

                        if not converted:
                            warning(f"  All conversions failed for {artist} - {album}")
                            stats["failed"] += 1
                            failures.append(f"{artist} - {album}: conversion failed")
                            continue

                        # Write meta.json
                        tracks_meta = [
                            {
                                "number": t.number,
                                "title": t.title,
                                "artist": t.artist,
                                "bpm": t.bpm,
                            }
                            for t in parsed.tracklist
                        ]
                        write_meta_json(
                            final_dir,
                            artist=artist,
                            album=album,
                            release_url=release_url,
                            genres=genre_names,
                            labels=label_names,
                            release_date=parsed.release_date,
                            cover_art_url=parsed.cover_art_url,
                            credits=parsed.credits,
                            download_source=source_pref,
                            download_url=download_url,
                            tracks=tracks_meta,
                        )

                    # Update cache
                    now = datetime.now(timezone.utc).isoformat()
                    existing = (
                        session.query(AnomaListicRelease)
                        .filter(AnomaListicRelease.post_id == post.get("id"))
                        .first()
                    )
                    if existing:
                        existing.download_status = "downloaded"
                        existing.output_path = str(final_dir)
                        existing.last_synced = now
                    else:
                        session.add(
                            AnomaListicRelease(
                                post_id=post.get("id", 0),
                                artist=artist,
                                album_title=album,
                                release_url=release_url,
                                download_url_wav=parsed.download_urls.get("wav"),
                                download_url_mp3=parsed.download_urls.get("mp3"),
                                genres=", ".join(genre_names),
                                labels=", ".join(label_names),
                                release_date=parsed.release_date,
                                cover_art_url=parsed.cover_art_url,
                                credits=parsed.credits,
                                download_status="downloaded",
                                output_path=str(final_dir),
                                last_synced=now,
                            )
                        )
                    session.commit()

                    stats["downloaded"] += 1
                    success(f"  Downloaded: {artist} - {album} ({len(converted)} tracks)")

                except KeyboardInterrupt:
                    warning(f"\nInterrupted during: {artist} - {album}")
                    raise
                except Exception as e:
                    logger.exception("Failed to process release: %s - %s", artist, album)
                    error(f"  Failed: {artist} - {album}: {e}")
                    stats["failed"] += 1
                    failures.append(f"{artist} - {album}: {e}")
                    continue

    except KeyboardInterrupt:
        warning("\nMirror interrupted by user")

    # Phase 3: Summary
    info("")
    info("Mirror complete:")
    info(f"  Downloaded: {stats['downloaded']}")
    info(f"  Skipped:    {stats['skipped']}")
    info(f"  Failed:     {stats['failed']}")

    if failures:
        info("")
        info("Failures:")
        for f in failures:
            info(f"  - {f}")

    if stats["failed"] > 0:
        raise SystemExit(EXIT_MIRROR_ERROR)
    raise SystemExit(EXIT_SUCCESS)
