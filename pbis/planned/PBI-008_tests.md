# PBI-008: Test Suite

**Status:** Planned
**Priority:** Medium
**Created:** 2026-06-16
**Completed:**

## Description

Implement a comprehensive test suite for the Hermes TS3 adapter. Tests cover the ServerQuery client, voice receiver (VAD), voice player, command parser, authorization logic, and adapter integration. Uses pytest with mocking for external dependencies (TS3 server, PulseAudio, sounddevice, Hermes agent).

## Acceptance Criteria

- [ ] `tests/test_server_query.py`:
  - [ ] Response parsing: pipe-delimited format, escape sequences, error codes
  - [ ] Command building: parameter encoding, multi-word values
  - [ ] Event parsing: text message, client enter/leave/move events
  - [ ] Reconnection logic: backoff timing, max retries
  - [ ] Uses a mock TCP server (asyncio) to simulate ServerQuery responses
- [ ] `tests/test_voice_receiver.py`:
  - [ ] VAD logic: silence threshold (1.5s), min speech (0.5s), edge cases (continuous speech, silence only, short bursts)
  - [ ] PCM buffering: correct byte accumulation, buffer clearing on resume
  - [ ] WAV conversion: ffmpeg output validation (16kHz mono, correct duration)
  - [ ] Echo prevention: pause/resume cycle, no frames processed while paused
  - [ ] Uses synthetic PCM data (generated sine waves) fed through a mock InputStream
- [ ] `tests/test_voice_player.py`:
  - [ ] PCM playback: correct data written to mock OutputStream
  - [ ] File playback: ffmpeg decode, correct PCM format
  - [ ] is_playing state transitions
  - [ ] Stop mid-playback cleanup
- [ ] `tests/test_commands.py`:
  - [ ] Command parsing: !summon, !leave, !voice on/off, !status, !help
  - [ ] Authorization: allowed user + allowed channel → accept; disallowed → reject with correct message; unknown user → silent ignore
  - [ ] Invalid commands: graceful error message
  - [ ] Edge cases: empty message, multiple exclamation marks, command with extra whitespace
- [ ] `tests/test_adapter.py`:
  - [ ] Adapter lifecycle: connect → connected → disconnect → disconnected
  - [ ] Session key mapping: channel ID → `agent:main:teamspeak3:channel:{id}`
  - [ ] Message routing: text → handle_message → MessageEvent
  - [ ] Voice callback wiring: voice input → _voice_input_callback invocation
  - [ ] Integration: full pipeline with mocked ServerQuery, TS3 client, and audio devices
- [ ] `tests/conftest.py`: shared fixtures (mock ServerQuery, mock audio devices, sample TS3Config)
- [ ] All tests run with `pytest`; coverage target: >80% on core modules

## Linked Files

- `tests/conftest.py` — new: shared fixtures
- `tests/test_server_query.py` — new
- `tests/test_voice_receiver.py` — new
- `tests/test_voice_player.py` — new
- `tests/test_commands.py` — new
- `tests/test_adapter.py` — new

## Comments and Notes

- Tests use `pytest-asyncio` for async test support matching Hermes' own test patterns.
- ServerQuery mock uses asyncio TCP server to faithfully simulate the TS3 protocol handshake and responses.
- Voice receiver tests use synthetic PCM (sine waves at known frequencies/durations) for deterministic VAD behavior verification.
- Adapter integration tests mock all external dependencies (ServerQuery, TS3 client process, PulseAudio, Hermes gateway) to test the wiring logic in isolation.

## Depends On

- PBI-001 — project structure (for test layout)
- PBI-002 — ServerQuery client (can start tests early against the protocol)
- PBI-004 — voice receiver + player (can start tests early with mocks)
- PBI-005 — TeamSpeakAdapter (integration tests)
- PBI-006 — commands (command tests)
