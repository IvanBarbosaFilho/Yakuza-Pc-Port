#!/usr/bin/env bash
# Decompile functions of the PC port (sh3.exe) from the user's Ghidra project, read-only.
#   nix develop ./env -c tools/pcdecomp.sh 0x454150 ...   -> stdout (also logs/pcdecomp.c)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PS2RECOMP="${PS2RECOMP:-$ROOT/../PS2Recomp}"
PC_GHIDRA="${PC_GHIDRA:-$HOME/Silent-Hill-3---Fix/mods/re/ghidra}"
OUT="$ROOT/logs/pcdecomp.c"
ghidra-analyzeHeadless "$PC_GHIDRA" sh3 -process sh3.exe -noanalysis -readOnly \
    -scriptPath "$PS2RECOMP/ps2xRecomp/tools/ghidra" \
    -postScript DecompileFunctions.java "$OUT" "$@" >"$ROOT/logs/pcdecomp.log" 2>&1 || true
cat "$OUT"
