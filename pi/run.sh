#!/usr/bin/env bash
# Everything the Pi does, with the right profile already chosen.
#
#   ./run.sh              the window: live view, dropdowns, Start cycle
#   ./run.sh console      the terminal view, for SSH - no display needed
#   ./run.sh preflight    is this Pi ready
#   ./run.sh bench        how fast the model runs HERE
#   ./run.sh check        the model against the held-out photos
#
# The profile is the whole point of this file. The base config.yaml says
# detector: yolo, which loads through ultralytics, which needs torch - and
# torch's aarch64 wheel fills the Pi's disk before it finishes installing.
# config/profiles/pi.yaml says ncnn instead. Forgetting --config was the
# commonest mistake at the station, and it fails in a way that reads like a
# broken model rather than a wrong flag.
#
# Anything you add on the command line is passed through, and argparse takes
# the last value, so ./run.sh preflight --no-camera overrides what is set here.
#
# Author: Suraj Karki
# Course: INA700 - AI-based pick and place
set -euo pipefail
cd "$(dirname "$0")"

CONSOLE=config/profiles/pi.yaml      # ncnn, no display needed
WINDOW=config/profiles/pi-gui.yaml   # the same, plus the window and the frame tap

command=${1:-start}
shift || true

case "$command" in
    start)
        exec python3 main.py --config "$WINDOW" "$@"
        ;;
    console)
        exec python3 main.py --config "$CONSOLE" "$@"
        ;;
    preflight)
        exec python3 tools/preflight.py --config "$CONSOLE" --length 100 "$@"
        ;;
    bench)
        exec python3 tools/benchmark.py --config "$CONSOLE" --count 20 "$@"
        ;;
    check)
        exec python3 tools/offline_check.py --config "$CONSOLE" "$@"
        ;;
    help|--help|-h)
        sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'
        ;;
    *)
        echo "Unknown command: $command" >&2
        sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//' >&2
        exit 1
        ;;
esac
