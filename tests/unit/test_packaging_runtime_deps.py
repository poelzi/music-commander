"""Tests for runtime dependency parity between package metadata and Nix."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _requirement_name(requirement: str) -> str:
    match = re.match(r"[A-Za-z0-9_.-]+", requirement)
    assert match is not None
    return match.group(0).lower().replace("_", "-")


def test_flake_runtime_deps_cover_pyproject_runtime_deps() -> None:
    """flake.nix pythonDeps should cover all pyproject runtime deps."""
    repo_root = _repo_root()

    pyproject_data = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))
    dependency_names = {
        _requirement_name(requirement)
        for requirement in pyproject_data["project"]["dependencies"]
    }

    # rookiepy is provided by a custom derivation and appended separately.
    dependency_names.discard("rookiepy")

    flake_text = (repo_root / "flake.nix").read_text(encoding="utf-8").lower()
    runtime_block = flake_text.split("pythondeps =", maxsplit=1)[1].split(
        "# development dependencies", maxsplit=1
    )[0]

    for dependency_name in sorted(dependency_names):
        assert dependency_name in runtime_block, (
            f"Dependency '{dependency_name}' exists in pyproject.toml but is missing "
            "from flake.nix pythonDeps."
        )
