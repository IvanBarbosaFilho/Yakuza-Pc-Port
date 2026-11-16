#!/usr/bin/env bash
# Decompile IOP code from an IRX at runtime addresses reported by [run:iop-thread] traces.
#   nix develop ./env -c tools/iopdecomp.sh disc/IOP/CRI_ADXI.IRX 0x7a300 0x7ee20 0x7f250
# The base is the module's load address ("[IOP] loaded IRX ... base=0x...").
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PS2RECOMP="${PS2RECOMP:-$ROOT/../PS2Recomp}"
IRX="$(realpath "$1")"; BASE=$(( $2 )); shift 2
NAME="$(basename "$IRX")"
PROJECT="$ROOT/ghidra/iop"
OUT="$ROOT/logs/iopdecomp.c"
mkdir -p "$PROJECT"

addresses=()
for address in "$@"; do
    addresses+=("$(printf '0x%x' $(( address - BASE )))")
done

# Import once per IRX (IRX is ELF type 0xFF80; Ghidra loads its LOAD segment at 0).
if [ ! -e "$PROJECT/iop.rep/idata/~index.dat" ] || ! grep -qa "$NAME" "$PROJECT"/iop.rep/idata/*/*.prp 2>/dev/null; then
    ghidra-analyzeHeadless "$PROJECT" iop -import "$IRX" -processor MIPS:LE:32:default \
        >"$ROOT/logs/iopdecomp-import.log" 2>&1 || true
fi
ghidra-analyzeHeadless "$PROJECT" iop -process "$NAME" -noanalysis -readOnly \
    -scriptPath "$PS2RECOMP/ps2xRecomp/tools/ghidra" \
    -postScript DecompileFunctions.java "$OUT" "${addresses[@]}" >"$ROOT/logs/iopdecomp.log" 2>&1 || true
echo "/* $NAME loaded at 0x$(printf %x $BASE); addresses below are module-relative */"
cat "$OUT"
