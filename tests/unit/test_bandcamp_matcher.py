"""Unit tests for Bandcamp matcher singles detection and helpers."""

from __future__ import annotations

from collections import defaultdict

from music_commander.bandcamp.matcher import (
    _match_single_file,
    _phase_comment,
    _phase_global,
    extract_folder,
    normalize_for_matching,
)
from music_commander.cache.models import BandcampRelease, BandcampTrack, CacheTrack


def _make_release(
    sale_item_id: int = 1,
    band_name: str = "TestArtist",
    album_title: str = "TestAlbum",
    bandcamp_url: str = "https://testartist.bandcamp.com/album/testalbum",
    sale_item_type: str = "p",
) -> BandcampRelease:
    r = BandcampRelease()
    r.sale_item_id = sale_item_id
    r.band_name = band_name
    r.album_title = album_title
    r.bandcamp_url = bandcamp_url
    r.sale_item_type = sale_item_type
    return r


def _make_track(
    key: str,
    file: str,
    title: str | None = None,
    album: str | None = None,
    comment: str | None = None,
) -> CacheTrack:
    t = CacheTrack(key=key, file=file)
    t.title = title
    t.album = album
    t.comment = comment
    return t


def _make_bc_track(release_id: int, title: str, track_num: int = 1) -> BandcampTrack:
    t = BandcampTrack()
    t.release_id = release_id
    t.title = title
    t.track_number = track_num
    t.duration_seconds = 180.0
    return t


def _build_comment_index(tracks: list[CacheTrack]) -> dict[str, list[CacheTrack]]:
    """Build subdomain -> tracks index from comment tags."""
    import re

    idx: dict[str, list[CacheTrack]] = defaultdict(list)
    for t in tracks:
        if t.comment:
            m = re.search(r"https?://([\w-]+)\.bandcamp\.com", t.comment)
            if m:
                idx[m.group(1).lower()].append(t)
    return idx


def _build_folder_to_tracks(tracks: list[CacheTrack]) -> dict[str, list[CacheTrack]]:
    idx: dict[str, list[CacheTrack]] = defaultdict(list)
    for t in tracks:
        if t.file:
            folder = extract_folder(t.file)
            if folder:
                idx[folder].append(t)
    return idx


def _build_all_tracks_by_key(tracks: list[CacheTrack]) -> dict[str, CacheTrack]:
    return {t.key: t for t in tracks}


