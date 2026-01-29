"""Unit tests for search query parser."""

from __future__ import annotations

import pytest

from music_commander.search.ast_nodes import FieldFilter, OrGroup, SearchQuery, TextTerm
from music_commander.search.parser import SearchParseError, parse_query

# ---------------------------------------------------------------------------
# Bare word / text term tests
# ---------------------------------------------------------------------------


class TestTextTerms:
    def test_single_word(self) -> None:
        q = parse_query("hello")
        assert len(q.groups) == 1
        assert len(q.groups[0].clauses) == 1
        term = q.groups[0].clauses[0]
        assert isinstance(term, TextTerm)
        assert term.value == "hello"
        assert term.negated is False

    def test_two_words_anded(self) -> None:
        q = parse_query("dark psy")
        assert len(q.groups) == 1
        clauses = q.groups[0].clauses
        assert len(clauses) == 2
        assert all(isinstance(c, TextTerm) for c in clauses)
        assert clauses[0].value == "dark"
        assert clauses[1].value == "psy"

    def test_quoted_phrase(self) -> None:
        q = parse_query('"dark psy"')
        assert len(q.groups) == 1
        assert len(q.groups[0].clauses) == 1
        term = q.groups[0].clauses[0]
        assert isinstance(term, TextTerm)
        assert term.value == "dark psy"

    def test_negated_word(self) -> None:
        q = parse_query("-ambient")
        assert len(q.groups) == 1
        term = q.groups[0].clauses[0]
        assert isinstance(term, TextTerm)
        assert term.value == "ambient"
        assert term.negated is True

    def test_negated_quoted_phrase(self) -> None:
        q = parse_query('-"dark psy"')
        term = q.groups[0].clauses[0]
        assert isinstance(term, TextTerm)
        assert term.value == "dark psy"
        assert term.negated is True


# ---------------------------------------------------------------------------
# Field filter tests
# ---------------------------------------------------------------------------


class TestFieldFilter:
    def test_contains(self) -> None:
        q = parse_query("artist:Basinski")
        f = q.groups[0].clauses[0]
        assert isinstance(f, FieldFilter)
        assert f.field == "artist"
        assert f.operator == "contains"
        assert f.value == "Basinski"
        assert f.negated is False

    def test_contains_quoted(self) -> None:
        q = parse_query('artist:"Com Truise"')
        f = q.groups[0].clauses[0]
        assert isinstance(f, FieldFilter)
        assert f.field == "artist"
        assert f.operator == "contains"
        assert f.value == "Com Truise"

    def test_exact_match_quoted(self) -> None:
        q = parse_query('artist:="DJ Name"')
        f = q.groups[0].clauses[0]
        assert isinstance(f, FieldFilter)
        assert f.field == "artist"
        assert f.operator == "="
        assert f.value == "DJ Name"

    def test_exact_match_bare(self) -> None:
        q = parse_query("artist:=Basinski")
        f = q.groups[0].clauses[0]
        assert isinstance(f, FieldFilter)
        assert f.operator == "="
        assert f.value == "Basinski"

    def test_gt(self) -> None:
        q = parse_query("bpm:>140")
        f = q.groups[0].clauses[0]
        assert isinstance(f, FieldFilter)
        assert f.field == "bpm"
        assert f.operator == ">"
        assert f.value == "140"

    def test_gte(self) -> None:
        q = parse_query("rating:>=4")
        f = q.groups[0].clauses[0]
        assert isinstance(f, FieldFilter)
        assert f.operator == ">="
        assert f.value == "4"

    def test_lt(self) -> None:
        q = parse_query("year:<2010")
        f = q.groups[0].clauses[0]
        assert isinstance(f, FieldFilter)
        assert f.operator == "<"
        assert f.value == "2010"

    def test_lte(self) -> None:
        q = parse_query("bpm:<=100")
        f = q.groups[0].clauses[0]
        assert isinstance(f, FieldFilter)
        assert f.operator == "<="
        assert f.value == "100"

    def test_range(self) -> None:
        q = parse_query("bpm:140-160")
        f = q.groups[0].clauses[0]
        assert isinstance(f, FieldFilter)
        assert f.field == "bpm"
        assert f.operator == "range"
        assert f.value == "140"
        assert f.value_end == "160"

    def test_range_rating(self) -> None:
        q = parse_query("rating:3-5")
        f = q.groups[0].clauses[0]
        assert isinstance(f, FieldFilter)
        assert f.operator == "range"
        assert f.value == "3"
        assert f.value_end == "5"

    def test_empty_field(self) -> None:
        q = parse_query('genre:""')
        f = q.groups[0].clauses[0]
        assert isinstance(f, FieldFilter)
        assert f.field == "genre"
        assert f.operator == "empty"
        assert f.value == ""

    def test_negated_field(self) -> None:
        q = parse_query("-genre:ambient")
        f = q.groups[0].clauses[0]
        assert isinstance(f, FieldFilter)
        assert f.field == "genre"
        assert f.operator == "contains"
        assert f.value == "ambient"
        assert f.negated is True

    def test_negated_field_gt(self) -> None:
        q = parse_query("-bpm:>200")
        f = q.groups[0].clauses[0]
        assert isinstance(f, FieldFilter)
        assert f.field == "bpm"
        assert f.operator == ">"
        assert f.value == "200"
        assert f.negated is True

    def test_location_alias(self) -> None:
        q = parse_query("location:ambient")
        f = q.groups[0].clauses[0]
        assert isinstance(f, FieldFilter)
        assert f.field == "file"
        assert f.operator == "contains"
        assert f.value == "ambient"

    def test_float_comparison(self) -> None:
        q = parse_query("bpm:>140.5")
        f = q.groups[0].clauses[0]
        assert isinstance(f, FieldFilter)
        assert f.value == "140.5"

    def test_float_range(self) -> None:
        q = parse_query("bpm:130.0-145.5")
        f = q.groups[0].clauses[0]
        assert isinstance(f, FieldFilter)
        assert f.operator == "range"
        assert f.value == "130.0"
        assert f.value_end == "145.5"


