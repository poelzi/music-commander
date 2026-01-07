#!/usr/bin/env bash
set -euo pipefail

if ! command -v /nix/store/8pd3b2rxdjvzmqb00n0ik3a006dh65q0-spec-kitty-cli-0.9.4/bin/spec-kitty-python >/dev/null 2>&1; then
  echo "Error: /nix/store/8pd3b2rxdjvzmqb00n0ik3a006dh65q0-spec-kitty-cli-0.9.4/bin/spec-kitty-python is required but was not found on PATH." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_HELPER="$SCRIPT_DIR/../tasks/tasks_cli.py"

if [[ ! -f "$PY_HELPER" ]]; then
  echo "Error: tasks_cli helper not found at $PY_HELPER" >&2
  exit 1
fi

/nix/store/8pd3b2rxdjvzmqb00n0ik3a006dh65q0-spec-kitty-cli-0.9.4/bin/spec-kitty-python "$PY_HELPER" history "$@"
