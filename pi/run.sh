#!/usr/bin/env bash
# Everything the Pi does, with the right profile already chosen.
#
#   ./run.sh              the window: live view, dropdowns, Send pick to robot
#   ./run.sh console      the terminal view, for SSH - no display needed
#   ./run.sh preflight    is this Pi ready
#   ./run.sh light        live lighting meter - aim the lamp by numbers
#   ./run.sh bench        how fast the model runs HERE
#   ./run.sh check        the model against the held-out photos

if [ "${BASH_SOURCE[0]:-$0}" != "$0" ]; then
    echo "Run this as ./run.sh - do not 'source' it." >&2
    echo "Sourced, it takes the terminal down with the window." >&2
    return 1
fi

set -euo pipefail
cd "$(dirname "$0")"

# The terminal may have been opened only to run this - a desktop icon, or
# "Execute" from the file manager. Such a window closes the moment the command
# ends, which is also when the error you need to read appears. Hold it open.
# A terminal you were already typing in has a prompt to return to, so it is
# left alone: its parent is a shell, and a shell's command line never names
# this script.
hold_terminal_open() {
    case "$(ps -o args= -p $PPID 2>/dev/null || true)" in
        *run.sh*)
            if [ -t 0 ]; then
                echo ""
                read -r -p "Finished. Press Enter to close this window. " _
            fi
            ;;
    esac
}
trap hold_terminal_open EXIT
if [ -z "${VIRTUAL_ENV:-}" ] && [ -f "$HOME/venv/bin/activate" ]; then
    echo "The virtual environment is not active. Run this first:" >&2
    echo "" >&2
    echo "    source ~/venv/bin/activate" >&2
    echo "" >&2
    exit 1
fi

CONSOLE=config/profiles/pi.yaml      # ncnn, no display needed
WINDOW=config/profiles/pi-gui.yaml   # the same, plus the window and the frame tap

command=${1:-start}
shift || true

# python runs as a child, never through exec: this shell has to outlive it to
# hold the window open, and an exec'd python leaves nothing here to do that.
case "$command" in
    start)
        python3 main.py --config "$WINDOW" "$@"
        ;;
    console)
        python3 main.py --config "$CONSOLE" "$@"
        ;;
    preflight)
        python3 tools/preflight.py --config "$CONSOLE" --length 100 "$@"
        ;;
    light)
        python3 tools/light_meter.py --config "$CONSOLE" "$@"
        ;;
    bench)
        python3 tools/benchmark.py --config "$CONSOLE" --count 20 "$@"
        ;;
    check)
        python3 tools/offline_check.py --config "$CONSOLE" "$@"
        ;;
    help|--help|-h)
        sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'
        ;;
    *)
        echo "Unknown command: $command" >&2
        sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//' >&2
        exit 1
        ;;
esac
