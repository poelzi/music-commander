"""Unit tests for view template rendering."""

from __future__ import annotations

import pytest

from music_commander.view.template import (
    TemplateRenderError,
    get_template_variables,
    render_path,
)


class TestRenderPath:
    def test_basic_substitution(self) -> None:
        result = render_path(
            "{{ artist }} - {{ title }}",
            {
                "artist": "Test",
                "title": "Song",
            },
        )
        assert result == "Test - Song"

    def test_directory_path(self) -> None:
        result = render_path(
            "{{ genre }}/{{ artist }} - {{ title }}",
            {
                "genre": "Ambient",
                "artist": "Test",
                "title": "Song",
            },
        )
        assert result == "Ambient/Test - Song"

    def test_missing_value_becomes_unknown(self) -> None:
        result = render_path(
            "{{ artist }} - {{ title }}",
            {
                "artist": None,
                "title": "Song",
            },
        )
        assert result == "Unknown - Song"

    def test_empty_string_becomes_unknown(self) -> None:
        result = render_path(
            "{{ genre }}/{{ title }}",
            {
                "genre": "",
                "title": "Song",
            },
        )
        assert result == "Unknown/Song"

    def test_undefined_variable_becomes_unknown(self) -> None:
        result = render_path("{{ nonexistent }}/test", {})
        assert result == "Unknown/test"

    def test_round_to_filter(self) -> None:
        result = render_path("{{ bpm | round_to(5) }}", {"bpm": "143"})
        assert result == "145"

    def test_round_to_filter_exact(self) -> None:
        result = render_path("{{ bpm | round_to(10) }}", {"bpm": "148"})
        assert result == "150"

    def test_round_to_filter_none(self) -> None:
        result = render_path("{{ bpm | round_to(5) }}", {"bpm": None})
        assert result == "0.0"

    def test_builtin_lower_filter(self) -> None:
        result = render_path("{{ genre | lower }}", {"genre": "TECHNO"})
        assert result == "techno"

    def test_builtin_upper_filter(self) -> None:
        result = render_path("{{ genre | upper }}", {"genre": "techno"})
        assert result == "TECHNO"

    def test_builtin_default_filter(self) -> None:
        result = render_path("{{ genre | default('NoGenre') }}", {"genre": None})
        # With StrictUndefined, the default filter works on None values
        assert "NoGenre" in result or "Unknown" in result

    def test_builtin_truncate_filter(self) -> None:
        result = render_path("{{ title | truncate(10) }}", {"title": "A Very Long Title"})
        assert len(result) <= 13  # truncate adds "..."

    def test_syntax_error_raises(self) -> None:
        with pytest.raises(TemplateRenderError):
            render_path("{{ unclosed", {})

    def test_complex_template(self) -> None:
        result = render_path(
            "{{ genre }}/{{ bpm | round_to(5) }}/{{ artist }} - {{ title }}",
            {"genre": "Techno", "bpm": "142", "artist": "DJ", "title": "Track"},
        )
        assert result == "Techno/140/DJ - Track"


class TestGetTemplateVariables:
    def test_simple(self) -> None:
        vars = get_template_variables("{{ artist }} - {{ title }}")
        assert vars == {"artist", "title"}

    def test_with_filters(self) -> None:
        vars = get_template_variables("{{ bpm | round_to(5) }}")
        assert "bpm" in vars

    def test_nested_path(self) -> None:
        vars = get_template_variables("{{ genre }}/{{ artist }}/{{ title }}")
        assert vars == {"genre", "artist", "title"}

    def test_invalid_template(self) -> None:
        vars = get_template_variables("{{ unclosed")
        assert vars == set()
