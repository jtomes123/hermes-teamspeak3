# PBI-005: TeamSpeakAdapter — Hermes Platform Integration

**Status:** Planned
**Priority:** High
**Created:** 2026-06-16
**Completed:**

## Description

Implement the `TeamSpeakAdapter` class extending Hermes' `BasePlatformAdapter`. This is the central integration point that wires together the ServerQuery client, TS3 client manager, audio bridge, voice pipeline, and Hermes' agent/gateway infrastructure. It mirrors `DiscordAdapter` in architecture — implementing the full lifecycle (connect, disconnect, send, voice I/O), handling session mapping, and routing transcribed speech to Hermes' AI agent and TTS responses back to the voice channel.

## Acceptance Criteria

- [ ] `TeamSpeakAdapter(BasePlatformAdapter)` class implementing all required abstract methods:
  - [ ] `connect()` — start TS3 client via `TS3ClientManager`, connect ServerQuery, join home channel, start voice receiver
  - [ ] `disconnect()` — stop voice receiver, disconnect ServerQuery, stop TS3 client, cleanup PulseAudio
  - [ ] `send(chat_id, content, reply_to, metadata)` → `SendResult` — send text message via ServerQuery
  - [ ] `handle_message(event: MessageEvent)` — inherited; routes messages to agent
  - [ ] `get_chat_info(chat_id)` → dict — channel name, type, member list
- [ ] Voice channel lifecycle (`join_voice_channel`, `leave_voice_channel`):
  - [ ] Move TS3 client to target channel via ServerQuery `client_move`
  - [ ] Start `_voice_listen_loop` asyncio task (per-server, not per-channel since single client)
  - [ ] Stop listen loop on leave; return to home channel
- [ ] Voice listen loop (mirrors Discord's `_voice_listen_loop`):
  - [ ] Poll `TS3VoiceReceiver.on_utterance()` callback
  - [ ] Run PCM→WAV→STT pipeline using `transcription_tools.transcribe_audio()`
  - [ ] Filter hallucinations via `tools.voice_mode.is_whisper_hallucination()`
  - [ ] Call `self._voice_input_callback(channel_id, user_name, transcript)` to dispatch to agent
- [ ] TTS response playback:
  - [ ] After agent responds, generate speech via `tts_tool.generate_speech()`
  - [ ] Play via `TS3VoicePlayer.play_file()` with echo prevention (pause receiver during playback)
- [ ] Session mapping: TS3 channels mapped to Hermes session keys (`agent:main:teamspeak3:channel:{channel_id}`)
- [ ] Authorization integration:
  - [ ] Check `TS3_ALLOWED_USERS` and `TS3_ALLOWED_CHANNELS` before processing messages or voice
  - [ ] Unauthorized users/channels silently ignored (text) or not transcribed (voice)
- [ ] Message source mapping: TS3 client IDs → human-readable names via `client_info`
- [ ] Voice mode getter: routes Hermes `/voice on|off|tts` commands to adapter state
- [ ] Auto-return to home channel after configurable idle timeout (default: 5 minutes silent)

## Linked Files

- `src/hermes_agent_ts3/adapter.py` — new: TeamSpeakAdapter class (~600-800 lines, modeled on DiscordAdapter)
- `src/hermes_agent_ts3/plugin.yaml` — modify: wire `register()` to `TeamSpeakAdapter` factory

## Comments and Notes

- The adapter follows the exact same callback pattern as `DiscordAdapter`: `_voice_input_callback`, `_on_voice_disconnect`, `_voice_mode_getter` are set by `GatewayRunner`.
- STT uses Hermes' existing `transcription_tools` — zero new STT code. Provider chain: local (faster-whisper) → groq → openai → etc.
- TTS uses Hermes' existing `tts_tool` — zero new TTS code. Provider chain: edge → elevenlabs → openai → etc.
- Text messages from TS3 chat flow through `handle_message()` → `MessageEvent` → agent `run_conversation()` — identical to Discord's text path.
- Single TS3 client = single voice channel at a time. Concurrent voice in multiple channels requires PBI-003's multi-client mode (deferred).

## Depends On

- PBI-001 — project structure, plugin.yaml, TS3Config
- PBI-002 — ServerQuery client (control plane)
- PBI-003 — TS3 client manager + audio bridge
- PBI-004 — voice receiver + player
