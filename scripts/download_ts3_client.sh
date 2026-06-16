#!/usr/bin/env bash
set -euo pipefail

# macOS sha256sum fallback (alias doesn't expand in non-interactive scripts)
sha256sum() {
    if command -v sha256sum >/dev/null 2>&1; then
        command sha256sum "$@"
    else
        shasum -a 256 "$@"
    fi
}

# Usage: download_ts3_client.sh <url> <sha256_checksum> <output_dir>
# Caching: if .run exists and checksum matches, skip download; re-extract if binary missing
# Steps: check cache → download (if needed) → verify → extract → echo path

URL="${1:?Usage: download_ts3_client.sh <url> <checksum> <output_dir>}"
CHECKSUM="${2:?}"
OUTPUT_DIR="${3:?}"

mkdir -p "$OUTPUT_DIR"
RUN_FILE="$OUTPUT_DIR/TeamSpeak3-Client.run"
EXTRACT_DIR="$OUTPUT_DIR/ts3client"

# Check cache
NEED_DOWNLOAD=true
if [ -f "$RUN_FILE" ]; then
    if echo "$CHECKSUM $RUN_FILE" | sha256sum -c >/dev/null 2>&1; then
        echo "TS3 client cached at $RUN_FILE" >&2
        if [ -f "$EXTRACT_DIR/ts3client_linux_amd64" ] || [ -f "$EXTRACT_DIR/ts3client_linux_x86" ]; then
            echo "TS3_CLIENT_BINARY=$EXTRACT_DIR"
            exit 0
        fi
        NEED_DOWNLOAD=false
    fi
fi

# Remove checksum prefix if present
CHECKSUM="${CHECKSUM#sha256:}"

# Download if needed
if [ "$NEED_DOWNLOAD" = true ]; then
    echo "Downloading TS3 client from $URL" >&2
    curl -fSL --progress-bar -o "${RUN_FILE}.download" "$URL"
    mv "${RUN_FILE}.download" "$RUN_FILE"
    echo "$CHECKSUM  $RUN_FILE" | sha256sum -c
fi

# Extract
chmod +x "$RUN_FILE"
rm -rf "$EXTRACT_DIR"
mkdir -p "$EXTRACT_DIR"
"$RUN_FILE" --target "$EXTRACT_DIR" --noexec 2>/dev/null || true
# The .run file extracts to target/ subdirs; find the binary
BINARY=$(find "$EXTRACT_DIR" -name 'ts3client_linux_*' -type f 2>/dev/null | head -1)
if [ -z "$BINARY" ]; then
    echo "ERROR: Could not find ts3client binary after extraction" >&2
    exit 1
fi
BINARY_DIR=$(dirname "$BINARY")
echo "TS3_CLIENT_BINARY=$BINARY_DIR"
exit 0
