# Research: Anomalistic Portal Mirror

**Feature**: 009-anomalistic-portal-mirror
**Date**: 2026-02-03

## R1: WordPress REST API Structure

**Decision**: Use `wp-json/wp/v2/posts` (paginated, `per_page=100`) and `wp-json/wp/v2/categories` (`per_page=100`) endpoints.

**Rationale**: The portal's WordPress REST API is fully public, returns structured JSON with rendered HTML content containing download links. Three API calls fetch the full catalog (~278 releases). Categories endpoint returns all 80 categories in one call.

**Alternatives considered**:
- HTML page scraping: Rejected — REST API provides cleaner structured data.
- WordPress XML-RPC: Rejected — REST API is more modern and already accessible.

**Key findings**:
- Posts endpoint returns `id`, `title.rendered`, `content.rendered`, `date`, `categories` (array of IDs), `link`.
- Categories endpoint returns `id`, `name`, `slug`, `count`.
- Pagination via `page` parameter; `per_page` max 100. Total pages in `X-WP-TotalPages` header.
- Download URLs embedded in `content.rendered` HTML as `<a href="...">` links pointing to `www.anomalisticrecords.com/[artist]/...`.

## R2: Download URL Extraction from HTML Content

**Decision**: Use BeautifulSoup4 to parse `content.rendered` and extract `<a>` tags with `href` pointing to `www.anomalisticrecords.com` containing archive file extensions (`.zip`, `.rar`).

**Rationale**: BS4 is already a project dependency. The HTML structure is WordPress-generated and consistent. Links follow a pattern: `https://www.anomalisticrecords.com/[artist]/Artist%20-%20Album%20-%20FORMAT.zip` (or `.rar`).

**Alternatives considered**:
- Regex: Rejected — fragile with HTML, BS4 handles edge cases.

**Key findings**:
- WAV links contain `WAV.zip` in the URL.
- MP3 links contain `MP3.zip` in the URL.
- Some releases have RAR archives (single download link, no format variants).
- Some releases may have only a "DOWNLOAD" link without format indication.

## R3: Category Classification (Genres vs Labels)

**Decision**: Hardcode a `GENRE_IDS` set containing the known genre category IDs. Categories not in `GENRE_IDS` and not in `IGNORED_IDS` are classified as labels.

**Rationale**: The genre set is small (~17 entries) and stable — the portal has existed since 2013 with the same style categories. New genres can be added by updating the set.

**Genre IDs** (from portal API):
- 7: Psycore, 8: Experimental, 9: DarkPsy, 10: Psytrance, 11: DownTempo, 12: Hi-Tech, 14: Horrordelic, 15: ForestCore, 16: Squirrel, 28: Full-On, 29: Morning, 30: Independent, 33: Forest, 44: Ambient, 47: IDM, 48: Dark Techno, 69: Swamp

**Ignored IDs**: 1 (Uncategorized), 3 (All Releases), 6 (Nerdy Psouth), 42 (P)

**Everything else**: Labels (record label names).

## R4: Shared Matching Module Extraction

**Decision**: Extract core matching primitives from `music_commander/bandcamp/matcher.py` into `music_commander/utils/matching.py`.

**Rationale**: DRY — the anomalistic dedup logic needs the same string normalization and scoring functions. The bandcamp matcher retains its multi-phase orchestration; only stateless scoring functions move.

**Functions to extract**:
- All regex patterns: `_MULTI_SPACE`, `_NON_ALNUM_SPACE`, `_EDITION_SUFFIX`, `_ZERO_WIDTH`, `_GUILLEMETS`, `_CATALOG_BRACKET`, `_DASHES`, `_NOISE_PHRASES`, `_VOLUME_PATTERN`
- Roman numeral utilities: `_ROMAN_MAP`, `_roman_to_int()`, `extract_volume()`
- Normalization: `normalize()`, `strip_punctuation()`, `strip_edition_suffixes()`, `normalize_for_matching()`
- Scoring: `match_release()`, `match_track()`

**Bandcamp matcher changes**: Replace local definitions with imports from `utils/matching.py`. Higher-level functions (`match_releases()`, phase logic, `MatchReport`) stay in `bandcamp/matcher.py`.

## R5: Comment Metadata in FFmpeg Commands

**Decision**: Extend `build_ffmpeg_command()` in `encoder.py` to accept an optional `extra_metadata: dict[str, str] | None` parameter. Insert `-metadata key=value` flags into the command.

**Rationale**: Current implementation has no mechanism for custom metadata. The `-metadata comment=URL` flag must come after `-map_metadata 0` in the ffmpeg command to override any existing comment tag.

**Alternatives considered**:
- Post-processing with mutagen/taglib: Rejected — adds dependency, ffmpeg handles it natively.
- Custom FormatPreset with comment in ffmpeg_args: Rejected — URL varies per release, not per preset.

## R6: RAR Extraction via unrar

**Decision**: Use `unrar-free` from nixpkgs (`pkgs.unrar-free`), invoked via subprocess.

**Rationale**: The user specified "unrar (free rar)" — the free/libre implementation. Available in nixpkgs as `unrar-free`. Called via `subprocess.run(["unrar", "x", archive_path, output_dir])`.

**Alternatives considered**:
- `pkgs.unrar` (proprietary): Rejected — user specified free implementation.
- `pkgs.unar` (TheUnarchiver): Rejected — different CLI interface, user specified unrar.
- Python `rarfile` library: Rejected — still requires `unrar` binary, adds unnecessary wrapper.

## R7: Title Parsing Strategy

**Decision**: Split post title on first occurrence of em-dash (`\u2013`), en-dash (`\u2013`), or ` - ` (space-hyphen-space). Left = artist, right = album. Recognize `V/A` and `VA` prefixes.

**Rationale**: Portal titles consistently use `Artist – Album` with an em-dash. Fallback to en-dash and space-hyphen-space for edge cases.

**Parsing rules**:
1. Strip HTML entities from `title.rendered` (WordPress may encode special chars).
2. Check for `V/A` or `VA` prefix → artist = "Various Artists", remainder = album.
3. Split on first em-dash, en-dash, or ` - `.
4. If no delimiter found, artist = "Various Artists", full title = album.
5. Strip leading/trailing whitespace from both parts.

## R8: Folder Pattern Rendering

**Decision**: Use Jinja2 `Environment` with `undefined=StrictUndefined` for folder pattern rendering. Variables: `genre`, `label`, `artist`, `album`, `year`. Sanitize rendered path for filesystem safety.

**Rationale**: Jinja2 is already a project dependency. `StrictUndefined` catches typos in patterns. The `{% if %}` syntax handles optional segments naturally.

**Default pattern**: `{{artist}} - {{album}}`

**Sanitization**: Replace `/` in variable values (not pattern delimiters), strip leading/trailing dots and spaces, replace reserved filesystem characters (`<>:"|?*`).