class TestSinglesDetectionByTrackCount:
    """Singles detection in _phase_comment uses BandcampTrack count."""

    def test_single_track_release_in_multi_file_folder_uses_file_match(self) -> None:
        """Release with 1 BC track in a multi-file folder -> file-level match."""
        release = _make_release(
            sale_item_id=100,
            band_name="IndacoRuna",
            album_title="MoonChild",
            bandcamp_url="https://indacoruna.bandcamp.com/track/moonchild",
        )

        # Multi-file folder with the matching file
        tracks = [
            _make_track(
                "k1",
                "Goa/IndacoRuna/MoonChild.flac",
                title="MoonChild",
                comment="Visit https://indacoruna.bandcamp.com",
            ),
            _make_track(
                "k2",
                "Goa/IndacoRuna/SunRise.flac",
                title="SunRise",
                comment="Visit https://indacoruna.bandcamp.com",
            ),
            _make_track(
                "k3",
                "Goa/IndacoRuna/NightFall.flac",
                title="NightFall",
                comment="Visit https://indacoruna.bandcamp.com",
            ),
        ]

        bc_tracks_by_release = {
            100: [_make_bc_track(100, "MoonChild")],  # 1 track = single
        }

        comment_index = _build_comment_index(tracks)
        folder_to_tracks = _build_folder_to_tracks(tracks)
        all_by_key = _build_all_tracks_by_key(tracks)

        matched, matched_ids, claimed_folders, claimed_files = _phase_comment(
            [release],
            bc_tracks_by_release,
            comment_index,
            folder_to_tracks,
            all_by_key,
            threshold=60,
        )

        assert len(matched) == 1
        assert matched[0].bc_sale_item_id == 100
        # File-level match: should claim a single file, not the folder
        assert len(claimed_files) == 1
        assert "Goa/IndacoRuna" not in claimed_folders

    def test_multi_track_release_in_multi_file_folder_uses_folder_match(self) -> None:
        """Release with 2+ BC tracks in a multi-file folder -> folder-level match."""
        release = _make_release(
            sale_item_id=200,
            band_name="TestArtist",
            album_title="Full Album",
            bandcamp_url="https://testartist.bandcamp.com/album/full-album",
        )

        tracks = [
            _make_track(
                "k1",
                "Goa/TestArtist/Full Album/01-Track1.flac",
                title="Track1",
                comment="Visit https://testartist.bandcamp.com",
            ),
            _make_track(
                "k2",
                "Goa/TestArtist/Full Album/02-Track2.flac",
                title="Track2",
                comment="Visit https://testartist.bandcamp.com",
            ),
            _make_track(
                "k3",
                "Goa/TestArtist/Full Album/03-Track3.flac",
                title="Track3",
                comment="Visit https://testartist.bandcamp.com",
            ),
        ]

        bc_tracks_by_release = {
            200: [
                _make_bc_track(200, "Track1", 1),
                _make_bc_track(200, "Track2", 2),
                _make_bc_track(200, "Track3", 3),
            ],
        }

        comment_index = _build_comment_index(tracks)
        folder_to_tracks = _build_folder_to_tracks(tracks)
        all_by_key = _build_all_tracks_by_key(tracks)

        matched, matched_ids, claimed_folders, claimed_files = _phase_comment(
            [release],
            bc_tracks_by_release,
            comment_index,
            folder_to_tracks,
            all_by_key,
            threshold=60,
        )

        assert len(matched) == 1
        assert matched[0].bc_sale_item_id == 200
        # Folder-level match: should claim the folder
        assert "Goa/TestArtist/Full Album" in claimed_folders

    def test_zero_bc_tracks_falls_through_to_folder_match(self) -> None:
        """Release with 0 BC tracks (missing data) -> folder-level match, not single."""
        release = _make_release(
            sale_item_id=300,
            band_name="TestArtist",
            album_title="Unknown Album",
            bandcamp_url="https://testartist.bandcamp.com/album/unknown-album",
        )

        tracks = [
            _make_track(
                "k1",
                "Goa/TestArtist/Unknown Album/01-Track.flac",
                title="Track",
                comment="Visit https://testartist.bandcamp.com",
            ),
            _make_track(
                "k2",
                "Goa/TestArtist/Unknown Album/02-Other.flac",
                title="Other",
                comment="Visit https://testartist.bandcamp.com",
            ),
        ]

        bc_tracks_by_release: dict[int, list[BandcampTrack]] = {}  # empty = missing data

        comment_index = _build_comment_index(tracks)
        folder_to_tracks = _build_folder_to_tracks(tracks)
        all_by_key = _build_all_tracks_by_key(tracks)

        matched, matched_ids, claimed_folders, claimed_files = _phase_comment(
            [release],
            bc_tracks_by_release,
            comment_index,
            folder_to_tracks,
            all_by_key,
            threshold=60,
        )

        assert len(matched) == 1
        # Folder-level match (safe fallback, not file-level)
        assert "Goa/TestArtist/Unknown Album" in claimed_folders

    def test_single_track_in_single_file_folder_claims_folder(self) -> None:
        """Release with 1 BC track in a single-file folder -> folder claim (not file-level)."""
        release = _make_release(
            sale_item_id=400,
            band_name="SoloArtist",
            album_title="OnlySingle",
            bandcamp_url="https://soloartist.bandcamp.com/track/onlysingle",
        )

        tracks = [
            _make_track(
                "k1",
                "Goa/SoloArtist/OnlySingle/01-OnlySingle.flac",
                title="OnlySingle",
                comment="Visit https://soloartist.bandcamp.com",
            ),
        ]

        bc_tracks_by_release = {
            400: [_make_bc_track(400, "OnlySingle")],
        }

        comment_index = _build_comment_index(tracks)
        folder_to_tracks = _build_folder_to_tracks(tracks)
        all_by_key = _build_all_tracks_by_key(tracks)

        matched, matched_ids, claimed_folders, claimed_files = _phase_comment(
            [release],
            bc_tracks_by_release,
            comment_index,
            folder_to_tracks,
            all_by_key,
            threshold=60,
        )

        assert len(matched) == 1
        # Single file in own folder -> folder claim, not file-level single detection
        assert "Goa/SoloArtist/OnlySingle" in claimed_folders


