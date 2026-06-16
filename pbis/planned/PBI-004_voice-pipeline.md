# PBI-004: Voice Pipeline — Audio Capture, VAD, and Playback

**Status:** Planned
**Priority:** High
**Created:** 2026-06-16
**Completed:**

## Description

Implement the voice audio pipeline that captures mixed TS3 channel audio from PulseAudio, detects speech utterances via silence-based VAD, and plays TTS output back into the TS3 channel. This mirrors the Hermes Discord `VoiceReceiver` and `VoiceMixer`/`play_in_voice_channel()` patterns but adapted for PulseAudio device I/O instead of Discord's RTP/Opus streaming.

## Acceptance Criteria

- [ ] `TS3VoiceReceiver` class:
  - [ ] Opens a `sounddevice.InputStream` on the PulseAudio monitor source (`ts3_playback.monitor`) at 48kHz stereo s16le
  - [ ] Continuous audio capture loop running in an asyncio-compatible thread
  - [ ] Silence-based VAD: 1.5s silence threshold, 0.5s minimum speech duration (matches Discord VoiceReceiver constants)
  - [ ] Buffers PCM data per utterance; flushes completed utterances for STT processing
  - [ ] Callback mechanism: `on_utterance(pcm_bytes: bytes, duration_seconds: float)` — called when a complete utterance is detected
  - [ ] Echo prevention: pauses capture while TTS is playing (driven by `pause()`/`resume()` methods)
  - [ ] PCM → WAV conversion utility (ffmpeg: 48kHz/2ch/s16le → 16kHz/mono WAV) matching Discord's `VoiceReceiver.pcm_to_wav()`
- [ ] `TS3VoicePlayer` class:
  - [ ] Opens a `sounddevice.OutputStream` on the PulseAudio virtual source (`bot_tts`)
  - [ ] `play_pcm(pcm_bytes: bytes)` — plays raw PCM audio into TS3 client's capture device
  - [ ] `play_file(audio_path: str)` — decodes audio file (mp3/ogg/wav) via ffmpeg and plays PCM
  - [ ] `is_playing` property — True while audio is being sent
  - [ ] `stop()` — immediately stop playback
  - [ ] Non-blocking: playback runs on a separate thread; returns immediately, signals completion via async event
- [ ] Audio format constants shared between receiver and player: 48kHz, 2ch, s16le, 960 samples/frame (20ms)

## Linked Files

- `src/hermes_agent_ts3/voice_receiver.py` — new: TS3VoiceReceiver (capture, VAD, WAV conversion)
- `src/hermes_agent_ts3/voice_player.py` — new: TS3VoicePlayer (playback, file decoding)

## Comments and Notes

- Uses `sounddevice` (PortAudio) — the same library Hermes uses internally. This ensures device enumeration and format compatibility.
- VAD algorithm is intentionally simple (buffer-duration-based) matching Discord's approach, not RMS thresholding. This avoids the complexity of per-sample energy computation.
- Multi-speaker audio is mixed by the TS3 client — we receive a single mixed PCM stream. v1 transcribes as a single stream; diarization is out of scope.
- Echo prevention: `pause()` mutes the `InputStream` callback (drops frames) while TTS is playing; `resume()` clears the buffer and resumes capture. This is the same pattern as Discord's `receiver.pause()`.
- The receiver and player are designed to be testable with mock audio devices (e.g., file-based PCM for receiver, null output for player).

## Depends On

- PBI-003 — PulseAudio virtual devices must exist (`ts3_playback.monitor`, `bot_tts`)
