#!/usr/bin/env python3
"""Side-by-side numbers of scenario runs (tools/scenario.sh), and baseline checks.

usage: scenario_compare.py [--baseline save|check --baseline-file F] <run-dir>...

Each run dir has metrics.json (runreport.py --json) and frames.txt (frames_report.py). The table
shows speed, VU1 runs/cut-offs, severe anomalies, final game state and how lit the last frames are.
--baseline save stores the first run as the scenario's reference; --baseline check lists every
number that got worse than the reference (exit 3), so a regression shows up the run it happens.
"""

import argparse
import json
import re
import sys
from pathlib import Path


def frame_numbers(path):
    """Mean brightness and lit % over the last 5 screenshots."""
    try:
        cells = re.findall(r"(\d+):(\d+)/(\d+)%", Path(path).read_text())
    except OSError:
        return None, None
    last = cells[-5:]
    if not last:
        return None, None
    return (round(sum(int(m) for _, m, _ in last) / len(last), 1),
            round(sum(int(l) for _, _, l in last) / len(last), 1))


def load(run):
    run = Path(run)
    try:
        metrics = json.loads((run / "metrics.json").read_text())
    except (OSError, ValueError):
        metrics = {}
    metrics["frame_mean"], metrics["frame_lit"] = frame_numbers(run / "frames.txt")
    metrics["run"] = run.name
    return metrics


# (key, label, worse-when): "up" = a higher value is worse, "down" = a lower value is worse.
COLUMNS = [("vsync", "vsync", "down"), ("speed_late", "vsync/s late", "down"), ("vu1_ended", "vu1 ended", None),
           ("vu1_cut", "vu1 cut", "up"), ("severe", "severe", "up"), ("anomaly_kinds", "anomaly kinds", "up"),
           ("frame_mean", "frame mean", None), ("frame_lit", "frame lit%", "down"), ("watch_final", "state", None),
           ("stall", "stall", None)]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--baseline", choices=("save", "check"))
    ap.add_argument("--baseline-file")
    args = ap.parse_args()
    rows = [load(r) for r in args.runs]

    width = max(14, *(len(r["run"]) for r in rows))
    print("".ljust(16) + "".join(r["run"].ljust(width + 2) for r in rows))
    for key, label, _ in COLUMNS:
        print(label.ljust(16) + "".join(str(r.get(key, "-")).ljust(width + 2) for r in rows))

    if not args.baseline or not args.baseline_file:
        return
    path = Path(args.baseline_file)
    if args.baseline == "save":
        path.write_text(json.dumps(rows[0], indent=1))
        print(f"baseline saved: {path}")
        return
    try:
        base = json.loads(path.read_text())
    except (OSError, ValueError):
        print(f"no baseline at {path} (run with --baseline save on a good run)")
        return
    worse = []
    for row in rows:
        for key, label, direction in COLUMNS:
            a, b = base.get(key), row.get(key)
            if direction is None or not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
                continue
            # Small noise is not a regression: 15% for rates, any increase for counts of problems.
            if direction == "up" and b > a:
                worse.append(f"{row['run']}: {label} {a} -> {b}")
            if direction == "down" and b < a * 0.85:
                worse.append(f"{row['run']}: {label} {a} -> {b}")
    if worse:
        print("WORSE than the baseline:\n  " + "\n  ".join(worse))
        sys.exit(3)
    print("no regression against the baseline")


if __name__ == "__main__":
    main()
