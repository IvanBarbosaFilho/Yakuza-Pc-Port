#!/usr/bin/env bash
# Reproducible test scenarios: one command per hypothesis, results kept per run.
#
#   tools/scenario.sh gameplay [options]     load slot 1 of disc/mc0, play (step 5)
#   tools/scenario.sh newgame  [options]     New Game from the title
# options:
#   --core lean,accurate,...   VU1 core(s) (PS2X_VU1_CORE); several = A/B, one run each + table
#   --seconds N                run time (default 240)
#   --delay N                  vsyncs after play starts for --capture/--dump (default 600)
#   --capture                  GS frame capture with per-pass VRAM at play+delay
#   --dump                     RAM/SPR/VU0/VU1 dump at play+delay
#   --baseline save|check      store this run's numbers as the scenario's baseline, or compare
#                              against it and list what got worse (exit 3)
#   -e NAME=VALUE              extra environment for the runner (repeatable)
# Results: logs/scenarios/<scenario>-<core>/ (run.log, run.report, metrics.json, frames.txt,
# capture/dump files). Conditions are on game state (step stack 0x34eca8 = 5: playing), not on
# frame numbers, because run timing differs from run to run.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PS2RECOMP="${PS2RECOMP:-$ROOT/../PS2Recomp}"
# Outside the dev shell python3 and friends are missing: re-enter it.
command -v python3 >/dev/null || exec nix develop "$ROOT/env" -c "$0" "$@"
. "$ROOT/config/run.env"

scenario=${1:?usage: scenario.sh gameplay|newgame [options]}
shift
cores="" seconds=240 delay=600 capture=0 dump=0 baseline="" extra=()
while [ $# -gt 0 ]; do
    case "$1" in
        --core) cores=$2; shift ;;
        --seconds) seconds=$2; shift ;;
        --delay) delay=$2; shift ;;
        --capture) capture=1 ;;
        --dump) dump=1 ;;
        --baseline) baseline=$2; shift ;;
        -e) extra+=("$2"); shift ;;
        *) echo "unknown option $1" >&2; exit 2 ;;
    esac
    shift
done

case "$scenario" in
    gameplay) input="$LOAD_INPUT_SCRIPT" ;;
    newgame) input="$NEW_GAME_INPUT_SCRIPT" ;;
    *) echo "unknown scenario $scenario" >&2; exit 2 ;;
esac

PLAYING='?0x34eca8=5'
results=()
[ -z "$cores" ] && cores=default
for core in ${cores//,/ }; do
    out="$ROOT/logs/scenarios/$scenario-$core"
    rm -rf "$out" && mkdir -p "$out"
    envs=(PS2X_INPUT_SCRIPT="$input" RUN_TIMEOUT="$seconds" PS2X_TRACE_THREADS=0 PS2X_TRACE_IO=0
          PS2X_TRACE_VU1_STATS=1 PS2X_VU1_REPORT_UNFINISHED=4 PS2X_WATCH=0x34eca8,0x1e548c0)
    [ "$core" != default ] && envs+=(PS2X_VU1_CORE="$core")
    [ "$capture" = 1 ] && envs+=(PS2X_GS_CAPTURE="$PLAYING@$delay:$out/cap" PS2X_GS_CAPTURE_VRAM=1)
    [ "$dump" = 1 ] && envs+=(PS2X_DUMP_RAM="$PLAYING@$delay:$out/ram.bin")
    echo "== $scenario, VU1 core $core, ${seconds}s -> logs/scenarios/$scenario-$core"
    env "${envs[@]}" ${extra[@]+"${extra[@]}"} "$ROOT/pipeline.sh" run >"$out/pipeline.out" 2>&1 || true
    cp "$ROOT/logs/run.log" "$ROOT/logs/run.report" "$out/" 2>/dev/null || true
    python3 -I "$ROOT/tools/frames_report.py" "$ROOT/logs/frames" >"$out/frames.txt" 2>/dev/null || true
    python3 -I "$PS2RECOMP/ps2xRecomp/tools/runreport.py" "$out/run.log" --symbols "$ROOT/logs/symbols.tsv" \
        --ignore "$ROOT/config/report.ignore" --json "$out/metrics.json" >/dev/null || true
    results+=("$out")
done

python3 -I "$ROOT/tools/scenario_compare.py" ${baseline:+--baseline "$baseline"} \
    --baseline-file "$ROOT/logs/scenarios/$scenario.baseline.json" "${results[@]}"
