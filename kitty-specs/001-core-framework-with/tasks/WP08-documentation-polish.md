---
work_package_id: "WP08"
subtasks:
  - "T025"
  - "T026"
  - "T027"
  - "T028"
title: "Documentation & Polish"
phase: "Phase 3 - Integration"
lane: "doing"
assignee: ""
agent: ""
shell_pid: ""
review_status: ""
reviewed_by: ""
history:
  - timestamp: "2026-01-06"
    lane: "planned"
    agent: "system"
    shell_pid: ""
    action: "Prompt generated via /spec-kitty.tasks"
---

# Work Package Prompt: WP08 – Documentation & Polish

## Objectives & Success Criteria

- Complete README with installation, configuration, usage
- All --help text is clear and includes examples
- Quickstart scenarios validated end-to-end
- .gitignore covers Python and Nix artifacts
- Project ready for first release

## Context & Constraints

**Constitution Requirements**:
- MUST support `--help` at all levels with clear descriptions
- MUST provide sensible defaults while allowing configuration overrides

**Reference Documents**:
- `kitty-specs/001-core-framework-with/quickstart.md` - User guide to validate
- `kitty-specs/001-core-framework-with/contracts/cli-interface.md` - CLI spec

**Dependencies**: WP07 must be complete (tests passing confirms stability)

## Subtasks & Detailed Guidance

### Subtask T025 – Create README.md

**Purpose**: Primary project documentation for GitHub/users.

**File**: `README.md`

**Implementation**:
```markdown
# music-commander

Manage git-annex based music collections with Mixxx DJ software integration.

## Features

- **git-annex integration**: Fetch music files from commits, branches, or tags
- **Mixxx database access**: Query and manage your Mixxx library programmatically
- **Reproducible builds**: Full Nix flake support for consistent environments
- **Beautiful CLI**: Colored output, progress bars, helpful error messages

## Installation

### Using Nix (recommended)

```bash
# Run directly without installing
nix run github:poelzi/musicCommander -- --help

# Install to your profile
nix profile install github:poelzi/musicCommander

# Enter development environment
nix develop
```

### From Source

```bash
git clone https://github.com/poelzi/musicCommander
cd musicCommander
nix develop
pip install -e .
```

## Configuration

Create `~/.config/music-commander/config.toml`:

```toml
[paths]
mixxx_db = "/path/to/mixxxdb.sqlite"
music_repo = "/path/to/music/repo"

[display]
colored_output = true

[git_annex]
default_remote = "nas"
```

## Usage

### Fetch files from commits

```bash
# Get files from the last commit
music-commander get-commit-files HEAD~1

# Get files from the last 5 commits
music-commander get-commit-files HEAD~5..HEAD

# Preview without fetching
music-commander get-commit-files --dry-run HEAD~3..HEAD
```

### Fetch files from a branch

```bash
# Get all files unique to a feature branch
music-commander get-commit-files feature/summer-playlist
```

### Fetch files from a tag

```bash
# Get files from a tagged release
music-commander get-commit-files v2025-summer-set
```

## Development

```bash
# Enter dev shell
nix develop

# Run tests
pytest

# Type check
mypy music_commander/

# Lint
ruff check .

# Format
ruff format .
```

## License

MIT
```

**Parallel**: Can proceed alongside other subtasks.

### Subtask T026 – Review and refine --help text

**Purpose**: Ensure all CLI help is clear and useful.

**Files to review**:
- `music_commander/cli.py` - Main group help
- `music_commander/commands/get_commit_files.py` - Command help

**Checklist**:
- [ ] Main --help shows all available commands
- [ ] Each command has clear description
- [ ] Examples are included in docstrings
- [ ] Options have helpful descriptions
- [ ] Arguments are clearly explained

**Guidelines**:
- Use `\b` in Click docstrings to preserve formatting
- Include 2-3 realistic examples per command
- Mention default values for options
- Use consistent terminology

**Parallel**: Can proceed alongside other subtasks.

### Subtask T027 – Validate quickstart.md scenarios

**Purpose**: Ensure documented workflows actually work.

**Steps**:
1. Create a test git-annex repository
2. Follow each scenario in `kitty-specs/001-core-framework-with/quickstart.md`
3. Document any discrepancies or needed updates
4. Update quickstart.md if commands have changed

**Scenarios to validate**:
- [ ] `nix run` and `nix develop` work
- [ ] Config file creation and loading
- [ ] `get-commit-files HEAD~1` works
- [ ] `get-commit-files HEAD~5..HEAD` works
- [ ] `get-commit-files --dry-run` works
- [ ] `get-commit-files <branch>` works
- [ ] `get-commit-files <tag>` works

**Parallel**: Can proceed alongside other subtasks.

### Subtask T028 – Create .gitignore

**Purpose**: Ignore build artifacts and generated files.

**File**: `.gitignore`

**Implementation**:
```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Virtual environments
.env
.venv
env/
venv/
ENV/

# IDE
.idea/
.vscode/
*.swp
*.swo
*~

# Testing
.pytest_cache/
.coverage
htmlcov/
.tox/
.nox/

# Mypy
.mypy_cache/
.dmypy.json
dmypy.json

# Ruff
.ruff_cache/

# Nix
result
result-*

# OS
.DS_Store
Thumbs.db

# Project specific
*.sqlite
!tests/fixtures/*.sqlite
```

**Parallel**: Can proceed alongside other subtasks.

## Definition of Done Checklist

- [ ] T025: README.md with complete documentation
- [ ] T026: All --help text reviewed and improved
- [ ] T027: All quickstart scenarios validated
- [ ] T028: .gitignore covers all artifacts
- [ ] README renders correctly on GitHub
- [ ] New user can follow README to install and use
- [ ] No typos or broken links
- [ ] Version numbers consistent throughout

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Documentation drift | Keep docs minimal, link to --help |
| Broken examples | Validate with real commands |
| Missing gitignore patterns | Run `git status` after full build |

## Review Guidance

- Follow README as a new user would
- Run all example commands
- Check `git status` shows no unexpected files
- Verify --help is genuinely helpful

## Activity Log

- 2026-01-06 – system – lane=planned – Prompt created.
