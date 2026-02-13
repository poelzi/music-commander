"""Convert SearchQuery AST to SQL and execute against the cache database."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import and_, func, not_, or_, text

from music_commander.cache.models import CacheTrack, TrackCrate
from music_commander.search.ast_nodes import FieldFilter, OrGroup, SearchQuery, TextTerm

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# Map search field names to CacheTrack column names.
# "key" (musical key) maps to key_musical to avoid collision with the PK.
_FIELD_TO_COLUMN: dict[str, str] = {
    "artist": "artist",
    "title": "title",
    "album": "album",
    "genre": "genre",
    "bpm": "bpm",
    "rating": "rating",
    "key": "key_musical",
    "year": "year",
    "tracknumber": "tracknumber",
    "comment": "comment",
    "color": "color",
    "file": "file",
}

# Numeric columns that should be cast to float/int for comparisons.
_NUMERIC_COLUMNS: frozenset[str] = frozenset({"bpm", "rating"})


def _get_column(field: str):
    """Get the SQLAlchemy column attribute for a field name."""
    col_name = _FIELD_TO_COLUMN.get(field, field)
    return getattr(CacheTrack, col_name, None)


def _build_text_term_clause(term: TextTerm, session: Session):
    """Build a SQL clause for a TextTerm (bare-word or quoted full-text search).

    Uses FTS5 MATCH for full-text search across artist, title, album, genre, file.
    The FTS5 virtual table is guaranteed to exist by the cache builder.
    """
    value = term.value
    # Use FTS5 MATCH — search for the term as a prefix match
    # We need to find track keys that match in the FTS5 table
    fts_match = f'"{value}"*'

    # Use raw text subquery for FTS5 (virtual tables aren't in ORM)
    fts_subquery = text("SELECT key FROM tracks_fts WHERE tracks_fts MATCH :fts_term").bindparams(
        fts_term=fts_match
    )
    fts_clause = CacheTrack.key.in_(fts_subquery)

    if term.negated:
        return not_(fts_clause)
    return fts_clause


def _build_text_term_clause_like(term: TextTerm):
    """Build a LIKE-based clause for text search (fallback).

    Searches across artist, title, album, genre, and file columns.
    """
    pattern = f"%{term.value}%"
    like_clause = or_(
        CacheTrack.artist.ilike(pattern),
        CacheTrack.title.ilike(pattern),
        CacheTrack.album.ilike(pattern),
        CacheTrack.genre.ilike(pattern),
        CacheTrack.file.ilike(pattern),
    )
    if term.negated:
        return not_(like_clause)
    return like_clause


def _build_field_filter_clause(ff: FieldFilter, session: Session):
    """Build a SQL clause for a FieldFilter."""
    # Handle crate field specially — it's in a separate table
    if ff.field == "crate":
        return _build_crate_clause(ff, session)

    col = _get_column(ff.field)
    if col is None:
        # Unknown field — fall back to LIKE across all text fields
        return _build_text_term_clause_like(TextTerm(value=ff.value, negated=ff.negated))

    clause = _build_column_clause(col, ff)

    if ff.negated:
        return not_(clause)
    return clause


def _build_column_clause(col, ff: FieldFilter):
    """Build the actual column comparison clause."""
    op = ff.operator

    if op == "empty":
        return or_(col.is_(None), col == "")

    if op == "contains":
        return col.ilike(f"%{ff.value}%")

    if op == "=":
        # Case-insensitive exact match
        return func.lower(col) == ff.value.lower()

    # Numeric operators
    try:
        val = float(ff.value)
    except (ValueError, TypeError):
        # Fall back to string comparison
        val = ff.value

    if op == ">":
        return col > val
    if op == ">=":
        return col >= val
    if op == "<":
        return col < val
    if op == "<=":
        return col <= val

    if op == "range":
        try:
            val_end = float(ff.value_end) if ff.value_end else val
        except (ValueError, TypeError):
            val_end = ff.value_end
        return and_(col >= val, col <= val_end)

    # Default fallback
    return col.ilike(f"%{ff.value}%")


def _build_crate_clause(ff: FieldFilter, session: Session):
    """Build a clause for crate field queries.

    Crate values are stored in the TrackCrate join table.
    """
    if ff.operator == "empty":
        # Track has no crate assignments
        subq = session.query(TrackCrate.key).subquery()
        clause = CacheTrack.key.notin_(session.query(subq.c.key))
    elif ff.operator == "=":
        clause = CacheTrack.key.in_(
            session.query(TrackCrate.key).filter(func.lower(TrackCrate.crate) == ff.value.lower())
        )
    else:
        # contains (default)
        clause = CacheTrack.key.in_(
            session.query(TrackCrate.key).filter(TrackCrate.crate.ilike(f"%{ff.value}%"))
        )

    if ff.negated:
        return not_(clause)
    return clause


def _build_or_group_clause(group: OrGroup, session: Session):
    """Build an AND clause from all clauses within an OrGroup."""
    conditions = []
    for clause_node in group.clauses:
        if isinstance(clause_node, TextTerm):
            conditions.append(_build_text_term_clause(clause_node, session))
        elif isinstance(clause_node, FieldFilter):
            conditions.append(_build_field_filter_clause(clause_node, session))

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return and_(*conditions)


def execute_search(session: Session, query: SearchQuery) -> list[CacheTrack]:
    """Execute a parsed SearchQuery against the cache database.

    Args:
        session: SQLAlchemy session connected to the cache database.
        query: Parsed SearchQuery AST.

    Returns:
        List of CacheTrack objects matching the query.
    """
    if not query.groups:
        return list(session.query(CacheTrack).all())

    or_conditions = []
    for group in query.groups:
        group_clause = _build_or_group_clause(group, session)
        if group_clause is not None:
            or_conditions.append(group_clause)

    if not or_conditions:
        return list(session.query(CacheTrack).all())

    if len(or_conditions) == 1:
        final_clause = or_conditions[0]
    else:
        final_clause = or_(*or_conditions)

    return list(
        session.query(CacheTrack)
        .filter(final_clause)
        .order_by(CacheTrack.artist, CacheTrack.title)
        .all()
    )
