#!/usr/bin/env sh
# Bootstrap Git dependencies only; public dependency installation is unchanged.
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"
exec python3 "$ROOT/scripts/install_requirements.py" --git-only requirements.txt