class TestMatchSingleFile:
    """Tests for _match_single_file helper."""

    def test_matches_by_title(self) -> None:
        release = _make_release(album_title="MoonChild")
        tracks = [
            _make_track("k1", "Artist/MoonChild.flac", title="MoonChild"),
            _make_track("k2", "Artist/SunRise.flac", title="SunRise"),
        ]
        claimed: set[str] = set()

        rm = _match_single_file(release, tracks, claimed, 60.0, "test")

        assert rm is not None
        assert rm.tracks[0].local_key == "k1"
        assert "k1" in claimed

    def test_skips_claimed_files(self) -> None:
        release = _make_release(album_title="MoonChild")
        tracks = [
            _make_track("k1", "Artist/MoonChild.flac", title="MoonChild"),
        ]
        claimed: set[str] = {"k1"}

        rm = _match_single_file(release, tracks, claimed, 60.0, "test")

        assert rm is None

    def test_returns_none_below_threshold(self) -> None:
        release = _make_release(album_title="Completely Different Name")
        tracks = [
            _make_track("k1", "Artist/SomeTrack.flac", title="SomeTrack"),
        ]
        claimed: set[str] = set()

        rm = _match_single_file(release, tracks, claimed, 90.0, "test")

        assert rm is None

    def test_matches_by_filename_stem(self) -> None:
        release = _make_release(album_title="NightFall")
        tracks = [
            _make_track("k1", "Artist/NightFall.flac", title=None),  # no title tag
        ]
        claimed: set[str] = set()

        rm = _match_single_file(release, tracks, claimed, 60.0, "test")

        assert rm is not None
        assert rm.tracks[0].local_key == "k1"


