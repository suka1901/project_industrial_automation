#!/usr/bin/env bash
# Builds the bundle, puts it on the Pi, and asks the Pi whether it agrees.
#
#   ./deploy.sh 192.168.1.42     # the address is remembered after the first time
#   ./deploy.sh                  # uses the remembered one
#   ./deploy.sh --with-camera    # also runs the camera and marker checks there
#   ./deploy.sh --skip-build     # push the bundle already built
#
# Everything is fixed on this PC and shipped; the Pi only runs what arrives.
#
# Author: Suraj Karki
# Course: INA700 - AI-based pick and place
set -euo pipefail
cd "$(dirname "$0")"

USER_NAME=${PI_USER:-pi}
DESTINATION=${PI_PATH:-'~/INA700'}
REMEMBERED=.pi-address
ADDRESS=""
BUILD=yes
CAMERA="--no-camera --length 0"

for argument in "$@"; do
    case "$argument" in
        --skip-build) BUILD=no ;;
        --with-camera) CAMERA="--length 100" ;;
        -*) echo "Unknown option: $argument"; exit 1 ;;
        *) ADDRESS="$argument" ;;
    esac
done

if [ -z "$ADDRESS" ] && [ -f "$REMEMBERED" ]; then
    ADDRESS=$(tr -d '[:space:]' < "$REMEMBERED")
    echo "Pi at $ADDRESS (remembered)"
fi
if [ -z "$ADDRESS" ]; then
    echo "No Pi address. Pass it once and it is remembered:  ./deploy.sh 192.168.1.42"
    exit 1
fi
printf '%s' "$ADDRESS" > "$REMEMBERED"
TARGET="$USER_NAME@$ADDRESS"

[ "$BUILD" = yes ] && ./rebundle.sh
[ -f ina700-pi.tar.gz ] || { echo "No ina700-pi.tar.gz to send."; exit 1; }

echo
echo "Copying to $TARGET ..."
scp ina700-pi.tar.gz "$TARGET:~/"
echo "Unpacking..."
ssh "$TARGET" "mkdir -p $DESTINATION && tar -xzf ~/ina700-pi.tar.gz -C $DESTINATION"

# The config carries every measured value, so it is the file worth checking: a
# mismatch means the unpack did not overwrite, and the Pi is running a
# different calibration from the one on screen here.
LOCAL_HASH=$(sha256sum pi/config/config.yaml | cut -d' ' -f1)
REMOTE_HASH=$(ssh "$TARGET" "sha256sum $DESTINATION/pi/config/config.yaml" | cut -d' ' -f1)
if [ "$LOCAL_HASH" != "$REMOTE_HASH" ]; then
    echo
    echo "THE PI HAS A DIFFERENT config.yaml."
    echo "  here $LOCAL_HASH"
    echo "  pi   $REMOTE_HASH"
    echo "The unpack did not overwrite. Everything after this inherits it."
    exit 1
fi
echo "config.yaml matches - the Pi has this calibration."

echo
echo "Pre-flight on the Pi..."
set +e
ssh "$TARGET" "cd $DESTINATION/pi && python3 tools/preflight.py --config config/profiles/pi.yaml $CAMERA"
PREFLIGHT=$?
set -e

echo
[ $PREFLIGHT -eq 0 ] && echo "  The Pi is ready." || echo "  Pre-flight failed on the Pi - see the rows above."
echo
echo "  ssh $TARGET"
echo "  cd $DESTINATION/pi && python3 main.py --config config/profiles/pi-gui.yaml"
exit $PREFLIGHT