# ---------------------------------------------------------------------------
# OR logic tests
# ---------------------------------------------------------------------------


class TestOrLogic:
    def test_pipe_separator(self) -> None:
        q = parse_query("genre:house | genre:techno")
        assert len(q.groups) == 2
        assert q.groups[0].clauses[0].value == "house"
        assert q.groups[1].clauses[0].value == "techno"

    def test_or_keyword(self) -> None:
        q = parse_query("genre:house OR genre:techno")
        assert len(q.groups) == 2
        assert q.groups[0].clauses[0].value == "house"
        assert q.groups[1].clauses[0].value == "techno"

    def test_or_precedence(self) -> None:
        """a b | c d should be (a AND b) OR (c AND d)."""
        q = parse_query("a b | c d")
        assert len(q.groups) == 2
        g0 = q.groups[0]
        g1 = q.groups[1]
        assert len(g0.clauses) == 2
        assert len(g1.clauses) == 2
        assert g0.clauses[0].value == "a"
        assert g0.clauses[1].value == "b"
        assert g1.clauses[0].value == "c"
        assert g1.clauses[1].value == "d"

    def test_multiple_or_groups(self) -> None:
        q = parse_query("a | b | c")
        assert len(q.groups) == 3

    def test_lowercase_or_is_word(self) -> None:
        """Lowercase 'or' should be treated as a bare word, not OR."""
        q = parse_query("dark or psy")
        assert len(q.groups) == 1
        clauses = q.groups[0].clauses
        assert len(clauses) == 3
        assert clauses[1].value == "or"


# ---------------------------------------------------------------------------
# Mixed / complex query tests
# ---------------------------------------------------------------------------


class TestMixedQueries:
    def test_mixed_terms_and_fields(self) -> None:
        q = parse_query("dark psy bpm:>140")
        assert len(q.groups) == 1
        clauses = q.groups[0].clauses
        assert len(clauses) == 3
        assert isinstance(clauses[0], TextTerm)
        assert isinstance(clauses[1], TextTerm)
        assert isinstance(clauses[2], FieldFilter)

    def test_complex_query(self) -> None:
        q = parse_query("dark psy bpm:>140 -genre:ambient | techno rating:>=4")
        assert len(q.groups) == 2
        g0 = q.groups[0]
        g1 = q.groups[1]
        # Group 0: dark AND psy AND bpm:>140 AND -genre:ambient
        assert len(g0.clauses) == 4
        assert g0.clauses[0].value == "dark"
        assert g0.clauses[1].value == "psy"
        assert g0.clauses[2].operator == ">"
        assert g0.clauses[3].negated is True
        # Group 1: techno AND rating:>=4
        assert len(g1.clauses) == 2
        assert g1.clauses[0].value == "techno"
        assert g1.clauses[1].operator == ">="

    def test_field_then_text(self) -> None:
        q = parse_query("artist:Test hello")
        clauses = q.groups[0].clauses
        assert len(clauses) == 2
        assert isinstance(clauses[0], FieldFilter)
        assert isinstance(clauses[1], TextTerm)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_query(self) -> None:
        q = parse_query("")
        assert q.groups == []

    def test_whitespace_only(self) -> None:
        q = parse_query("   ")
        assert q.groups == []

    def test_single_term(self) -> None:
        q = parse_query("hello")
        assert len(q.groups) == 1
        assert len(q.groups[0].clauses) == 1

    def test_only_negation(self) -> None:
        q = parse_query("-ambient")
        assert len(q.groups) == 1
        assert q.groups[0].clauses[0].negated is True

    def test_multiple_negations(self) -> None:
        q = parse_query("-dark -ambient")
        clauses = q.groups[0].clauses
        assert len(clauses) == 2
        assert all(c.negated for c in clauses)


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_parse_error_type(self) -> None:
        """SearchParseError should contain the query string."""
        with pytest.raises(SearchParseError) as exc_info:
            parse_query('artist:"unclosed')
        assert "unclosed" in str(exc_info.value)

    def test_search_parse_error_attributes(self) -> None:
        try:
            parse_query('artist:"unclosed')
        except SearchParseError as e:
            assert e.query == 'artist:"unclosed'
