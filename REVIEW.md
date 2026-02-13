# Publish Readiness Review

Date: 2026-02-11
Repository: `music-commander`

## Executive Summary

- This pass re-validated previously collected publish-readiness concerns against current repository contents.
- I found 12 reportable items: 11 actionable issues and 1 informational note.
- Severity split: 2 High, 5 Medium, 4 Low, 1 Informational.
- Release blockers to fix before publish: **F01** (dependency drift) and **F03** (batch commit behavior mismatch).
- Validation method: static review (`read`/`grep`/`glob`) only; no full test/lint/typecheck run in this pass.

## Publish Blocker Checklist

- [x] **F01** Add missing runtime dependency parity between `pyproject.toml` and `flake.nix`. *(addressed prior to review session)*
- [x] **F03** Fix `mixxx sync --batch-size` to commit every N synced files (as documented). *(addressed prior to review session)*
- [x] **F02** DRY init-config: sourced from `config.example.toml` via `importlib.resources`; fixed docs URL.
- [x] **F04** Checker timeout: single `_CHECKER_TIMEOUT` constant for subprocess and error message.
- [x] **F05** Search query docstring: removed false FTS-to-LIKE fallback claim.
- [x] **F06** CLAUDE.md parser strategy: corrected LALR → Earley.
- [x] **F07** README typo: "never loose" → "never lose".
- [x] **F08** Cue splitter: `check_tools_available()` returns `(required, optional)` tuple; ffmpeg is optional; new `check-deps` command.
- [x] **F09** Bandcamp client: added `stream_get()` method; downloader uses shared session.
- [x] **F10** ReportServer: added `wait()` public API; removed `_thread` access.
- [x] **F11** Full docs/ content: 10 documentation files covering install, config, commands, search DSL, Bandcamp workflow, git-annex, troubleshooting, contributing, release process.
- [x] **F12** .gitignore: added intent comment for `TODOs` entry.
- [x] Run release gate checks after fixes: `nix develop --command pytest`, `nix develop --command ruff check .`, `nix develop --command mypy music_commander/`, `nix flake check`.

## Detailed Findings

