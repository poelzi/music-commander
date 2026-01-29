# Research: Annex Metadata Search & Symlink Views

**Date**: 2026-01-29
**Feature**: 003-annex-metadata-search-views

## Decision 1: Git-Annex Metadata Retrieval Strategy

**Decision**: Use raw git-annex branch read for cache population; use `git annex find --metadata` for simple pre-filtering.

**Rationale**: Benchmarked on 107,842 files:
- `metadata --batch --json` (official API): 3m 42s — too slow for cache build
- `git annex find --metadata` (filter only): 48s — no metadata values in output
- **Raw branch read** (`git ls-tree` + `git cat-file --batch`): **~16s total** — 14x faster

The raw approach reads `.log.met` files from the `git-annex` branch directly. Each file contains `key=value` pairs. A second pass with `git annex find --format='${key}\t${file}\n'` (~12s) maps keys to file paths.

**Alternatives considered**:
- `metadata --batch --json`: Too slow (3m42s). Rejected.
- `git annex find --metadata` alone: Cannot output metadata values, only filter. Insufficient for Jinja2 templates.
- Reading `.git/annex/` directly: Implementation-specific, may break with git-annex upgrades.

## Decision 2: Cache Invalidation Strategy

**Decision**: Use `git diff-tree` on the `git-annex` branch to detect incremental changes.

**Rationale**: Comparing the last-seen `git-annex` branch commit to current HEAD gives a list of changed `.log.met` files, enabling incremental cache updates without full re-scan.

**Alternatives considered**:
- Full re-scan on every search: 16s acceptable but unnecessary for repeated queries.
- File modification timestamps: git-annex branch is a bare git branch, no filesystem timestamps.

## Decision 3: Git-Annex Native Capabilities

**What git-annex CAN do natively** (push to git-annex):
- `--metadata field=value` (exact/glob match, case-insensitive)
- `--metadata field>number`, `field<number`, `field>=number`, `field<=number`
- `--or` between filter groups
- `--not` to negate any matcher
- Combine multiple `--metadata` flags (AND logic)

**What REQUIRES the local SQLite cache**:
- Full-text search across multiple fields (bare words)
- Metadata value output (git-annex find cannot output metadata, only filter)
- Sorting by metadata fields
- Cross-field queries for Jinja2 template rendering
- Partial text matching (git-annex only supports glob, not substring)
- Aggregation, grouping, counting

## Decision 4: Metadata Log Format

**Format**: Git-annex branch stores metadata in `.log.met` files. Each file may
contain multiple lines (log entries), one per metadata update event. The path
encodes the annex key: `1f5/9b3/SHA256E-s6850832--...mp3.log.met`.

**Line format**:
```
<unix-timestamp>s <field1> +<value1> [+<value2>] [-<value3>] <field2> +<value1> ...
```

**Value encoding**:
- `+value` — set this value (plain text, no spaces allowed in plain values)
- `-value` — unset/remove this value
- `+!<base64>` — set a base64-encoded value (used when value contains spaces, special chars, or non-ASCII)
- `-!<base64>` — unset a base64-encoded value

**Examples from real data**:
```
# Simple values (no spaces):
1769651283s album +Gromoviti artist +Psyriots bpm +150.00 rating +5

# Base64-encoded values (contain spaces):
1769651204s artist +!U3BhY2V5ICYgU2xlZXB5IEtvYWxh  → "Spacey & Sleepy Koala"
              title +!VGhpcyBJcyBOb3QgQmFuam8=      → "This Is Not Banjo"

# Multi-value field (crate with two values on same line):
crate +jazzy +psyjazz

# Multi-value field (genre with three values):
genre +darkpsy +experimental +full-on

# Empty field (no values, field name alone):
crate    → field exists but no values set

# Multi-line blob (later entry overrides earlier):
1502762922s genre +ambient
1769651187s genre +Ambient -ambient    → removes "ambient", adds "Ambient"

# Musical key with base64 (contains unicode sharp/flat):
key +!NG0gKEbima9tKQ==  → "4m (F♯m)"
```

**Parser requirements**:
1. Split log entry by spaces into tokens
2. Identify field names (tokens not starting with `+` or `-` and not the timestamp)
3. Collect subsequent `+`/`-` values until the next field name
4. Decode `!`-prefixed values as base64
5. For multi-line blobs: replay chronologically, applying set/unset operations
6. Final state = all `+` values that haven't been `-` removed

## Decision 5: Search Parser Library

**Decision**: Use `lark` for grammar-based parsing of Mixxx search syntax.

**Rationale**: The Mixxx search syntax has enough complexity (field:value, operators, quotes, OR, negation) to warrant a proper grammar rather than regex.

**Alternatives considered**:
- Hand-written recursive descent: Works but harder to maintain.
- Regex tokenizer: Fragile for nested OR groups and quoted strings.
- pyparsing: Similar to lark but less actively maintained.

## Decision 6: Template Engine

**Decision**: Jinja2 for path templates in view export.

**Rationale**: Well-known Python library with filter syntax (`{{ bpm | round_to(10) }}`), good error messages, sandboxed execution.
