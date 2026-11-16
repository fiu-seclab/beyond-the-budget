#!/usr/bin/env bash
# Regenerate the tables and figures from the archived episode records.
set -euo pipefail
source "$(dirname "$0")/_py.sh"
mkdir -p figures
"$PY" harness/score_priced.py
"$PY" harness/rq1_figs.py
"$PY" harness/rq2_figs.py
"$PY" harness/rq3_figs.py