class TestCommentFalsePositives:
    """Comment phase should not match releases to wrong folders on the same label."""

    def test_same_label_different_release_no_match(self) -> None:
        """Different artist+album on same label subdomain should not match.

        Real case: Disect - Tentacle matched Somnium - Rocket Science (score=66.7)
        because both were on Kinematic Recordings subdomain.
        """
        release = _make_release(
            sale_item_id=1,
            band_name="Disect",
            album_title="Tentacle",
            bandcamp_url="https://kinematicrecordings.bandcamp.com/album/tentacle",
        )

        # Only folder available is a completely different release on same label
        tracks = [
            _make_track(
                "k1",
                "zenonesque/[Kinematic Recordings]/Somnium - Rocket Science/01.flac",
                title="Track 1",
                comment="Visit https://kinematicrecordings.bandcamp.com",
            ),
            _make_track(
                "k2",
                "zenonesque/[Kinematic Recordings]/Somnium - Rocket Science/02.flac",
                title="Track 2",
                comment="Visit https://kinematicrecordings.bandcamp.com",
            ),
            _make_track(
                "k3",
                "zenonesque/[Kinematic Recordings]/Somnium - Rocket Science/03.flac",
                title="Track 3",
                comment="Visit https://kinematicrecordings.bandcamp.com",
            ),
            _make_track(
                "k4",
                "zenonesque/[Kinematic Recordings]/Somnium - Rocket Science/04.flac",
                title="Track 4",
                comment="Visit https://kinematicrecordings.bandcamp.com",
            ),
        ]

        bc_tracks_by_release: dict[int, list[BandcampTrack]] = {
            1: [_make_bc_track(1, "Tentacle", 1)],
        }

        comment_index = _build_comment_index(tracks)
        folder_to_tracks = _build_folder_to_tracks(tracks)
        all_by_key = _build_all_tracks_by_key(tracks)

        matched, matched_ids, _, _ = _phase_comment(
            [release],
            bc_tracks_by_release,
            comment_index,
            folder_to_tracks,
            all_by_key,
            threshold=60,
        )

        # Should NOT match — album "Tentacle" vs folder "Somnium - Rocket Science"
        # scores ~66.7 which is below the raised threshold of 75
        assert len(matched) == 0

    def test_volume_mismatch_in_comment_phase(self) -> None:
        """Volume II should not match Volume I folder even on same subdomain.

        Real case: Swamp Music - The Swampilation, Volume II matched Volume I (score=98.0)
        """
        release = _make_release(
            sale_item_id=2,
            band_name="Swamp Music",
            album_title="The Swampilation, Volume II",
            bandcamp_url="https://swampmusic.bandcamp.com/album/the-swampilation-volume-ii",
        )

        tracks = [
            _make_track(
                "k1",
                "psydub/[Swamp Music]/The Swampilation Volume I/01.flac",
                title="Track 1",
                comment="Visit https://swampmusic.bandcamp.com",
            ),
            _make_track(
                "k2",
                "psydub/[Swamp Music]/The Swampilation Volume I/02.flac",
                title="Track 2",
                comment="Visit https://swampmusic.bandcamp.com",
            ),
            _make_track(
                "k3",
                "psydub/[Swamp Music]/The Swampilation Volume I/03.flac",
                title="Track 3",
                comment="Visit https://swampmusic.bandcamp.com",
            ),
            _make_track(
                "k4",
                "psydub/[Swamp Music]/The Swampilation Volume I/04.flac",
                title="Track 4",
                comment="Visit https://swampmusic.bandcamp.com",
            ),
        ]

        bc_tracks_by_release: dict[int, list[BandcampTrack]] = {
            2: [
                _make_bc_track(2, "Track A", 1),
                _make_bc_track(2, "Track B", 2),
            ],
        }

        comment_index = _build_comment_index(tracks)
        folder_to_tracks = _build_folder_to_tracks(tracks)
        all_by_key = _build_all_tracks_by_key(tracks)

        matched, matched_ids, _, _ = _phase_comment(
            [release],
            bc_tracks_by_release,
            comment_index,
            folder_to_tracks,
            all_by_key,
            threshold=60,
        )

        # Should NOT match — Volume II vs Volume I
        assert len(matched) == 0

    def test_legitimate_comment_match_still_works(self) -> None:
        """Correct release on same subdomain should still match."""
        release = _make_release(
            sale_item_id=3,
            band_name="Bluetech",
            album_title="Cosmic Dubs",
            bandcamp_url="https://bluetech.bandcamp.com/album/cosmic-dubs",
        )

        tracks = [
            _make_track(
                "k1",
                "psychill/Bluetech/Bluetech - Cosmic Dubs/01.flac",
                title="Track 1",
                comment="Visit https://bluetech.bandcamp.com",
            ),
            _make_track(
                "k2",
                "psychill/Bluetech/Bluetech - Cosmic Dubs/02.flac",
                title="Track 2",
                comment="Visit https://bluetech.bandcamp.com",
            ),
            _make_track(
                "k3",
                "psychill/Bluetech/Bluetech - Cosmic Dubs/03.flac",
                title="Track 3",
                comment="Visit https://bluetech.bandcamp.com",
            ),
        ]

        bc_tracks_by_release: dict[int, list[BandcampTrack]] = {
            3: [
                _make_bc_track(3, "Track 1", 1),
                _make_bc_track(3, "Track 2", 2),
                _make_bc_track(3, "Track 3", 3),
            ],
        }

        comment_index = _build_comment_index(tracks)
        folder_to_tracks = _build_folder_to_tracks(tracks)
        all_by_key = _build_all_tracks_by_key(tracks)

        matched, matched_ids, _, _ = _phase_comment(
            [release],
            bc_tracks_by_release,
            comment_index,
            folder_to_tracks,
            all_by_key,
            threshold=60,
        )

        assert len(matched) == 1
        assert matched[0].bc_sale_item_id == 3


