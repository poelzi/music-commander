# Git-Annex How-To for Music Libraries

git-annex is the foundation of music-commander. It lets you manage a large music collection across multiple storage locations (NAS, external drives, cloud) while keeping a single git repository as the index. This guide covers practical usage with large music libraries.

## What is git-annex?

git-annex extends git to handle large files. Instead of storing file contents directly in git, it stores them in a content-addressed object store and tracks only symlinks (pointers) in git. The actual content can live on any number of "remotes" -- local drives, NAS, S3, etc.

Key properties:

- **Content-addressed** -- Files are identified by their hash, so duplicates are automatically detected
- **Location tracking** -- git-annex knows which remotes have which files
- **Metadata** -- Arbitrary key-value metadata can be attached to any file (this is what `mixxx sync` uses)
- **Partial clones** -- You don't need all files locally; fetch only what you need

## Setting Up a Music Repository

```bash
# Initialize a new repo
mkdir ~/Music && cd ~/Music
git init
git annex init "laptop"

# Or clone an existing one
git clone ssh://nas/music.git ~/Music
cd ~/Music
git annex init "laptop"
```

## Adding Files

```bash
# Add files to git-annex (large files)
git annex add .
git commit -m "Add music collection"

# Or configure automatic large file handling
echo "* annex.largefiles=largerthan=100kb" >> .gitattributes
git add .gitattributes
git commit -m "Auto-annex files larger than 100kb"
```

With `.gitattributes` configured, `git add` automatically annexes large files while keeping small files (playlists, cue sheets, NFOs) in regular git.

## Remotes

Add remotes to store copies of your files:

```bash
# NAS via SSH
git remote add nas ssh://nas.local/path/to/music
git annex enableremote nas

# External USB drive
git remote add usb /mnt/usb-drive/music
git annex enableremote usb

# Check what remotes exist
git annex info
```

## Fetching and Dropping Content

```bash
# Fetch specific files
git annex get ./darkpsy/

# Fetch from a specific remote
git annex get --from nas ./darkpsy/

# Fetch files from recent commits (music-commander)
music-commander files get-commit HEAD~5..HEAD

# Drop local copies (keep on remotes)
git annex drop ./old-sets/

# Drop with minimum copy check (ensure at least 1 remote has it)
git annex drop --numcopies 1 ./old-sets/
```

## Size Filters

git-annex has powerful filtering for working with large libraries:

```bash
# Find all files larger than 50MB
git annex find --largerthan=50mb

# Find all files smaller than 1MB
git annex find --smallerthan=1mb

# Get only files smaller than 100MB (skip huge WAV files)
git annex get --smallerthan=100mb ./incoming/

# Drop files larger than 200MB to free space
git annex drop --largerthan=200mb

# Combine with metadata filters
git annex find --metadata rating=5 --largerthan=10mb

# Find files not present locally
git annex find --not --in here

# Find files only on one remote
git annex find --in nas --not --in usb
```

## Metadata

git-annex supports arbitrary key-value metadata on annexed files:

```bash
# Set metadata
git annex metadata --set rating=5 ./track.flac
git annex metadata --set genre=darkpsy ./track.flac
git annex metadata --set "crate=Festival Sets" ./track.flac

# Query metadata
git annex find --metadata rating=5
git annex find --metadata genre=darkpsy
git annex find --metadata "crate=Festival Sets"

# View metadata for a file
git annex metadata ./track.flac

# Batch metadata (what music-commander uses internally)
git annex metadata --batch --json
```

music-commander's `mixxx sync` writes these metadata fields automatically from your Mixxx library: `artist`, `title`, `album`, `genre`, `bpm`, `rating`, `key`, `year`, `tracknumber`, `comment`, `color`, `crate`.

## Views

git-annex views let you create filtered directory views based on metadata:

```bash
# View by genre
git annex view "genre=*"

# View by rating
git annex view "rating=5"

# Combined view
git annex view "genre=darkpsy" "rating=5"

# Return to normal
git annex vpop
```

music-commander's `view` command provides more flexibility with Jinja2 templates.

## Preferred Content

Configure which remotes should have which content:

```bash
# Laptop: only want files you're working with
git annex wanted here "include=darkpsy/* or include=sets/*"

# NAS: want everything
git annex wanted nas "anything"

# USB backup: want everything except temporary files
git annex wanted usb "not include=tmp/*"

# Auto-sync based on preferred content
git annex sync --content
```

## Tips for Large Libraries (Multi-TB)

### Use Batch Operations

For collections with tens of thousands of files, always use batch operations:

```bash
# Batch metadata updates (music-commander does this automatically)
music-commander mixxx sync --batch-size 1000

# Parallel fetching
git annex get --jobs 4 ./incoming/
music-commander files get-commit --jobs 4 HEAD~10..HEAD
```

### Clean Up Unused Content

```bash
# Find annexed content no longer referenced by any branch
git annex unused

# Drop unused content
git annex dropunused 1-100

# Or drop all unused
git annex dropunused all
```

### Check Repository Health

```bash
# Verify local content integrity
git annex fsck

# Verify a specific remote
git annex fsck --from nas

# Use music-commander for format-aware checking
music-commander files check --output report.json
```

### .gitattributes for Mixed Content

For repositories that mix large audio files with small text files:

```
# Annex audio files
*.flac annex.largefiles=anything
*.mp3 annex.largefiles=anything
*.wav annex.largefiles=anything
*.aiff annex.largefiles=anything
*.ogg annex.largefiles=anything
*.m4a annex.largefiles=anything
*.ape annex.largefiles=anything
*.wv annex.largefiles=anything

# Keep small files in git directly
*.cue annex.largefiles=nothing
*.nfo annex.largefiles=nothing
*.txt annex.largefiles=nothing
*.m3u annex.largefiles=nothing
*.md annex.largefiles=nothing

# Size-based default for everything else
* annex.largefiles=largerthan=100kb
```

### Disk Space Management

```bash
# Check how much space is used locally
git annex info --fast

# Check space per remote
git annex info nas

# Find largest files
git annex find --largerthan=500mb --format='${bytesize} ${file}\n' | sort -rn | head -20

# Free up space by dropping content available elsewhere
git annex drop --auto
```

## Further Reading

- [git-annex documentation](https://git-annex.branchable.com/)
- [git-annex walkthrough](https://git-annex.branchable.com/walkthrough/)
- [git-annex preferred content](https://git-annex.branchable.com/preferred_content/)
- [git-annex metadata](https://git-annex.branchable.com/metadata/)
- [git-annex tips](https://git-annex.branchable.com/tips/)
