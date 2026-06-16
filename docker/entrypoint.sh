#!/usr/bin/env bash
set -euo pipefail

cleanup() {
    echo "Shutting down..."
    kill -TERM "$HERMES_PID" 2>/dev/null || true
    kill -TERM "$XVFB_PID" 2>/dev/null || true
    pulseaudio --kill 2>/dev/null || true
    wait "$HERMES_PID" 2>/dev/null || true
    wait "$XVFB_PID" 2>/dev/null || true
    exit 0
}
trap cleanup SIGTERM SIGINT

# Start Xvfb on display :99
export DISPLAY=:99
Xvfb :99 -screen 0 1024x768x24 -ac +extension GLX +render -noreset &
XVFB_PID=$!
echo "Xvfb started (PID $XVFB_PID)"

# Wait for Xvfb to be ready
for i in $(seq 1 30); do
    if xdpyinfo -display :99 >/dev/null 2>&1; then
        break
    fi
    sleep 0.5
done
if ! xdpyinfo -display :99 >/dev/null 2>&1; then
    echo "ERROR: Xvfb failed to start" >&2
    exit 1
fi

# Start PulseAudio daemon
pulseaudio --start --exit-idle-time=-1 --log-target=stderr
echo "PulseAudio started"

# Wait for PulseAudio socket
for i in $(seq 1 30); do
    if [ -S /run/pulse/native ]; then
        break
    fi
    sleep 0.5
done
if ! [ -S /run/pulse/native ]; then
    echo "ERROR: PulseAudio socket not found" >&2
    exit 1
fi

# Setup audio virtual devices
echo "Setting up audio devices..."
/scripts/setup_audio.sh

echo "Starting Hermes gateway..."
hermes gateway &
HERMES_PID=$!

wait "$HERMES_PID"
