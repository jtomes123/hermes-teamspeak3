# PBI-003: TS3 Client Subprocess Manager & PulseAudio Bridge

**Status:** Planned
**Priority:** High
**Created:** 2026-06-16
**Completed:**

## Description

Implement the infrastructure to run the official TeamSpeak 3 Linux client as a headless subprocess and configure PulseAudio virtual audio devices for routing audio between the TS3 client and the Python agent. This is the core "Approach B" enabler — managing the TS3 client lifecycle (start, monitor, restart) and the audio plumbing (virtual sinks, sources, loopbacks) that lets us capture and inject audio without reverse-engineering the TS3 voice protocol.

## Acceptance Criteria

- [ ] `TS3ClientManager` class: starts TS3 client subprocess under Xvfb, monitors health, handles graceful shutdown
- [ ] Auto-generates TS3 identity (keypair) on first run and persists it; uses existing identity if present
- [ ] Downloads/caches official TS3 Linux client binary (checksum-verified) via `scripts/download_ts3_client.sh`
- [ ] Configures TS3 client to auto-connect using `ts3server://` URL with nickname and password
- [ ] Configures TS3 client to use specified PulseAudio devices for playback and capture (via settings.db or command-line)
- [ ] `PulseAudioBridge` class: creates and configures virtual audio devices via `pactl`
  - Virtual sink for TS3 playback output: `ts3_playback` — Python captures from `ts3_playback.monitor`
  - Virtual source for bot TTS input: `bot_tts` — TS3 client captures from `bot_tts.monitor` (or directly)
  - Cleanup on shutdown (removes PulseAudio modules)
- [ ] `setup_audio.sh` script: idempotent PulseAudio setup, verifies devices exist, outputs device names for Python to reference
- [ ] Health checks: process alive, PulseAudio modules present, TS3 client connected (via ServerQuery)
- [ ] Auto-reconnect: if TS3 client exits unexpectedly, restart with exponential backoff (1s → 60s max), rejoin home channel
- [ ] Diagnostic logging: client stdout/stderr captured, PulseAudio module IDs logged

## Linked Files

- `src/hermes_agent_ts3/ts3_client.py` — new: TS3ClientManager (subprocess lifecycle, identity, config)
- `src/hermes_agent_ts3/audio_bridge.py` — new: PulseAudioBridge (virtual sinks, sources, monitoring)
- `scripts/download_ts3_client.sh` — new: fetch + verify TS3 Linux client
- `scripts/setup_audio.sh` — new: idempotent PulseAudio configuration

## Comments and Notes

- TS3 client runs under Xvfb on a virtual display (e.g., `:99`). The client is configured via `settings.db` (SQLite) with pre-set audio devices, bookmarks, and VAD sensitivity.
- Audio format: 48kHz, stereo (2ch), s16le — matches TS3 internal format and Hermes Discord adapter.
- Identity auto-generation uses TS3's built-in identity creation — the client can generate its own security level on first run.
- PulseAudio module cleanup must use module IDs (not names) to avoid accidentally removing other modules with the same name.
- `setup_audio.sh` must be idempotent — safe to run multiple times, only creates modules if they don't exist.

## Depends On

- PBI-001 — project structure and config (TS3Config)
