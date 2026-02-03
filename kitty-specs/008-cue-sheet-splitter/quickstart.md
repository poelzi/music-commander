# Quickstart: CUE Sheet Splitter

**Feature**: 008-cue-sheet-splitter

## Prerequisites

Enter the nix dev shell (shntool must be available):

```bash
nix develop
```

## Basic Usage

### Split a single album directory

```bash
music-cmd cue split /path/to/album/
```

The directory should contain a `.cue` file and the corresponding audio file (FLAC, WAV, APE, or WV).

### Preview without splitting

```bash
music-cmd cue split /path/to/album/ --dry-run
```

### Split an entire collection recursively

```bash
music-cmd cue split /path/to/music/ --recursive
```

### Split and clean up originals

```bash
music-cmd cue split /path/to/album/ --remove-originals
```

### Handle non-UTF-8 cue files

```bash
music-cmd cue split /path/to/album/ --encoding cp1252
```

## What it does

1. Finds `.cue` files in the target directory (or tree with `--recursive`)
2. Parses each cue sheet for track boundaries and metadata
3. Splits the source audio file into individual FLAC tracks using shntool
4. Tags each track with metadata from the cue sheet (artist, album, title, track number, genre, date, etc.)
5. Adds ReplayGain tags
6. Embeds cover art from image files found in the directory
7. Optionally removes the original source file and cue sheet