| ID | Priority | Issue | Evidence | Publish Impact | Concrete Fix |
| --- | --- | --- | --- | --- | --- |
| F01 | High | Runtime dependency drift: `rapidfuzz` is declared in package metadata but not in Nix runtime deps. | `pyproject.toml:31`, `flake.nix:74`, `flake.nix:77`, `flake.nix:88` | Nix-based package/runtime can fail with `ModuleNotFoundError` on paths that require fuzzy matching. | Add `rapidfuzz` to `pythonDeps` in `flake.nix`; add a smoke test/import check in `flake check` path to ensure parity. |
| F02 | Medium | `init-config` template is stale/incomplete and contains a broken docs URL. | `music_commander/commands/init_config.py:37`, `music_commander/commands/init_config.py:70`, `music_commander/commands/init_config.py:72`, `config.example.toml:19`, `config.example.toml:27`, `config.example.toml:38` | New users get an incomplete starter config and a dead/incorrect documentation link. | Update template to include all current sections/options (or source it from `config.example.toml`); fix URL to `https://github.com/poelzi/music-commander`; add unit tests for generated content coverage. |
| F03 | High | `mixxx sync --batch-size` intermediate commit logic does not run per batch. | `music_commander/commands/mixxx.py:365`, `music_commander/commands/mixxx.py:468` | Behavior differs from CLI contract; large syncs may accumulate too many staged metadata changes before commit. | Move commit threshold check into the per-track sync loop and track synced count correctly; keep final merge behavior; add a unit test asserting expected `commit()` call frequency. |
| F04 | Low | Checker timeout duration and timeout error message disagree (`600` vs `300`). | `music_commander/utils/checkers.py:622`, `music_commander/utils/checkers.py:644` | Misleading diagnostics for long-running checks. | Define a single timeout constant and reuse it for both `subprocess.run(..., timeout=...)` and error text. |
| F05 | Medium | Search query code documents FTS-to-LIKE fallback, but runtime fallback is not implemented in `_build_text_term_clause`. | `music_commander/search/query.py:45`, `music_commander/search/query.py:46`, `music_commander/search/query.py:54`, `music_commander/search/query.py:57` | If FTS table is missing/broken, search can fail hard instead of degrading gracefully. | Either implement operational fallback (catch DB/FTS errors and route to `_build_text_term_clause_like`) or remove fallback claim and guarantee FTS schema creation with explicit checks/migrations. Add tests in `tests/unit/test_search_query.py`. |
| F06 | Low | Parser strategy documentation mismatch: internal docs say LALR, code uses Earley. | `music_commander/search/parser.py:51`, `CLAUDE.md:52` | Contributor confusion and inaccurate architecture guidance. | Update docs to match implementation, or switch parser mode intentionally and update tests/docs together. |
| F07 | Low | README typo: "never loose" should be "never lose". | `README.md:7` | Polish/credibility issue in primary project page. | Correct wording in `README.md`. |
| F08 | Medium | Cue splitting dependency contract is unclear: ffmpeg fallback exists, but command hard-requires `shntool` + `metaflac`. | `music_commander/cue/splitter.py:3`, `music_commander/cue/splitter.py:4`, `music_commander/cue/splitter.py:77`, `music_commander/cue/splitter.py:84`, `README.md:290`, `README.md:291` | Users may be blocked unexpectedly or misled about which tools are truly required. | Decide and document one contract: (A) require `shntool` explicitly everywhere, or (B) make tool checks backend-aware and allow ffmpeg-only operation where feasible; add command tests in `tests/unit/test_cmd_cue_split.py`. |
| F09 | Medium | Bandcamp download path bypasses shared client session/retry/rate-limit logic. | `music_commander/bandcamp/downloader.py:142`, `music_commander/bandcamp/client.py:100`, `music_commander/bandcamp/client.py:103`, `music_commander/bandcamp/client.py:105`, `music_commander/bandcamp/client.py:131` | Inconsistent HTTP behavior (auth, retries, rate limiting) between metadata and file download flows. | Introduce a download method on `BandcampClient` that reuses `_session` and limiter policy; refactor downloader to call it; add tests around retry/auth failure behavior. |
| F10 | Low | Bandcamp report command reaches private implementation detail (`server._thread`). | `music_commander/commands/bandcamp/report.py:294`, `music_commander/commands/bandcamp/report.py:467` | Encapsulation leak increases maintenance risk and makes refactors brittle. | Add public server lifecycle API (`join()`/`wait_until_stopped()`/`is_running`) and consume that from CLI code. |
| F11 | Medium | `docs/` is effectively empty for publish-level documentation needs. | `docs/.gitkeep` | Increases support burden and weakens release readiness for new users/contributors. | Add at least: release process, support matrix/system deps, troubleshooting, Bandcamp cookie/privacy notes, and deeper command reference pages. |
| F12 | Low | `.gitignore` contains unusual broad/specialized entries that need intent confirmation. | `.gitignore:15`, `.gitignore:92` | Risk of accidentally hiding useful artifacts from version control. | Confirm intent; if local-only, move to user-level excludes; if repo policy, document rationale in `CONTRIBUTING.md`/README. |
| F13 | Informational | TODO/FIXME scan in product code/docs found no unresolved markers. | Scan scope: `music_commander/**/*.py`, `tests/**/*.py`, `README.md`, `config.example.toml` | Positive signal for publish hygiene. | No action needed. |

## Items Not Reproduced From Earlier Notes

- README references to `music-cmd` were **not** present in the currently checked file.
- "Roadmap already implemented" concern was not conclusively validated in this pass.

## Suggested Release-Prep Plan (Ordered)

1. Fix blockers **F01** and **F03** first, with unit tests.
2. Address behavior/documentation mismatches **F02**, **F05**, **F08**, and HTTP consistency in **F09**.
3. Apply quick polish fixes **F04**, **F06**, **F07**, **F10**, **F12**.
4. Fill `docs/` baseline content for publish readiness (**F11**).
5. Run release gate commands and capture outcomes in release notes/PR description.
6. Perform one end-to-end smoke pass of core flows (`mixxx sync --dry-run`, `search`, `bandcamp report --no-server`, `cue split --dry-run`).
7. Cut release only after blockers and gate checks are green.
