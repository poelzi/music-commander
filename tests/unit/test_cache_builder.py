"""Unit tests for cache builder module — pure-logic tests only.

Mock-heavy cache build, FTS5, and refresh tests have been replaced by
real git-annex integration tests in ``tests/integration/``.
"""

from __future__ import annotations

import base64

from music_commander.cache.builder import (
    _decode_value,
    _extract_key_from_path,
    _metadata_to_crates,
    _metadata_to_track,
    parse_metadata_log,
)

# ---------------------------------------------------------------------------
# parse_metadata_log tests
# ---------------------------------------------------------------------------


class TestParseMetadataLog:
    def test_single_field_single_value(self) -> None:
        content = "1769651283s artist +AphexTwin\n"
        result = parse_metadata_log(content)
        assert result == {"artist": ["AphexTwin"]}

    def test_multiple_fields(self) -> None:
        content = "1769651283s artist +Boards of Canada genre +IDM\n"
        # Note: "of" and "Canada" look like values but they lack +/- prefix,
        # so "of" and "Canada" become field names. This matches the real format
        # where multi-word values are base64-encoded.
        # The real format for multi-word artist would be:
        content = "1769651283s artist +!Qm9hcmRzIG9mIENhbmFkYQ== genre +IDM\n"
        result = parse_metadata_log(content)
        assert result["artist"] == ["Boards of Canada"]
        assert result["genre"] == ["IDM"]

    def test_multi_value_field(self) -> None:
        content = "1769651283s genre +Ambient +IDM +Downtempo\n"
        result = parse_metadata_log(content)
        assert result["genre"] == ["Ambient", "Downtempo", "IDM"]

    def test_unset_value(self) -> None:
        content = "1769651283s genre +Ambient +IDM\n1769651284s genre -IDM\n"
        result = parse_metadata_log(content)
        assert result["genre"] == ["Ambient"]

    def test_multiline_replay(self) -> None:
        content = "1769651283s artist +OldArtist\n1769651290s artist -OldArtist +NewArtist\n"
        result = parse_metadata_log(content)
        assert result["artist"] == ["NewArtist"]

    def test_base64_value(self) -> None:
        # "Hello World" base64-encoded
        encoded = base64.b64encode(b"Hello World").decode()
        content = f"1769651283s title +!{encoded}\n"
        result = parse_metadata_log(content)
        assert result["title"] == ["Hello World"]

    def test_base64_with_special_chars(self) -> None:
        # Value with spaces and special characters
        raw = "Aphex Twin - Selected Ambient Works (Vol. 2)"
        encoded = base64.b64encode(raw.encode()).decode()
        content = f"1769651283s album +!{encoded}\n"
        result = parse_metadata_log(content)
        assert result["album"] == [raw]

    def test_empty_content(self) -> None:
        result = parse_metadata_log("")
        assert result == {}

    def test_whitespace_only(self) -> None:
        result = parse_metadata_log("   \n  \n")
        assert result == {}

    def test_timestamp_with_decimal(self) -> None:
        content = "1507541153.566038914s artist +Test\n"
        result = parse_metadata_log(content)
        assert result["artist"] == ["Test"]

    def test_multiple_fields_single_line(self) -> None:
        content = "1769651283s artist +TestArtist title +TestTitle bpm +128\n"
        result = parse_metadata_log(content)
        assert result["artist"] == ["TestArtist"]
        assert result["title"] == ["TestTitle"]
        assert result["bpm"] == ["128"]

    def test_crate_values(self) -> None:
        content = "1769651283s crate +Festival +DarkPsy +Chillout\n"
        result = parse_metadata_log(content)
        assert result["crate"] == ["Chillout", "DarkPsy", "Festival"]

    def test_unset_nonexistent_value(self) -> None:
        """Unsetting a value that was never set should not error."""
        content = "1769651283s genre -NonExistent\n"
        result = parse_metadata_log(content)
        assert result["genre"] == []

    def test_field_with_no_values(self) -> None:
        """A field name followed by another field name (no values)."""
        content = "1769651283s artist genre +IDM\n"
        result = parse_metadata_log(content)
        assert result["artist"] == []
        assert result["genre"] == ["IDM"]


# ---------------------------------------------------------------------------
# _decode_value tests
# ---------------------------------------------------------------------------


class TestDecodeValue:
    def test_plain_value(self) -> None:
        assert _decode_value("hello") == "hello"

    def test_base64_value(self) -> None:
        encoded = base64.b64encode(b"test value").decode()
        assert _decode_value(f"!{encoded}") == "test value"

    def test_base64_unicode(self) -> None:
        encoded = base64.b64encode("über cool".encode()).decode()
        assert _decode_value(f"!{encoded}") == "über cool"


# ---------------------------------------------------------------------------
# _extract_key_from_path tests
# ---------------------------------------------------------------------------


class TestExtractKeyFromPath:
    def test_standard_path(self) -> None:
        path = "abc/def/SHA256E-s6850832--abc123.mp3.log.met"
        assert _extract_key_from_path(path) == "SHA256E-s6850832--abc123.mp3"

    def test_deep_path(self) -> None:
        path = "a0/b1/SHA256E-s100--xyz.flac.log.met"
        assert _extract_key_from_path(path) == "SHA256E-s100--xyz.flac"

    def test_no_directory(self) -> None:
        path = "KEY-s100--test.mp3.log.met"
        assert _extract_key_from_path(path) == "KEY-s100--test.mp3"


# ---------------------------------------------------------------------------
# _metadata_to_track / _metadata_to_crates tests
# ---------------------------------------------------------------------------


class TestMetadataToTrack:
    def test_full_metadata(self) -> None:
        metadata = {
            "artist": ["Test Artist"],
            "title": ["Test Title"],
            "album": ["Test Album"],
            "genre": ["Ambient"],
            "bpm": ["128.5"],
            "rating": ["4"],
            "key": ["Am"],
            "year": ["2024"],
            "tracknumber": ["03"],
            "comment": ["Nice track"],
            "color": ["#FF0000"],
        }
        track = _metadata_to_track("key1", metadata, "test.mp3")
        assert track.key == "key1"
        assert track.file == "test.mp3"
        assert track.artist == "Test Artist"
        assert track.title == "Test Title"
        assert track.bpm == 128.5
        assert track.rating == 4
        assert track.key_musical == "Am"

    def test_minimal_metadata(self) -> None:
        track = _metadata_to_track("key1", {}, "test.mp3")
        assert track.key == "key1"
        assert track.file == "test.mp3"
        assert track.artist is None
        assert track.bpm is None

    def test_invalid_bpm(self) -> None:
        metadata = {"bpm": ["notanumber"]}
        track = _metadata_to_track("key1", metadata, "test.mp3")
        assert track.bpm is None

    def test_invalid_rating(self) -> None:
        metadata = {"rating": ["notanint"]}
        track = _metadata_to_track("key1", metadata, "test.mp3")
        assert track.rating is None


class TestMetadataToCrates:
    def test_multiple_crates(self) -> None:
        metadata = {"crate": ["Festival", "DarkPsy"]}
        crates = _metadata_to_crates("key1", metadata)
        assert len(crates) == 2
        assert {c.crate for c in crates} == {"Festival", "DarkPsy"}

    def test_no_crates(self) -> None:
        crates = _metadata_to_crates("key1", {})
        assert crates == []
