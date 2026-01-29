"""AST data classes for parsed search queries."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TextTerm:
    """A bare-word or quoted phrase for full-text search."""

    value: str
    negated: bool = False


@dataclass
class FieldFilter:
    """A field-specific filter like ``artist:value`` or ``bpm:>140``.

    Operators:
        - ``contains``: partial match (default for ``field:value``)
        - ``=``: exact match (``field:="value"``)
        - ``>``, ``<``, ``>=``, ``<=``: numeric comparison
        - ``range``: numeric range (``field:N-M``), value=N, value_end=M
        - ``empty``: empty field search (``field:""``)
    """

    field: str
    operator: str
    value: str
    value_end: str | None = None
    negated: bool = False


@dataclass
class OrGroup:
    """A group of AND-ed clauses.

    Within an OrGroup, all clauses are implicitly ANDed.
    Multiple OrGroups in a SearchQuery are OR-ed together.
    """

    clauses: list[TextTerm | FieldFilter] = field(default_factory=list)


@dataclass
class SearchQuery:
    """Top-level search query: OR-separated groups of AND-ed clauses."""

    groups: list[OrGroup] = field(default_factory=list)
