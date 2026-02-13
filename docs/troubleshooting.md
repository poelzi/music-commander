# Troubleshooting

## Missing External Tools

**Symptom:** Commands fail with "command not found" or cryptic subprocess errors.

**Fix:** Run `music-commander check-deps` to see which tools are missing and which commands need them. Install missing tools via your package manager or use `nix develop` for a complete environment.

```bash
# Check all dependencies
music-commander check-deps

# Enter Nix shell with all deps
nix develop
```

## git-annex Not Initialized

**Symptom:** "Not a git-annex repository" error.

**Fix:** Initialize git-annex in your music repository:

```bash
cd ~/Music
git annex init "my-machine"
```

If the repo was cloned, you may need to enable the remote:

```bash
git annex enableremote origin
```

## Mixxx Database Not Found

**Symptom:** "Could not find Mixxx database" or sync produces no results.

**Fix:** Check the path in your config:

```toml
[paths]
mixxx_db = "~/.mixxx/mixxxdb.sqlite"
```

Common locations:
- Linux: `~/.mixxx/mixxxdb.sqlite`
- macOS: `~/Library/Containers/org.mixxx.mixxx/Data/Library/Application Support/Mixxx/mixxxdb.sqlite`
- Flatpak: `~/.var/app/org.mixxx.Mixxx/data/mixxx/mixxxdb.sqlite`

Ensure Mixxx is not running (its database uses WAL mode, which supports concurrent reads, but the path must be correct).

## Bandcamp Cookie Expired

**Symptom:** `BandcampAuthError: Bandcamp authentication failed. Your session cookie may have expired.`

**Fix:** Re-authenticate:

```bash
music-commander bandcamp auth --browser firefox
```

If auto-extraction fails, log in to Bandcamp in your browser first:

```bash
music-commander bandcamp auth --login --browser firefox
```

## Stale Search Cache

**Symptom:** Search results don't include recently synced tracks.

**Fix:** The cache refreshes automatically on search by checking the git-annex branch HEAD. If it seems stale, force a rebuild:

```bash
music-commander rebuild-cache
```

The cache file is at `<music_repo>/.music-commander-cache.db`. You can safely delete it and it will be rebuilt on next search.

## Colored Output Issues

**Symptom:** Garbled terminal output or unwanted color codes in pipes.

**Fix:** Disable colors:

```bash
# Via flag
music-commander --no-color search "dark"

# Via environment variable
export NO_COLOR=1

# Via config
[display]
colored_output = false
```

## Permission Errors on Cache

**Symptom:** `OSError: [Errno 13] Permission denied: '.music-commander-cache.db'`

**Fix:** The cache is stored in your music repo directory. Ensure you have write permissions:

```bash
ls -la ~/Music/.music-commander-cache.db
```

## Slow Operations on Large Libraries

**Symptom:** Commands take a long time on large collections (50k+ files).

**Tips:**
- Use `--batch-size` with `mixxx sync` to commit incrementally
- Use `--jobs` with `files check` and `files get-commit` for parallelism
- The search cache makes repeated queries fast; initial build may take a minute
- Use `--limit` with `search` to cap result count

## CUE Split Missing Tools

**Symptom:** `cue split` exits with "Missing required tools: shntool"

**Fix:** Install shntool and metaflac:

```bash
# Debian/Ubuntu
sudo apt install shntool flac

# Arch
sudo pacman -S shntool flac

# Or use nix develop
nix develop
```

If you see a warning about ffmpeg, that's only needed for APE/WavPack source files.
