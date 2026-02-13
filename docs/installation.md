# Installation

## System Requirements

- **Python** 3.13 or later
- **git** and **git-annex** (core functionality)
- **ffmpeg** and **ffprobe** (audio processing)
- **libmagic** (file type detection via python-magic)

Optional tools for specific features:

| Tool | Feature | Install |
|------|---------|---------|
| `flac` | FLAC integrity checking | `apt install flac` |
| `mp3val` | MP3 integrity checking | `apt install mp3val` |
| `ogginfo` | OGG integrity checking | `apt install vorbis-tools` |
| `sox` | WAV/AIFF integrity checking | `apt install sox` |
| `shntool` | CUE sheet splitting | `apt install shntool` |
| `metaflac` | FLAC tagging and analysis | Included with `flac` |
| `unrar` | RAR extraction (Anomalistic mirror) | `apt install unrar-free` |
| `firefox` | Bandcamp browser authentication | System package |

Run `music-commander check-deps` to verify which tools are available on your system.

## Using Nix (Recommended)

Nix provides all dependencies automatically, including git-annex, ffmpeg, and audio tools.

```bash
# Run directly without installing
nix run github:poelzi/music-commander -- --help

# Install to your profile
nix profile install github:poelzi/music-commander

# Enter development environment (includes all system deps)
nix develop
```

## Using pip

Install system dependencies first, then install music-commander.

### Debian / Ubuntu

```bash
sudo apt install git git-annex ffmpeg libmagic1 flac vorbis-tools shntool sox
pip install .
```

### Arch Linux

```bash
sudo pacman -S git git-annex ffmpeg file flac vorbis-tools shntool sox
pip install .
```

### macOS (Homebrew)

```bash
brew install git git-annex ffmpeg libmagic flac vorbis-tools shntool sox
pip install .
```

### Isolated Install with pipx

```bash
pipx install .
```

## From Source (Development)

```bash
git clone https://github.com/poelzi/music-commander
cd music-commander

# With Nix (recommended -- includes all deps):
nix develop
pip install -e .

# Without Nix (requires system deps above):
pip install -e ".[dev]"
```

See [Contributing](contributing.md) for development setup details.
