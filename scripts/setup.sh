#!/usr/bin/env bash
# Install the packages needed to regenerate tables and figures.
set -euo pipefail
cd "$(dirname "$0")/.."
if python3 -c "import sys" >/dev/null 2>&1; then
  PY=python3
elif python -c "import sys" >/dev/null 2>&1; then
  PY=python
else
  echo "python not found" >&2
  exit 1
fi
"$PY" -m venv .venv
if [[ -x .venv/bin/python ]]; then
  V=.venv/bin/python
else
  V=.venv/Scripts/python.exe
fi
"$V" -m pip install --upgrade pip
"$V" -m pip install -r requirements.txt
echo "Installed. Next: bash scripts/kick-the-tires.sh"