class TestGlobalFalsePositives:
    """Global phase should not match releases with only partial word overlap."""

    def _make_local_track(
        self,
        key: str,
        file: str,
        artist: str,
        album: str,
        title: str,
    ) -> CacheTrack:
        t = CacheTrack(key=key, file=file)
        t.artist = artist
        t.album = album
        t.title = title
        return t

    def test_same_artist_different_album_no_match(self) -> None:
        """Same artist but completely different album should not match.

        Real case: Gumnut - Inside Out matched Gumnut - Nuts and Bolts (score=70.0)
        """
        release = _make_release(
            sale_item_id=1,
            band_name="Gumnut",
            album_title="Inside Out",
            bandcamp_url="https://gumnut.bandcamp.com/album/inside-out",
        )

        # Use realistic track titles that don't coincidentally match
        local_titles = [
            "Ratchet Wrench",
            "Cog Assembly",
            "Bolt Tightening",
            "Nut Cracker",
            "Spring Coil",
        ]
        bc_titles = ["Looking In", "Turning Around", "Flipping Over"]

        local_tracks = [
            self._make_local_track(
                f"k{i}",
                f"zenonesque/Gumnut/Nuts and Bolts/0{i}.flac",
                "Gumnut",
                "Nuts and Bolts",
                local_titles[i - 1],
            )
            for i in range(1, 6)
        ]

        bc_tracks_by_release: dict[int, list[BandcampTrack]] = {
            1: [_make_bc_track(1, title, i) for i, title in enumerate(bc_titles, 1)],
        }

        matched, matched_ids, _, _ = _phase_global(
            [release],
            bc_tracks_by_release,
            local_tracks,
            threshold=75,
        )

        # Should NOT match — "Inside Out" vs "Nuts and Bolts" are unrelated albums
        assert len(matched) == 0

    def test_unrelated_release_word_overlap_no_match(self) -> None:
        """Releases with only incidental word overlap should not match.

        Real case: STEREOTYPE - DEEP STRUCTURES matched Terahert - Digital Structures EP
        (score=68.4) due to "structures" word overlap.
        """
        release = _make_release(
            sale_item_id=2,
            band_name="STEREOTYPE",
            album_title="DEEP STRUCTURES (EP)",
            bandcamp_url="https://stereotype.bandcamp.com/album/deep-structures",
        )

        local_tracks = [
            self._make_local_track(
                "k1",
                "progressive/Terahert/Digital Structures EP/01.flac",
                "Terahert",
                "Digital Structures EP",
                "Binary Code",
            ),
            self._make_local_track(
                "k2",
                "progressive/Terahert/Digital Structures EP/02.flac",
                "Terahert",
                "Digital Structures EP",
                "Quantum Field",
            ),
        ]

        bc_tracks_by_release: dict[int, list[BandcampTrack]] = {
            2: [
                _make_bc_track(2, "Deep Thought", 1),
                _make_bc_track(2, "Foundation Layer", 2),
            ],
        }

        matched, matched_ids, _, _ = _phase_global(
            [release],
            bc_tracks_by_release,
            local_tracks,
            threshold=75,
        )

        # Should NOT match — different artist and only partial album word overlap
        assert len(matched) == 0

    def test_legitimate_global_match_works(self) -> None:
        """Correct artist+album should still match in global phase."""
        release = _make_release(
            sale_item_id=3,
            band_name="Dreamstalker",
            album_title="Sensorial Experience",
            bandcamp_url="https://dreamstalker.bandcamp.com/album/sensorial-experience",
        )

        local_tracks = [
            self._make_local_track(
                f"k{i}",
                f"zenonesque/Dreamstalker/Sensorial Experience/0{i}.flac",
                "Dreamstalker",
                "Sensorial Experience",
                f"Track {i}",
            )
            for i in range(1, 9)
        ]

        bc_tracks_by_release: dict[int, list[BandcampTrack]] = {
            3: [_make_bc_track(3, f"Track {i}", i) for i in range(1, 9)],
        }

        matched, matched_ids, _, _ = _phase_global(
            [release],
            bc_tracks_by_release,
            local_tracks,
            threshold=75,
        )

        assert len(matched) == 1
        assert matched[0].bc_sale_item_id == 3
