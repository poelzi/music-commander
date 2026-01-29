---
work_package_id: "WP03"
subtasks:
  - "T013"
  - "T014"
  - "T015"
  - "T016"
  - "T017"
  - "T018"
title: "Search Parser"
phase: "Phase 1 - Core"
lane: "doing"
dependencies: []
assignee: ""
agent: "claude-opus"
shell_pid: ""
review_status: ""
reviewed_by: ""
history:
  - timestamp: "2026-01-29T02:41:50Z"
    lane: "planned"
    agent: "system"
    shell_pid: ""
    action: "Prompt generated via /spec-kitty.tasks"
---

# Work Package Prompt: WP03 -- Search Parser

## Implementation Command

```bash
spec-kitty implement WP03
```

## Objectives & Success Criteria

- Parse Mixxx 2.5-compatible search syntax into a structured AST
- Support all operators: bare words, field:value, field:>N, field:N-M, -negation, | OR, field:="exact", field:"", quoted strings
- Unit tests for every syntax variant
- Parser handles malformed input gracefully (meaningful error messages)

## Context & Constraints

- Spec: `kitty-specs/003-annex-metadata-search-views/spec.md` — FR-001 through FR-010
- Research: Mixxx 2.5 search syntax (see spec Clarifications section)
- Use `lark` library for grammar definition
- No dependency on cache infrastructure — can be developed in parallel with WP01/WP02

## Subtasks & Detailed Guidance

### Subtask T013 -- Create search __init__.py
- **Files**: `music_commander/search/__init__.py`
- **Steps**: Export key classes (SearchQuery, parse_query).

### Subtask T014 -- Create lark grammar file
- **Purpose**: Define formal grammar for Mixxx search syntax.
- **Files**: `music_commander/search/grammar.lark`
- **Steps**:
  1. Define grammar rules for:
     - `query`: top-level, sequence of or_groups separated by `|` or `OR`
     - `or_group`: sequence of and_clauses (implicitly ANDed)
     - `and_clause`: optional `-` negation + (field_filter | text_term)
     - `field_filter`: `FIELD:OP?VALUE` or `FIELD:=VALUE` or `FIELD:"quoted"`
     - `text_term`: bare word or `"quoted phrase"`
     - Operators: `>`, `<`, `>=`, `<=`, range `N-M`
  2. Handle: `dark psy bpm:>140 rating:>=4 -genre:ambient genre:house | genre:techno artist:="DJ Name"`
  3. Whitespace between tokens, optional space after colon
  4. `OR` keyword is case-sensitive (uppercase only). Lowercase `or` is treated as a bare search term.
  5. `|` is an alternative OR separator.

### Subtask T015 -- Create search parser module
- **Purpose**: Use lark to parse query strings into AST.
- **Files**: `music_commander/search/parser.py`
- **Steps**:
  1. Load grammar from `grammar.lark` (use `importlib.resources` or relative path)
  2. Create `parse_query(query_string: str) -> SearchQuery` function
  3. Implement Transformer to convert lark parse tree to AST data classes
  4. Handle parse errors with meaningful messages

### Subtask T016 -- Implement AST data classes
- **Purpose**: Structured representation of parsed search queries.
- **Files**: `music_commander/search/parser.py` (or separate `ast.py`)
- **Steps**:
  Define dataclasses:
  ```python
  @dataclass
  class TextTerm:
      value: str
      negated: bool = False

  @dataclass
  class FieldFilter:
      field: str
      operator: str  # "contains", "=", ">", "<", ">=", "<=", "range", "empty"
      value: str
      value_end: str | None = None  # For range: N-M
      negated: bool = False

  @dataclass
  class OrGroup:
      clauses: list[TextTerm | FieldFilter]

  @dataclass
  class SearchQuery:
      groups: list[OrGroup]  # OR-separated groups
  ```
- **Parallel?**: Yes, can be defined independently.

### Subtask T017 -- Handle all syntax variants
- **Purpose**: Ensure comprehensive syntax support.
- **Files**: `music_commander/search/parser.py`
- **Steps**: Verify these parse correctly:
  - Bare words: `dark psy` → two TextTerms ANDed
  - Field partial match: `artist:Basinski` → FieldFilter(contains)
  - Field exact match: `artist:="DJ Name"` → FieldFilter(=)
  - Numeric comparison: `bpm:>140`, `rating:>=4`, `year:<2010`
  - Numeric range: `bpm:140-160`, `rating:3-5`
  - Negation: `-genre:ambient` → FieldFilter(negated=True)
  - OR: `genre:house | genre:techno` → two OrGroups
  - OR (spelled): `genre:house OR genre:techno`
  - Empty field: `genre:""` → FieldFilter(empty)
  - Quoted strings: `artist:"Com Truise"` → FieldFilter(contains, "Com Truise")
  - Mixed: `dark psy bpm:>140 -genre:ambient | techno rating:>=4`

### Subtask T018 -- Parser tests
- **Files**: `tests/test_search_parser.py`
- **Steps**:
  1. Test each syntax variant from T017
  2. Test edge cases: empty query, single term, only negation
  3. Test malformed input: unclosed quotes, invalid operator, field with no value
  4. Test OR precedence: `a b | c d` should be `(a AND b) OR (c AND d)`

## Test Strategy

- Pure unit tests — parser has no external dependencies
- Test both parse success and parse failure cases
- Verify AST structure matches expected output for each query

## Risks & Mitigations

- Grammar ambiguity with `-` (negation vs hyphenated words) — treat `-` as negation only at term start
- OR precedence edge cases — explicit grammar rules handle this
- Lark version compatibility — pin minimum version

## Review Guidance

- Verify grammar handles all Mixxx 2.5 syntax from FR-001 through FR-010
- Verify OR has lower precedence than AND
- Verify error messages are user-friendly

## Activity Log

- 2026-01-29T02:41:50Z -- system -- lane=planned -- Prompt created.
- 2026-01-29T12:40:40Z – claude-opus – shell_pid= – lane=doing – Starting implementation of WP03: Search Grammar & Parser
