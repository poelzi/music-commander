# Data Model: CUE Sheet Splitter

**Feature**: 008-cue-sheet-splitter
**Date**: 2026-02-03

## Entities

### CueSheet

Represents a fully parsed cue file with global metadata and track list.

| Field | Type | Description |
|-------|------|-------------|
| performer | str | Global artist/performer (default: "Unknown") |
| album | str | Album title (default: "Unknown") |
| genre | str \| None | Genre from REM GENRE |
| date | str \| None | Year/date from REM DATE |
| songwriter | str \| None | Songwriter from SONGWRITER |
| disc_id | str \| None | Disc ID from REM DISCID |
| comment | str \| None | Comment from REM COMMENT |
| file | str \| None | Source audio filename from FILE command |
| tracks | list[CueTrack] | Ordered track list |

### CueTrack

Single track within a cue sheet. Inherits global fields, can override performer/songwriter.

| Field | Type | Description |
|-------|------|-------------|
| track_num | int | Track number (1-based) |
| title | str | Track title |
| performer | str | Artist (track-level or inherited from global) |
| songwriter | str \| None | Track songwriter |
| isrc | str \| None | ISRC code |
| index | str | Raw index timestring (mm:ss:ff) |
| start_samples | int | Start position in samples at 44100Hz |
| end_samples | int \| None | End position in samples (None = end of file) |
| genre | str \| None | Inherited from global |
| date | str \| None | Inherited from global |
| album | str | Inherited from global |
| disc_id | str \| None | Inherited from global |

### SplitResult

Outcome of processing one cue/file pair.

| Field | Type | Description |
|-------|------|-------------|
| source_path | Path | Source audio file path |
| cue_path | Path | Cue file path |
| track_count | int | Number of tracks defined in cue |
| output_files | list[Path] | Created track file paths |
| status | str | "ok" \| "skipped" \| "error" |
| error | str \| None | Error message if status is "error" |

## Relationships

- CueSheet → CueTrack: one-to-many (ordered)
- CueSheet → source file: one-to-one (or one-to-many for multi-FILE cue sheets)
- SplitResult → CueSheet: one-to-one (processing result for one cue)

## Tag Mapping (CueTrack → FLAC metadata)

| CueTrack field | FLAC tag |
|----------------|----------|
| performer | ARTIST |
| album | ALBUM |
| title | TITLE |
| track_num | TRACKNUMBER |
| genre | GENRE |
| date | DATE |
| songwriter | SONGWRITER |
| isrc | ISRC |
| disc_id | DISCID |
