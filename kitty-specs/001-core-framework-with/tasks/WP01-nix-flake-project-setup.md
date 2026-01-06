---
work_package_id: "WP01"
subtasks:
  - "T001"
  - "T002"
  - "T003"
  - "T004"
title: "Nix Flake & Project Setup"
phase: "Phase 1 - Foundation"
lane: "for_review"
assignee: "claude"
agent: "claude"
shell_pid: "1112538"
review_status: ""
reviewed_by: ""
history:
  - timestamp: "2026-01-06"
    lane: "planned"
    agent: "system"
    shell_pid: ""
    action: "Prompt generated via /spec-kitty.tasks"
  - timestamp: "2026-01-06T19:45:00Z"
    lane: "doing"
    agent: "claude"
    shell_pid: "1112538"
    action: "Started implementation of Nix flake and project setup"
  - timestamp: "2026-01-06T19:50:00Z"
    lane: "for_review"
    agent: "claude"
    shell_pid: "1112538"
    action: "Completed implementation. All tasks (T001-T004) done. Tests: nix run --version and --help both work."
---

# Work Package Prompt: WP01 – Nix Flake & Project Setup

## Objectives & Success Criteria

- Create a fully functional Nix flake that provides reproducible builds
- `nix develop` enters a shell with Python 3.11 and all dependencies
- `nix build` produces a working `music-commander` executable
- `nix flake check` runs pytest (even if no tests yet, the framework works)
- Package installs correctly with entry point `music-commander`

## Context & Constraints

**Constitution Requirements**:
- Principle I: Nix-First Packaging is NON-NEGOTIABLE
- `nix build`, `nix run`, `nix develop` MUST work without additional setup
- All dependencies declared in flake, not fetched at runtime

**Reference Documents**:
- `.kittify/memory/constitution.md` - Project principles
- `kitty-specs/001-core-framework-with/research.md` - Technology decisions
- `kitty-specs/001-core-framework-with/plan.md` - Architecture overview

**Dependencies**: Click, Rich, SQLAlchemy 2.0, tomli-w, pytest, ruff, mypy

## Subtasks & Detailed Guidance

### Subtask T001 – Create flake.nix

**Purpose**: Establish reproducible build environment with Nix.

**Steps**:
1. Create `flake.nix` at repository root
2. Define inputs: nixpkgs (unstable), flake-utils
3. Create Python environment with Python 3.11
4. Define outputs:
   - `packages.default`: buildPythonApplication for music-commander
   - `devShells.default`: development shell with all tools
   - `checks.default`: pytest execution

**File**: `flake.nix`

**Implementation**:
```nix
{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python311;
        
        # Runtime dependencies
        pythonDeps = ps: with ps; [
          click
          rich
          sqlalchemy
          tomli-w
        ];
        
        # Development dependencies
        devDeps = ps: with ps; [
          pytest
          pytest-cov
          mypy
          ruff
        ];
        
        pythonEnv = python.withPackages (ps: (pythonDeps ps) ++ (devDeps ps));
        
      in {
        packages.default = python.pkgs.buildPythonApplication {
          pname = "music-commander";
          version = "0.1.0";
          src = ./.;
          format = "pyproject";
          
          nativeBuildInputs = with python.pkgs; [
            setuptools
          ];
          
          propagatedBuildInputs = pythonDeps python.pkgs;
          
          # Skip tests during build (run via checks)
          doCheck = false;
        };

        devShells.default = pkgs.mkShell {
          buildInputs = [ 
            pythonEnv 
            pkgs.git-annex
          ];
          
          shellHook = ''
            export PYTHONPATH="$PWD:$PYTHONPATH"
          '';
        };

        checks.default = pkgs.runCommand "pytest" {
          buildInputs = [ pythonEnv ];
        } ''
          cd ${./.}
          pytest --tb=short
          touch $out
        '';
      });
}
```

**Notes**: The check will fail initially until tests exist, which is expected.

### Subtask T002 – Create pyproject.toml

**Purpose**: Define Python package metadata and entry point.

**Steps**:
1. Create `pyproject.toml` at repository root
2. Define project metadata (name, version, description, authors)
3. Configure entry point for CLI
4. Add tool configurations for ruff and mypy

**File**: `pyproject.toml`

**Implementation**:
```toml
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "music-commander"
version = "0.1.0"
description = "Manage git-annex based music collections with Mixxx integration"
readme = "README.md"
requires-python = ">=3.11"
license = {text = "MIT"}
authors = [
    {name = "poelzi"}
]
dependencies = [
    "click>=8.0",
    "rich>=13.0",
    "sqlalchemy>=2.0",
    "tomli-w>=1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
    "mypy>=1.0",
    "ruff>=0.1",
]

[project.scripts]
music-commander = "music_commander.cli:cli"

[tool.setuptools.packages.find]
where = ["."]
include = ["music_commander*"]

[tool.ruff]
target-version = "py311"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP"]

[tool.mypy]
python_version = "3.11"
strict = true
warn_return_any = true
warn_unused_ignores = true
```

### Subtask T003 – Create music_commander/__init__.py

**Purpose**: Initialize package with version information.

**Steps**:
1. Create `music_commander/` directory
2. Create `__init__.py` with version constant

**File**: `music_commander/__init__.py`

**Implementation**:
```python
"""music-commander: Manage git-annex based music collections with Mixxx integration."""

__version__ = "0.1.0"
__all__ = ["__version__"]
```

**Parallel**: Can proceed alongside T004.

### Subtask T004 – Create music_commander/__main__.py

**Purpose**: Enable `python -m music_commander` execution.

**Steps**:
1. Create `__main__.py` that imports and runs the CLI

**File**: `music_commander/__main__.py`

**Implementation**:
```python
"""Entry point for python -m music_commander."""

from music_commander.cli import cli

if __name__ == "__main__":
    cli()
```

**Notes**: cli.py doesn't exist yet; this will be created in WP04. For now, create a stub cli.py:

**File**: `music_commander/cli.py` (temporary stub)
```python
"""CLI stub - replaced in WP04."""

import click

@click.group()
@click.version_option()
def cli() -> None:
    """music-commander: Manage git-annex music collections."""
    pass
```

**Parallel**: Can proceed alongside T003.

## Definition of Done Checklist

- [ ] T001: flake.nix exists and `nix develop` works
- [ ] T002: pyproject.toml defines package correctly
- [ ] T003: music_commander/__init__.py with __version__
- [ ] T004: music_commander/__main__.py entry point works
- [ ] `nix build` produces executable
- [ ] `nix run . -- --version` shows version
- [ ] `nix run . -- --help` shows help text
- [ ] Package directory structure matches plan.md

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Nix Python packaging complex | Follow nixpkgs python patterns exactly |
| Version mismatch __init__ vs pyproject | Single source of truth in pyproject.toml |
| Missing dependencies | Test `nix build` from clean state |

## Review Guidance

- Verify `nix develop` provides Python 3.11 with all deps
- Verify `nix build` succeeds from clean clone
- Check entry point works: `./result/bin/music-commander --help`
- Ensure no hardcoded paths in flake.nix

## Activity Log

- 2026-01-06 – system – lane=planned – Prompt created.
