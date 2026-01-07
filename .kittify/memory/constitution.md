<!--
Sync Impact Report
==================
Version change: 0.0.0 → 1.0.0 (MAJOR - initial constitution creation)
Modified principles: N/A (initial creation)
Added sections:
  - Core Principles (6 principles)
  - Development Workflow
  - Quality Gates
  - Governance
Removed sections: N/A
Templates requiring updates:
  - .kittify/missions/software-dev/templates/plan-template.md ✅ (already compatible)
  - .kittify/missions/software-dev/templates/spec-template.md ✅ (already compatible)
  - .kittify/missions/software-dev/templates/tasks-template.md ✅ (already compatible)
Follow-up TODOs: None
-->

# musicCommander Constitution

## Core Principles

### I. Nix-First Packaging (NON-NEGOTIABLE)

All project artifacts MUST be buildable and runnable via Nix flake. This principle ensures reproducible builds and consistent development environments across all contributors.

- The project MUST have a `flake.nix` at the repository root
- All dependencies MUST be declared in the flake, not fetched at runtime
- `nix build`, `nix run`, and `nix develop` MUST work without additional setup
- CI/CD pipelines MUST use Nix for all build and test operations
- Development shells MUST provide all required tools (Python, linters, test runners)

### II. Python Implementation

musicCommander is implemented in Python, targeting modern Python standards for maintainability and ecosystem compatibility.

- Python 3.11+ MUST be the minimum supported version
- Type hints MUST be used for all public interfaces
- Code MUST pass `ruff` linting and `mypy` type checking
- Dependencies MUST be pinned and managed through the Nix flake

### III. CLI Usability

The tool MUST provide an excellent command-line experience with clear subcommands and helpful output.

- MUST use a subcommand structure (e.g., `musicCommander sync`, `musicCommander list`)
- MUST provide colored terminal output for improved readability
- MUST support `--help` at all levels with clear descriptions
- MUST output errors to stderr with actionable messages
- SHOULD support `--json` output for scriptability where applicable
- MUST provide sensible defaults while allowing configuration overrides

### IV. git-annex Integration

The primary purpose is managing large music collections via git-annex, with special consideration for Mixxx DJ software integration.

- MUST handle git-annex operations correctly (get, drop, sync, etc.)
- MUST respect git-annex preferred content settings
- MUST work with both direct and indirect mode repositories
- SHOULD provide Mixxx-specific features (library management, playlist handling)
- MUST handle large file counts efficiently (10,000+ tracks)

### V. Test Coverage

Functionality MUST have test coverage to ensure reliability and enable confident refactoring.

- New features MUST include unit tests before merging
- Integration tests MUST cover git-annex operations using fixtures
- Tests MUST be runnable via `nix flake check`
- Mocking MUST be used for external services (git-annex, filesystem operations in unit tests)
- Test coverage SHOULD be maintained above 80% for core modules

### VI. Simplicity and Pragmatism

Follow YAGNI principles - build what is needed now, not what might be needed later.

- Start with the simplest solution that works
- Avoid premature abstraction; three similar code blocks are acceptable
- Dependencies MUST be justified; prefer standard library when sufficient
- Configuration complexity MUST be proportional to actual use cases

## Development Workflow

### Local Development

1. Enter development shell: `nix develop`
2. Run tests: `pytest` or `nix flake check`
3. Format code: `ruff format .`
4. Type check: `mypy music_commander/`

### Feature Development

1. Create feature branch from `master`
2. Implement with tests
3. Ensure `nix flake check` passes
4. Submit for review

## Quality Gates

All changes MUST pass these gates before merging:

| Gate | Command | Requirement |
|------|---------|-------------|
| Build | `nix build` | Success |
| Tests | `nix flake check` | All pass |
| Lint | `ruff check .` | No errors |
| Types | `mypy music_commander/` | No errors |

## Governance

This constitution defines the non-negotiable principles for musicCommander development. All features, specifications, and implementation plans MUST align with these principles.

**Amendment Process**:
1. Propose changes via pull request to this file
2. Changes require explicit justification
3. Breaking changes to principles require migration plan

**Compliance**:
- All PRs MUST verify compliance with these principles
- The `/spec-kitty.analyze` command validates alignment
- Violations MUST be documented in plan.md Complexity Tracking section with justification

**Version**: 1.0.1 | **Ratified**: 2026-01-06 | **Last Amended**: 2026-01-06
