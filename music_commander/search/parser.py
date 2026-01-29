"""Parse Mixxx-compatible search syntax into an AST."""

from __future__ import annotations

from importlib import resources
from typing import Any

from lark import Lark, Token, Transformer, Tree, UnexpectedInput

from music_commander.search.ast_nodes import (
    FieldFilter,
    OrGroup,
    SearchQuery,
    TextTerm,
)

# Field name aliases (Mixxx compatibility)
_FIELD_ALIASES: dict[str, str] = {
    "location": "file",
}

# Known fields that map to cache columns
KNOWN_FIELDS: frozenset[str] = frozenset(
    {
        "artist",
        "title",
        "album",
        "genre",
        "bpm",
        "rating",
        "key",
        "year",
        "tracknumber",
        "comment",
        "color",
        "file",
        "crate",
    }
)


def _load_grammar() -> str:
    """Load the Lark grammar from the package resources."""
    return resources.files("music_commander.search").joinpath("grammar.lark").read_text()


_GRAMMAR_TEXT = _load_grammar()

_parser = Lark(
    _GRAMMAR_TEXT,
    parser="earley",
    ambiguity="resolve",
)


class _SearchTransformer(Transformer):
    """Transform Lark parse tree into AST data classes."""

    def start(self, items: list[Any]) -> SearchQuery:
        return items[0]

    def query(self, items: list[Any]) -> SearchQuery:
        groups: list[OrGroup] = []
        for item in items:
            if isinstance(item, OrGroup):
                groups.append(item)
        return SearchQuery(groups=groups)

    def or_group(self, items: list[Any]) -> OrGroup:
        clauses: list[TextTerm | FieldFilter] = []
        for item in items:
            if isinstance(item, (TextTerm, FieldFilter)):
                clauses.append(item)
        return OrGroup(clauses=clauses)

    def negated_clause(self, items: list[Any]) -> TextTerm | FieldFilter:
        # items[0] is NEGATE token "-", items[1] is the actual clause
        clause = items[-1]
        if isinstance(clause, (TextTerm, FieldFilter)):
            clause.negated = True
        return clause

    def field_filter(self, items: list[Any]) -> FieldFilter:
        field_name = str(items[0])
        # Apply aliases
        field_name = _FIELD_ALIASES.get(field_name, field_name)
        value_node = items[1]
        if isinstance(value_node, FieldFilter):
            value_node.field = field_name
            return value_node
        # Shouldn't happen with well-formed grammar
        return FieldFilter(field=field_name, operator="contains", value=str(value_node))

    def exact_value(self, items: list[Any]) -> FieldFilter:
        value = str(items[0])
        return FieldFilter(field="", operator="=", value=value)

    def empty_value(self, items: list[Any]) -> FieldFilter:
        return FieldFilter(field="", operator="empty", value="")

    def range_value(self, items: list[Any]) -> FieldFilter:
        return FieldFilter(
            field="",
            operator="range",
            value=str(items[0]),
            value_end=str(items[1]),
        )

    def comparison_value(self, items: list[Any]) -> FieldFilter:
        op = str(items[0])
        value = str(items[1])
        return FieldFilter(field="", operator=op, value=value)

    def contains_value(self, items: list[Any]) -> FieldFilter:
        value = str(items[0])
        return FieldFilter(field="", operator="contains", value=value)

    def bare_value(self, items: list[Any]) -> str:
        return str(items[0])

    def quoted_string(self, items: list[Any]) -> str:
        # QUOTED_STRING terminal already stripped by QUOTED_STRING handler
        return str(items[0])

    def text_term(self, items: list[Any]) -> TextTerm:
        value = str(items[0])
        return TextTerm(value=value)

    # Pass through tokens we don't need
    def OR_SEP(self, token: Token) -> Token:
        return token

    def FIELD_NAME(self, token: Token) -> str:
        return str(token)

    def CMP_OP(self, token: Token) -> str:
        return str(token)

    def NUMBER(self, token: Token) -> str:
        return str(token)

    def EMPTY_QUOTES(self, token: Token) -> str:
        return ""

    def BARE_VALUE(self, token: Token) -> str:
        return str(token)

    def QUOTED_STRING(self, token: Token) -> str:
        raw = str(token)
        # Strip surrounding quotes
        if raw.startswith('"') and raw.endswith('"'):
            return raw[1:-1]
        return raw


_transformer = _SearchTransformer()


class SearchParseError(Exception):
    """Raised when a search query cannot be parsed."""

    def __init__(self, query: str, message: str) -> None:
        self.query = query
        super().__init__(f"Failed to parse search query '{query}': {message}")


def parse_query(query_string: str) -> SearchQuery:
    """Parse a Mixxx-compatible search query string into an AST.

    Args:
        query_string: The search query to parse.

    Returns:
        A SearchQuery AST representing the parsed query.

    Raises:
        SearchParseError: If the query cannot be parsed.
    """
    query_string = query_string.strip()
    if not query_string:
        return SearchQuery(groups=[])

    try:
        tree = _parser.parse(query_string)
        return _transformer.transform(tree)
    except UnexpectedInput as e:
        raise SearchParseError(query_string, str(e)) from e
