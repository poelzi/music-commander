"""Unit tests for shared matching utilities."""

from __future__ import annotations

import pytest
from music_commander.utils.matching import (
    MatchTier,
    classify_match,
    extract_embedded_artist,
    extract_volume,
    match_release,
    match_track,
    normalize,
    normalize_for_matching,
    safe_partial_ratio,
    split_band_name,
    strip_edition_suffixes,
    strip_punctuation,
)


class TestNormalize:
    """Tests for normalize()."""

    def test_lowercase(self):
        assert normalize("Hello World") == "hello world"

    def test_collapse_whitespace(self):
        assert normalize("hello   world") == "hello world"

    def test_strip_edges(self):
        assert normalize("  hello  ") == "hello"


class TestStripPunctuation:
    """Tests for strip_punctuation()."""

    def test_removes_punctuation(self):
        assert strip_punctuation("hello, world!") == "hello world"

    def test_keeps_alphanumeric(self):
        assert strip_punctuation("track01") == "track01"

    def test_keeps_spaces(self):
        assert strip_punctuation("hello world") == "hello world"


class TestStripEditionSuffixes:
    """Tests for strip_edition_suffixes()."""

    def test_removes_deluxe(self):
        assert strip_edition_suffixes("Album (Deluxe Edition)") == "Album"

    def test_removes_remastered(self):
        assert strip_edition_suffixes("Album [Remastered]") == "Album"

    def test_removes_anniversary(self):
        assert strip_edition_suffixes("Album (10th Anniversary Edition)") == "Album"

    def test_keeps_non_edition(self):
        assert strip_edition_suffixes("Album (Part 1)") == "Album (Part 1)"


class TestNormalizeForMatching:
    """Tests for normalize_for_matching()."""

    def test_full_pipeline(self):
        result = normalize_for_matching("Artist\u2013Album [CAT001] (Deluxe)")
        assert "cat001" not in result
        assert "deluxe" not in result

    def test_dashes_become_spaces(self):
        result = normalize_for_matching("dark-psy-portal")
        assert result == "dark psy portal"

    def test_zero_width_removed(self):
        result = normalize_for_matching("hello\u200bworld")
        assert result == "helloworld"

    def test_noise_phrases_removed(self):
        result = normalize_for_matching("Track Name (Free Download)")
        assert "free download" not in result.lower()

    def test_colons_become_spaces(self):
        result = normalize_for_matching("Label: Album")
        assert ":" not in result


class TestExtractVolume:
    """Tests for extract_volume()."""

    def test_vol_arabic(self):
        assert extract_volume("Compilation Vol. 3") == 3

    def test_volume_roman(self):
        assert extract_volume("Series Volume IV") == 4

    def test_part_number(self):
        assert extract_volume("Part 2") == 2

    def test_pt_number(self):
        assert extract_volume("Pt. 5") == 5

    def test_no_volume(self):
        assert extract_volume("Regular Album") is None


class TestExtractEmbeddedArtist:
    """Tests for extract_embedded_artist()."""

    def test_artist_album(self):
        artist, album = extract_embedded_artist("Artist - Album Title")
        assert artist == "Artist"
        assert album == "Album Title"

    def test_no_separator(self):
        artist, album = extract_embedded_artist("Just An Album")
        assert artist is None
        assert album == "Just An Album"

    def test_multiple_dashes(self):
        artist, album = extract_embedded_artist("Artist - Sub - Album")
        assert artist == "Artist"
        assert album == "Sub - Album"

    def test_em_dash(self):
        artist, album = extract_embedded_artist("Artist \u2014 Album")
        assert artist == "Artist"
        assert album == "Album"


class TestSplitBandName:
    """Tests for split_band_name()."""

    def test_simple_name(self):
        result = split_band_name("Artist")
        assert result == ["Artist"]

    def test_label_artist(self):
        result = split_band_name("Label - Artist")
        assert "Artist" in result
        assert "Label" in result
        # Artist (last part) should come first
        assert result[0] == "Artist"

    def test_three_parts(self):
        result = split_band_name("Label - Artist - Album")
        assert "Artist" in result

    def test_original_always_included(self):
        result = split_band_name("Label - Artist")
        assert "Label - Artist" in result


class TestSafePartialRatio:
    """Tests for safe_partial_ratio()."""

    def test_empty_strings(self):
        assert safe_partial_ratio("", "test") == 0.0
        assert safe_partial_ratio("test", "") == 0.0

    def test_short_strings_use_full_match(self):
        # Short strings should use token_sort_ratio, not partial
        score = safe_partial_ratio("ab", "abcdefghij")
        # Should be low because full match penalizes length difference
        assert score < 50

    def test_identical_strings(self):
        score = safe_partial_ratio("dark psy portal", "dark psy portal")
        assert score >= 95

    def test_length_ratio_penalty(self):
        # Very different lengths should get penalized
        score = safe_partial_ratio("ra", "ace ventura live at ozora")
        assert score < 80


class TestMatchTier:
    """Tests for classify_match()."""

    def test_exact(self):
        assert classify_match(95) == MatchTier.EXACT
        assert classify_match(100) == MatchTier.EXACT

    def test_high(self):
        assert classify_match(80) == MatchTier.HIGH
        assert classify_match(94) == MatchTier.HIGH

    def test_low(self):
        assert classify_match(60) == MatchTier.LOW
        assert classify_match(79) == MatchTier.LOW

    def test_none(self):
        assert classify_match(59) == MatchTier.NONE
        assert classify_match(0) == MatchTier.NONE


class TestMatchRelease:
    """Tests for match_release()."""

    def test_identical(self):
        score = match_release("Artist", "Album", "Artist", "Album")
        assert score >= 95

    def test_different_artist(self):
        score = match_release("Artist A", "Album", "Artist B", "Album")
        assert score < 95

    def test_completely_different(self):
        score = match_release("Foo", "Bar", "Baz", "Qux")
        assert score < 50

    def test_case_insensitive(self):
        score = match_release("ARTIST", "ALBUM", "artist", "album")
        assert score >= 95


class TestMatchTrack:
    """Tests for match_track()."""

    def test_identical(self):
        score = match_track("Artist", "Title", "Artist", "Title")
        assert score >= 95

    def test_different_title(self):
        score = match_track("Artist", "Track A", "Artist", "Track B")
        assert score < 95

    def test_weighting(self):
        # Title has 60% weight, so same title different artist should score
        # higher than same artist different title
        score_same_title = match_track("Foo", "Same Title", "Bar", "Same Title")
        score_same_artist = match_track("Same Artist", "Foo", "Same Artist", "Bar")
        assert score_same_title > score_same_artist
