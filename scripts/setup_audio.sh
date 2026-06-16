#!/usr/bin/env bash
set -euo pipefail

# Usage: setup_audio.sh [--pulse-server <server>]
# Idempotent PulseAudio setup for TS3 ↔ Python audio routing
# Outputs shell-eval'able device names

# Parse args
PULSE_SERVER_ARG=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --pulse-server) PULSE_SERVER_ARG="PULSE_SERVER=$2"; shift 2 ;;
        *) shift ;;
    esac
done

run_pactl() {
    if [ -n "$PULSE_SERVER_ARG" ]; then
        env "$PULSE_SERVER_ARG" pactl "$@"
    else
        pactl "$@"
    fi
}

PLAYBACK_SINK="ts3_playback"
TTS_SINK="bot_tts_sink"
TTS_SOURCE="bot_tts"
MODULE_IDS=""

# Check each device individually; create only missing ones
SINKS=$(run_pactl list short sinks 2>/dev/null || echo "")
SOURCES=$(run_pactl list short sources 2>/dev/null || echo "")

HAS_PLAYBACK=$(echo "$SINKS" | grep -cw "$PLAYBACK_SINK" || true)
HAS_TTS_SINK=$(echo "$SINKS" | grep -cw "$TTS_SINK" || true)
HAS_TTS_SOURCE=$(echo "$SOURCES" | grep -cw "$TTS_SOURCE" || true)

# Create playback null sink (TS3 outputs here) — only if missing
if [ "$HAS_PLAYBACK" -eq 0 ]; then
    if ID1=$(run_pactl load-module module-null-sink "sink_name=$PLAYBACK_SINK" "sink_properties=device.description=TS3_Playback" 2>/dev/null); then
        echo "Created $PLAYBACK_SINK (module $ID1)" >&2
        MODULE_IDS="$MODULE_IDS${MODULE_IDS:+,}$ID1"
    else
        echo "WARNING: Failed to create $PLAYBACK_SINK" >&2
    fi
else
    echo "$PLAYBACK_SINK already exists — skipping" >&2
fi

# Create TTS null sink (Python writes TTS here) — only if missing
if [ "$HAS_TTS_SINK" -eq 0 ]; then
    if ID2=$(run_pactl load-module module-null-sink "sink_name=$TTS_SINK" "sink_properties=device.description=Bot_TTS_Sink" 2>/dev/null); then
        echo "Created $TTS_SINK (module $ID2)" >&2
        MODULE_IDS="$MODULE_IDS${MODULE_IDS:+,}$ID2"
    else
        echo "WARNING: Failed to create $TTS_SINK" >&2
    fi
else
    echo "$TTS_SINK already exists — skipping" >&2
fi

# Create remap source from TTS sink monitor (TS3 captures from this) — only if missing
if [ "$HAS_TTS_SOURCE" -eq 0 ]; then
    if ID3=$(run_pactl load-module module-remap-source "source_name=$TTS_SOURCE" "master=$TTS_SINK.monitor" "source_properties=device.description=Bot_TTS" 2>/dev/null); then
        echo "Created $TTS_SOURCE (module $ID3)" >&2
        MODULE_IDS="$MODULE_IDS${MODULE_IDS:+,}$ID3"
    else
        echo "WARNING: Failed to create $TTS_SOURCE" >&2
    fi
else
    echo "$TTS_SOURCE already exists — skipping" >&2
fi

# Output for Python parsing
cat <<EOF
PULSE_TS3_PLAYBACK_SINK=$PLAYBACK_SINK
PULSE_TS3_PLAYBACK_MONITOR=$PLAYBACK_SINK.monitor
PULSE_BOT_TTS_SINK=$TTS_SINK
PULSE_BOT_TTS_SOURCE=$TTS_SOURCE
PULSE_MODULE_IDS=$MODULE_IDS
EOF
