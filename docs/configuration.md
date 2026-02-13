# Configuration Reference

music-commander is configured via a TOML file at `~/.config/music-commander/config.toml`. Create one with:

```bash
music-commander init-config
```

Override the config path with `--config /path/to/config.toml`.

## Sections

### `[paths]`

| Key | Default | Description |
|-----|---------|-------------|
| `mixxx_db` | `~/.mixxx/mixxxdb.sqlite` | Path to the Mixxx SQLite database |
| `music_repo` | `~/Music` | Path to your git-annex music repository |

### `[display]`

| Key | Default | Description |
|-----|---------|-------------|
| `colored_output` | `true` | Enable colored terminal output. Also controlled by `--no-color` flag or `NO_COLOR` env var |

### `[git_annex]`

| Key | Default | Description |
|-----|---------|-------------|
| `default_remote` | *(unset)* | Preferred remote name for `git annex get` operations (e.g., `"nas"`) |

### `[checks]`

| Key | Default | Description |
|-----|---------|-------------|
| `flac_multichannel` | `false` | Enable FLAC multichannel check for Pioneer CDJ compatibility |

### `[editors]`

| Key | Default | Description |
|-----|---------|-------------|
| `meta_editor` | *(unset)* | External tag editor command (e.g., `"puddletag"`, `"kid3-cli"`) used by `files edit-meta` |

### `[bandcamp]`

| Key | Default | Description |
|-----|---------|-------------|
| `session_cookie` | *(auto-detected)* | Bandcamp identity cookie. Usually extracted automatically via `bandcamp auth` |
| `default_format` | `"flac"` | Preferred download format. Options: `flac`, `mp3-v0`, `mp3-320`, `aac-hi`, `vorbis`, `alac`, `wav`, `aiff-lossless` |
| `match_threshold` | `60` | Fuzzy match confidence threshold (0-100) for `bandcamp match` |

### `[anomalistic]`

| Key | Default | Description |
|-----|---------|-------------|
| `output_dir` | `<music_repo>/Anomalistic` | Output directory for mirrored releases |
| `format` | `"flac"` | Target audio format. Options: `flac`, `mp3-320`, `mp3-v0`, `aiff`, `wav` |
| `output_pattern` | `"{{artist}} - {{album}}"` | Jinja2 template for folder structure. Variables: `artist`, `album`, `genre`, `label`, `year` |
| `download_source` | `"wav"` | Preferred source format from the portal: `wav` or `mp3` |

## Environment Variables

| Variable | Effect |
|----------|--------|
| `NO_COLOR` | Disables colored output (any value) |

## Example

See [config.example.toml](../config.example.toml) for a fully annotated configuration file.
