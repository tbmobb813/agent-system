#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
EXE="$ROOT/backend/.venv/bin/pytest"
if [[ ! -x "$EXE" ]]; then
  echo "Missing $EXE" >&2
  echo "Run: cd \"$ROOT/backend\" && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt" >&2
  exit 1
fi
exec "$EXE" "$@"
