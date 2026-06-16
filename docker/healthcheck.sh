#!/usr/bin/env bash
set -euo pipefail

# 1. Check Xvfb is running
if ! pgrep -x Xvfb >/dev/null; then
    echo "UNHEALTHY: Xvfb not running"
    exit 1
fi

# 2. Check PulseAudio is running
if ! pgrep -x pulseaudio >/dev/null; then
    echo "UNHEALTHY: PulseAudio not running"
    exit 1
fi

# 3. Check PulseAudio responsiveness
if ! pactl info >/dev/null 2>&1; then
    echo "UNHEALTHY: PulseAudio unresponsive"
    exit 1
fi

# 4. Check TS3 client binary exists (connectivity check happens at runtime)
if [ ! -f /opt/ts3client/ts3client_linux_amd64 ]; then
    BINARY=$(find /opt/ts3client -name 'ts3client_linux_*' -type f 2>/dev/null | head -1)
    if [ -z "$BINARY" ]; then
        echo "UNHEALTHY: TS3 client binary not found"
        exit 1
    fi
fi

# 5. Check hermes gateway is running
if ! pgrep -f "hermes gateway" >/dev/null 2>&1; then
    echo "UNHEALTHY: Hermes gateway not running"
    exit 1
fi

echo "HEALTHY"
exit 0
