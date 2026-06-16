# hermes-agent-ts3

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://hub.docker.com/)

TeamSpeak 3 voice AI bot powered by [Hermes Agent](https://github.com/NousResearch/hermes-agent) — a fully autonomous voice bot that listens to users in TeamSpeak voice channels, transcribes speech, processes it through an LLM, and speaks responses back.

Uses the official TeamSpeak 3 Linux client running headless on Xvfb, with PulseAudio virtual audio routing — **zero reverse-engineering** of the TS3 voice protocol.

---

## Architecture

```
┌───────────────────────────────────────────────────────────┐
│                     TS3 Server                             │
│  ┌──────────┐  ┌──────────────┐  ┌─────────────────────┐ │
│  │ Server   │  │ Voice (Opus) │  │ Voice (UDP)         │ │
│  │ Query    │  │              │  │                      │ │
│  └────┬─────┘  └──────┬───────┘  └──────────┬──────────┘ │
└───────┼───────────────┼────────────────────┼─────────────┘
        │               │                    │
   ┌────▼────┐    ┌──────▼───────┐    ┌───────▼──────────┐
   │Python   │    │ TS3 Client   │    │  TS3 Client      │
   │Server   │    │ (Official)   │    │  (Official)      │
   │Query    │    │ Playback ◄───┼────┤  Capture ─────►  │
   │Client   │    │ via Pulse    │    │  via Pulse        │
   └────┬────┘    └──────────────┘    └──────────────────┘
        │               ▲                       │
        │        ┌──────┴───────┐        ┌──────▼───────────┐
        │        │ PulseAudio   │        │ Audio Capture    │
        │        │ Virtual Sink │◄───────┤ (48kHz stereo)   │
        │        │ (bot_tts)    │        └──────┬───────────┘
        │        └──────────────┘               │
        │                                       ▼
        │                              ┌────────────────────┐
        │                              │ TS3VoiceReceiver   │
        │                              │  • VAD (1.5s/0.5s) │
        │                              │  • PCM → WAV       │
        │                              │  • Echo Prevention  │
        │                              └────────┬───────────┘
        │                                       │
        │                              ┌────────▼───────────┐
        │                              │ Transcription      │
        │                              │ (faster-whisper /   │
        │                              │  Groq / OpenAI)    │
        │                              └────────┬───────────┘
        │                                       │
        │                              ┌────────▼───────────┐
        │                              │ Hermes Agent       │
        │                              │  • LLM Processing  │
        │                              │  • Tools & Memory  │
        │                              └────────┬───────────┘
        │                                       │
        └───────────────────────────────────────┼───────────────
                                                │
                                       ┌────────▼───────────┐
                                       │ TTS Generation     │
                                       │ (Edge TTS /        │
                                       │  ElevenLabs / etc) │
                                       └────────┬───────────┘
                                                │
                                       ┌────────▼───────────┐
                                       │ TS3VoicePlayer     │
                                       │  • FFmpeg decode   │
                                       │  • PulseAudio out  │
                                       └────────────────────┘
```

## Features

- **Full voice pipeline** — Speech-to-Text → LLM Agent → Text-to-Speech, all in real-time
- **Always-on** — Bot sits in a home channel, summoned by users with `!summon`
- **Voice Activity Detection** — RMS-based energy detection with configurable thresholds
- **Echo prevention** — Automatic receiver pausing during TTS playback
- **Commands** — `!summon`, `!leave`, `!voice on/off/tts`, `!status`, `!help`
- **Authorization** — Allowlists for users and channels
- **Auto-reconnect** — TS3 client and ServerQuery reconnect with exponential backoff
- **Headless** — Runs entirely without a display via Xvfb

---

## Prerequisites

- **Linux** server (Debian/Ubuntu recommended)
- **TeamSpeak 3** server with Opus voice codec enabled
- **ServerQuery** access (user/password or serveradmin credentials)
- **Hermes Agent** configured with an LLM provider

For bare-metal:
- Python 3.11+
- Xvfb, PulseAudio, ffmpeg, libopus0, portaudio19-dev
- 2GB+ RAM, ~500MB disk

---

## Installation

### Option 1: Docker (Recommended)

**1. Clone the repository**

```bash
git clone https://github.com/jtomes123/hermes-teamspeak3.git
cd hermes-teamspeak3
```

**2. Configure environment**

Create a `.env` file:

```env
# Required
TS3_SERVER_HOST=your-server.com
TS3_SERVERQUERY_USER=serveradmin
TS3_SERVERQUERY_PASS=your-password

# Optional — adjust to your server
TS3_SERVERQUERY_PORT=10011
TS3_VOICE_PORT=9987
TS3_HOME_CHANNEL=Hermes Lounge
TS3_ALLOWED_USERS=User1,User2
TS3_ALLOWED_CHANNELS=General,Bot Channel
TS3_NICKNAME=Hermes

# Hermes Agent LLM configuration
OPENAI_API_KEY=sk-...
# or any other provider Hermes supports
```

**3. Configure Hermes Agent**

Create `~/.hermes/config.yaml` (mounted into the container):

```yaml
model: openai/gpt-4o-mini
voice:
  stt:
    provider: local
    local:
      model: base
  tts:
    provider: edge
```

**4. Build and run**

```bash
docker compose up -d
```

**5. Optional: VNC for debugging**

```bash
docker compose --profile vnc up -d
# VNC at localhost:5900, password: password
```

**Docker volumes:**

| Host Path | Container Path | Purpose |
|-----------|---------------|---------|
| `./hermes_config` | `/home/hermes/.hermes` | Hermes config + API keys |
| `./ts3_data` | `/home/hermes/ts3_data` | TS3 identity, settings.db, logs |

### Option 2: Bare-Metal Linux

**1. Install system dependencies**

```bash
# Debian/Ubuntu
sudo apt update
sudo apt install -y xvfb pulseaudio ffmpeg libopus0 \
    portaudio19-dev libportaudio2 espeak-ng \
    python3 python3-pip python3-venv
```

**2. Install the package**

```bash
git clone https://github.com/jtomes123/hermes-teamspeak3.git
cd hermes-teamspeak3
pip install -e .
```

**3. Download the TeamSpeak 3 client**

```bash
# Option A: Use the bundled script (recommended)
export TS3_CLIENT_DOWNLOAD_URL="https://files.teamspeak-services.com/releases/client/3.6.2/TeamSpeak3-Client-linux_amd64-3.6.2.run"
export TS3_CLIENT_DOWNLOAD_CHECKSUM="sha256:<insert checksum>"
./scripts/download_ts3_client.sh \
    "$TS3_CLIENT_DOWNLOAD_URL" \
    "$TS3_CLIENT_DOWNLOAD_CHECKSUM" \
    "./ts3_client_data"

# Option B: Download manually
# Download from https://teamspeak.com/downloads/
# Extract to ./ts3_client_data/ts3client/
```

**4. Configure PulseAudio**

```bash
# Start PulseAudio if not running
pulseaudio --start

# Run the audio setup script (idempotent)
./scripts/setup_audio.sh
```

**5. Set environment variables**

```bash
export TS3_SERVER_HOST="your-server.com"
export TS3_SERVERQUERY_USER="serveradmin"
export TS3_SERVERQUERY_PASS="your-password"
export TS3_HOME_CHANNEL="Hermes Lounge"
export TS3_ALLOWED_USERS="User1,User2"
export TS3_ALLOWED_CHANNELS="General,Bot Channel"
export TS3_CLIENT_DATA_DIR="./ts3_client_data"
export TS3_XVFB_DISPLAY=":99"
```

**6. Start Xvfb**

```bash
Xvfb :99 -screen 0 1280x1024x24 -ac &
export DISPLAY=:99
```

**7. Run**

```bash
hermes gateway
```

The bot will connect to your TS3 server and join the configured home channel.

---

## Bot Commands

Users interact with the bot via text commands in TS3 channel chat:

| Command | Description |
|---------|-------------|
| `!summon` | Summon the bot to your current channel |
| `!leave` | Send the bot back to its home channel |
| `!voice on` | Enable voice processing |
| `!voice off` | Disable voice processing (text only) |
| `!voice tts` | Voice replies only (speaks only on voice input) |
| `!status` | Show current channel, voice mode, and uptime |
| `!help` | List all available commands |

### Examples

```
User: !summon
Bot:  [moves to User's channel] Hello! I'm now listening in #General.

User: !voice on
Bot:  Voice mode enabled.

User: Hello bot, how are you?
Bot:  (voice) I'm doing great, thanks for asking!

User: !status
Bot:  📍 Channel: General | Voice: on | Uptime: 2h 34m

User: !leave
Bot:  [returns to home channel] Goodbye!
```

---

## Configuration Reference

All configuration is done via environment variables:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TS3_SERVER_HOST` | **Yes** | — | TS3 server hostname or IP |
| `TS3_SERVERQUERY_USER` | **Yes** | — | ServerQuery login username |
| `TS3_SERVERQUERY_PASS` | **Yes** | — | ServerQuery login password |
| `TS3_SERVERQUERY_PORT` | No | `10011` | ServerQuery TCP port |
| `TS3_VOICE_PORT` | No | `9987` | TS3 voice UDP port |
| `TS3_HOME_CHANNEL` | No | — | Default channel the bot idles in |
| `TS3_ALLOWED_USERS` | No | — | Comma-separated allowed nicknames/IDs |
| `TS3_ALLOWED_CHANNELS` | No | — | Comma-separated allowed channel names/IDs |
| `TS3_ALLOW_ALL_USERS` | No | `false` | Allow any user (dev/testing only) |
| `TS3_NICKNAME` | No | `Hermes` | Bot display name in TS3 |
| `TS3_SERVER_PASSWORD` | No | — | TS3 server password (if required) |
| `TS3_IDENTITY_FILE` | No | `ts3_identity` | Path to TS3 identity file |
| `TS3_CLIENT_DATA_DIR` | No | `ts3_client_data` | Working directory for settings.db/identity/logs |
| `TS3_CLIENT_DOWNLOAD_URL` | No | — | TS3 Linux client download URL |
| `TS3_CLIENT_DOWNLOAD_CHECKSUM` | No | — | SHA256 checksum of the client binary |
| `TS3_PULSE_SINK` | No | `ts3_playback` | PulseAudio playback sink name |
| `TS3_PULSE_SOURCE` | No | `bot_tts` | PulseAudio TTS source name |
| `TS3_PULSE_SERVER` | No | — | PulseAudio server (empty = default socket) |
| `TS3_XVFB_DISPLAY` | No | `:99` | Xvfb display number |
| `TS3_RECONNECT_BASE` | No | `1.0` | Initial reconnect delay (seconds) |
| `TS3_RECONNECT_MAX` | No | `60.0` | Maximum reconnect delay (seconds) |
| `TS3_COMMAND_PREFIX` | No | `!` | Bot command prefix |

### Hermes Agent Configuration

The adapter is a Hermes Agent platform plugin. Configure your LLM provider and voice settings in Hermes' `config.yaml`:

```yaml
# ~/.hermes/config.yaml
model: openai/gpt-4o-mini

voice:
  stt:
    provider: local           # local, groq, openai, or mistral
    local:
      model: base             # tiny, base, small, medium, large-v3
      language: en
  tts:
    provider: edge            # edge, elevenlabs, openai, piper, neustts
    edge:
      voice: en-US-AriaNeural
```

## Echo Prevention

During TTS playback, the voice receiver is automatically paused to prevent the bot from hearing and processing its own speech output. The receiver resumes after playback completes. This uses **separate PulseAudio audio paths** — TTS output goes to `bot_tts_sink` (never mixed with the incoming `ts3_playback` monitor), so there is no electrical/software echo loop.

## Testing

```bash
# Run the full test suite (214 tests)
python3 -m pytest tests/ -v

# Run specific test files
python3 -m pytest tests/test_adapter.py -v
python3 -m pytest tests/test_commands.py -v
python3 -m pytest tests/test_voice_receiver.py -v
```

## Troubleshooting

### Bot doesn't appear in TS3

- Check ServerQuery connectivity: `echo "use sid=1\nclientlist\nquit" | nc <host> 10011`
- Verify the TS3 client binary exists: `ls ts3_client_data/ts3client/`
- Check Xvfb is running: `ps aux | grep Xvfb`

### No audio / silent bot

- Verify PulseAudio is running: `pactl info`
- Check virtual devices exist: `pactl list short sinks | grep ts3` and `pactl list short sources | grep bot_tts`
- Run setup_audio.sh: `./scripts/setup_audio.sh`
- Check TS3 client uses correct audio devices: examine `ts3_client_data/settings.db`

### Voice recognition not working

- Ensure the TS3 server uses **Opus Voice** codec
- Check STT provider configuration in Hermes config
- Verify `sounddevice` can see the PulseAudio monitor source
- Increase logging: `export HERMES_LOG_LEVEL=DEBUG`

### Bot connects but can't speak

- Check TTS provider configuration in Hermes config
- Verify ffmpeg is installed: `ffmpeg -version`
- Check `bot_tts_sink` sink is not muted: `pactl set-sink-mute bot_tts_sink 0`

## Development

### Project Structure

```
src/hermes_agent_ts3/
├── __init__.py              # Hermes plugin entry (register function)
├── plugin.yaml               # Platform metadata + env var declarations
├── config.py                 # TS3Config dataclass
├── server_query.py           # Async TS3 ServerQuery protocol client
├── server_query_types.py     # Types, parsing, escape handling
├── ts3_client.py             # TS3 client subprocess manager
├── audio_bridge.py           # PulseAudio virtual device bridge
├── voice_receiver.py         # Audio capture + VAD + PCM→WAV
├── voice_player.py           # TTS audio playback via PulseAudio
├── voice_constants.py        # Shared audio format constants
├── adapter.py                # TeamSpeakAdapter (BasePlatformAdapter)
└── commands.py               # !summon, !leave, !voice, !status, !help

scripts/
├── download_ts3_client.sh    # Fetch + verify TS3 Linux client
└── setup_audio.sh            # Idempotent PulseAudio configuration

docker/
├── Dockerfile
├── docker-compose.yml
├── entrypoint.sh
└── healthcheck.sh

tests/
├── test_config.py            # TS3Config tests
├── test_server_query.py      # ServerQuery protocol tests
├── test_ts3_client.py        # Client manager tests
├── test_audio_bridge.py      # PulseAudio bridge tests
├── test_voice_receiver.py    # Voice receiver + VAD tests
├── test_voice_player.py      # Voice player tests
├── test_adapter.py           # Adapter integration tests
└── test_commands.py          # Command handler tests
```

### Running Tests

```bash
pip install -e ".[dev]"
python3 -m pytest tests/ -v
```

## License

MIT
