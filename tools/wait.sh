#!/usr/bin/env bash
# Waits for background work without the pitfalls that bit before.
#   tools/wait.sh pid 1234 [5678...]   until those processes exit
#   tools/wait.sh file logs/x.done     until the file exists (and is not empty)
#   tools/wait.sh runner               until no ps2EntryRunner process is left
#   TIMEOUT=600 tools/wait.sh ...      give up after N seconds (exit 1); default: no limit
# Never `pgrep -f <pattern>`: the waiting shell's own command line contains the pattern, so it
# matches itself and the wait never ends. `pgrep -x` matches the process name only.
set -uo pipefail

mode=${1:-}
shift || true
deadline=$(( ${TIMEOUT:-0} > 0 ? SECONDS + TIMEOUT : 0 ))

done_yet() {
    case "$mode" in
        pid)
            for p in "$@"; do kill -0 "$p" 2>/dev/null && return 1; done
            return 0 ;;
        file)
            [ -s "$1" ] ;;
        runner)
            ! pgrep -x ps2EntryRunner >/dev/null ;;
        *)
            echo "usage: wait.sh pid <pid>... | file <path> | runner" >&2
            exit 2 ;;
    esac
}

until done_yet "$@"; do
    if [ "$deadline" -gt 0 ] && [ "$SECONDS" -ge "$deadline" ]; then
        echo "wait.sh: timed out after ${TIMEOUT}s ($mode $*)" >&2
        exit 1
    fi
    sleep 5
done
