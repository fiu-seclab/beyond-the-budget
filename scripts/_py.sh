#!/usr/bin/env bash
# Resolve the repo root and a Python interpreter. Sourced by the other scripts.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# The Windows "python3" app-execution alias can exist and still fail.
works() { "$1" -c "import sys" >/dev/null 2>&1; }

if [[ -x "$ROOT/.venv/bin/python" ]] && works "$ROOT/.venv/bin/python"; then
  PY="$ROOT/.venv/bin/python"
elif [[ -x "$ROOT/.venv/Scripts/python.exe" ]] && works "$ROOT/.venv/Scripts/python.exe"; then
  PY="$ROOT/.venv/Scripts/python.exe"
elif works python3; then
  PY=python3
elif works python; then
  PY=python
else
  echo "python not found" >&2
  exit 1
fi
