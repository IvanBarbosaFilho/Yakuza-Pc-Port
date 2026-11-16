#!/usr/bin/env bash
# List functions referencing strings that contain the given text, using the pipeline's Ghidra project.
#   nix develop ./env -c tools/strrefs.sh iop_modules ioprp   -> prints to stdout (also logs/strrefs.txt)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
. "$ROOT/tools/game.sh"
PS2RECOMP="${PS2RECOMP:-$ROOT/../PS2Recomp}"
OUT="$ROOT/logs/strrefs.txt"

ghidra-analyzeHeadless "$ROOT/ghidra" "$GAME" -process "$ELF_NAME" -noanalysis -readOnly \
    -scriptPath "$PS2RECOMP/ps2xRecomp/tools/ghidra" \
    -postScript FindStringRefs.java "$OUT" "$@" >"$ROOT/logs/strrefs.log" 2>&1 || true
cat "$OUT"
