# TeamSpeak 3 Setup

Learn how to connect Hermes Agent to a TeamSpeak 3 server. Once set up, Hermes
joins voice channels, listens to speech, transcribes it, processes it through
your LLM, and speaks responses back.

## How Hermes Behaves on TeamSpeak

Hermes connects as a regular voice client (not a ServerQuery bot). It sits in a
**home channel** by default and waits to be summoned.

**Channels:**
- Hermes can be summoned to allowed channels with `!summon`
- It leaves with `!leave` and returns to its home channel
- After 5 minutes of silence, it automatically returns home

**Voice:**
- Hermes continuously listens in the voice channel using Voice Activity Detection
- When someone finishes speaking, Hermes transcribes and responds
- Echo prevention pauses listening during TTS playback
- Voice mode can be toggled: `!voice on`, `!voice off`, `!voice tts`

**Text:**
- Hermes reads channel messages and responds to text
- Commands start with `!` (configurable prefix)
- Non-command messages are passed to the agent for conversation

**Sessions:**
- Each user gets a separate conversation session, keyed by their TS3 identity
- Voice transcriptions are attributed to the channel

## Prerequisites

- **Linux server** (Debian 12 / Ubuntu 24.04 LTS recommended)
- **Hermes Agent** v0.15.0 or later, with a configured LLM provider
- **TeamSpeak 3 server** with the Opus voice codec
- **ServerQuery access** — username and password, or the `serveradmin` account
- **System packages:** `xvfb`, `pulseaudio`, `ffmpeg`, `libopus0`, `portaudio19-dev`

## Installation

### Option A: Pip Install (Recommended)

Install the plugin as a Python package. Hermes discovers it automatically via
pip entry points — no manual plugin directory setup needed.

```bash
pip install hermes-agent-ts3
```

Install the system dependencies:

```bash
# Debian / Ubuntu
sudo apt install -y xvfb pulseaudio ffmpeg libopus0 \
    portaudio19-dev libportaudio2 espeak-ng

# Enable user-level PulseAudio lingering (survives logout)
loginctl enable-linger
```

### Option B: Git Clone

Clone the repository and install in development mode:

```bash
git clone https://github.com/jtomes123/hermes-teamspeak3.git
cd hermes-teamspeak3
pip install -e .
```

:::tip[Plugin Discovery]
After installing, run `hermes plugins list`. You should see:

```
teamspeak3          ✓ installed     (TeamSpeak 3)
```
:::

### Docker (Alternative)

A pre-built Docker image bundles Xvfb, PulseAudio, and the TS3 client:

```bash
git clone https://github.com/jtomes123/hermes-teamspeak3.git
cd hermes-teamspeak3
# Edit .env with your TS3 credentials
docker compose up -d
```

See [Docker Setup](#docker-setup) below for full details.

---

## Step 1: Download the TeamSpeak Client

Hermes uses the official TeamSpeak 3 Linux client to handle the voice protocol.
Download and extract it once:

```bash
# Set the download URL and checksum
TS3_URL="https://files.teamspeak-services.com/releases/client/3.6.2/TeamSpeak3-Client-linux_amd64-3.6.2.run"
TS3_CHECKSUM="sha256:<INSERT_CHECKSUM_HERE>"

# Run the download script (idempotent — skips if already cached)
./scripts/download_ts3_client.sh "$TS3_URL" "$TS3_CHECKSUM" "./ts3_client_data"
```

:::note[Find the checksum]
Visit [teamspeak.com/downloads](https://teamspeak.com/downloads) to get the
latest Linux client URL and SHA256 checksum.
:::

Set the data directory so Hermes knows where the client lives:

```bash
export TS3_CLIENT_DATA_DIR=$(pwd)/ts3_client_data
```

---

## Step 2: Configure ServerQuery Access

Hermes needs ServerQuery credentials to control the bot (move between channels,
send messages, list clients). Use the `serveradmin` account or create a dedicated
ServerQuery login on your TS3 server.

Add these to your Hermes environment (`~/.hermes/.env`):

```bash
TS3_SERVER_HOST=your-server.com
TS3_SERVERQUERY_USER=serveradmin
TS3_SERVERQUERY_PASS=your-password
```

:::tip[ServerQuery Health Check]
Before starting Hermes, verify ServerQuery works:

```bash
printf "use sid=1\nclientlist\nquit\n" | nc your-server.com 10011
```

You should see a list of currently connected clients. If you get `error id=3329`
(insufficient permissions), your ServerQuery account needs more privileges.
:::

---

## Step 3: Set Up PulseAudio

Start PulseAudio and create the virtual audio devices:

```bash
# Start PulseAudio
pulseaudio --start

# Create the virtual audio devices (idempotent)
./scripts/setup_audio.sh
```

The script creates four audio devices that route between the TS3 client and Hermes:

| Device | Type | Purpose |
|--------|------|---------|
| `ts3_playback` | Sink | TS3 client plays incoming voice here |
| `ts3_playback.monitor` | Source | Hermes captures from here (what users say) |
| `bot_tts_sink` | Sink | Hermes writes TTS audio here |
| `bot_tts` | Source | TS3 client transmits from here (what the bot says) |

Verify the devices exist:

```bash
pactl list short sinks | grep -E "ts3_playback|bot_tts"
pactl list short sources | grep -E "ts3_playback|bot_tts"
```

---

## Step 4: Start Xvfb

The TS3 client needs a display even though it runs headless. Xvfb provides one:

```bash
# Start Xvfb on display :99
Xvfb :99 -screen 0 1280x1024x24 -ac &

# Tell the TS3 client which display to use
export DISPLAY=:99
export TS3_XVFB_DISPLAY=:99
```

:::tip[Auto-start Xvfb]
To persist across reboots, add to your crontab or systemd user service:

```
@reboot Xvfb :99 -screen 0 1280x1024x24 -ac &
```
:::

---

## Step 5: Configure Authorization

Control who can interact with Hermes:

```bash
# Only these users can use commands or trigger voice responses
export TS3_ALLOWED_USERS="Alice,Bob,Charlie"

# Only these channels can the bot join
export TS3_ALLOWED_CHANNELS="General,AI Lounge,Bot Testing"

# Where Hermes hangs out when idle (required)
export TS3_HOME_CHANNEL="Hermes Lounge"

# Bot display name in TS3
export TS3_NICKNAME="Hermes"
```

:::warning[Empty allowlist]
If `TS3_ALLOWED_USERS` is left empty, **everyone** on the server can interact
with the bot. In production, always set an allowlist.
:::

---

## Step 6: Configure Hermes Voice Settings

Set up STT and TTS in your Hermes config file (`~/.hermes/config.yaml`):

```yaml
voice:
  stt:
    provider: local                      # Free, zero API keys required
    local:
      model: base                        # tiny | base | small | medium | large-v3
      language: en
  tts:
    provider: edge                       # Free, natural-sounding
    edge:
      voice: en-US-AriaNeural
```

### STT Providers

| Provider | Model | Speed | Cost | Key Required |
|----------|-------|-------|------|:---:|
| `local` | `base`–`large-v3` | Medium | Free | No |
| `groq` | `whisper-large-v3-turbo` | ~0.5s | Free tier | Yes |
| `openai` | `whisper-1` | ~1s | Paid | Yes |

### TTS Providers

| Provider | Quality | Latency | Cost | Key Required |
|----------|---------|---------|------|:---:|
| `edge` | Good | ~1s | Free | No |
| `elevenlabs` | Excellent | ~2s | Paid | Yes |
| `openai` | Good | ~1.5s | Paid | Yes |
| `piper` | Good | Local | Free | No |

---

## Step 7: Start the Gateway

With everything configured, start Hermes:

```bash
hermes gateway
```

You should see log output similar to:

```
INFO  TeamSpeak adapter connected (client_id=12, home_channel=5)
INFO  Voice player started on bot_tts_sink
INFO  Voice receiver started on ts3_playback.monitor (paused)
```

The bot now sits in your home channel, waiting for `!summon`.

## Step 8: Test

1. Join the same TS3 server (as a regular user, not as the bot)
2. Send `!summon` in any allowed channel's chat
3. Hermes should move to your channel and announce its arrival
4. Say something — Hermes transcribes, processes, and speaks back
5. Send `!status` to see current state
6. Send `!leave` to send the bot back home

## Bot Commands

:::tip[Prefix]
The default command prefix is `!`. Change it via `TS3_COMMAND_PREFIX` if you
already have another bot using that prefix.
:::

| Command | Description |
|---------|-------------|
| `!summon` | Summon Hermes to your current channel |
| `!leave` | Send Hermes back to its home channel |
| `!voice on` | Enable voice processing (listens to speech) |
| `!voice off` | Disable voice (text-only mode) |
| `!voice tts` | Voice replies only (speaks on voice input, text replies on text) |
| `!status` | Show current channel, voice mode, and uptime |
| `!help` | List all available commands |

## Configuration Reference

All environment variables:

| Variable | Required | Default | Description |
|----------|:-------:|---------|-------------|
| `TS3_SERVER_HOST` | **Yes** | — | TS3 server hostname or IP |
| `TS3_SERVERQUERY_USER` | **Yes** | — | ServerQuery username |
| `TS3_SERVERQUERY_PASS` | **Yes** | — | ServerQuery password |
| `TS3_HOME_CHANNEL` | **Yes** | — | Channel the bot idles in |
| `TS3_SERVERQUERY_PORT` | No | `10011` | ServerQuery TCP port |
| `TS3_VOICE_PORT` | No | `9987` | TS3 voice UDP port |
| `TS3_SERVER_PASSWORD` | No | — | TS3 server password (if required) |
| `TS3_NICKNAME` | No | `Hermes` | Bot display name |
| `TS3_ALLOWED_USERS` | No | `""` (everyone) | Comma-separated allowed nicknames |
| `TS3_ALLOWED_CHANNELS` | No | — | Comma-separated allowed channel names |
| `TS3_ALLOW_ALL_USERS` | No | `false` | Allow any user (dev/testing) |
| `TS3_CLIENT_DATA_DIR` | No | `ts3_client_data` | Working directory for identity/settings/logs |
| `TS3_CLIENT_DOWNLOAD_URL` | No | — | TS3 Linux client .run URL |
| `TS3_CLIENT_DOWNLOAD_CHECKSUM` | No | — | SHA256 checksum |
| `TS3_IDENTITY_FILE` | No | `ts3_identity` | Path to TS3 identity file |
| `TS3_XVFB_DISPLAY` | No | `:99` | Xvfb display |
| `TS3_PULSE_SINK` | No | `ts3_playback` | PulseAudio playback sink |
| `TS3_PULSE_SOURCE` | No | `bot_tts` | PulseAudio TTS source |
| `TS3_PULSE_SERVER` | No | — | PulseAudio server (empty = default) |
| `TS3_RECONNECT_BASE` | No | `1.0` | Initial reconnect delay (seconds) |
| `TS3_RECONNECT_MAX` | No | `60.0` | Maximum reconnect delay (seconds) |
| `TS3_COMMAND_PREFIX` | No | `!` | Bot command prefix |

---

## Docker Setup

For a fully containerized deployment:

**1. Create `.env` file:**

```bash
TS3_SERVER_HOST=your-server.com
TS3_SERVERQUERY_USER=serveradmin
TS3_SERVERQUERY_PASS=your-password
TS3_HOME_CHANNEL=Hermes Lounge
TS3_ALLOWED_USERS=User1,User2
TS3_ALLOWED_CHANNELS=General,Bot Channel
TS3_NICKNAME=Hermes
OPENAI_API_KEY=sk-...  # or your LLM provider's key
```

**2. Configure Hermes** (`./hermes_config/config.yaml`):

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

**3. Build and run:**

```bash
docker compose up -d
```

**4. Debug with VNC (optional):**

```bash
docker compose --profile vnc up -d
# Connect VNC client to localhost:5900, password: password
```

**Docker volumes:**

| Host Path | Container Path | Purpose |
|-----------|---------------|---------|
| `./hermes_config` | `/home/hermes/.hermes` | Hermes config + API keys |
| `./ts3_data` | `/home/hermes/ts3_data` | TS3 identity, settings.db, logs |

---

## Troubleshooting

### Bot doesn't appear in TS3

| Cause | Fix |
|-------|-----|
| ServerQuery unreachable | `printf "use sid=1\nclientlist\nquit\n" \| nc <HOST> 10011` |
| TS3 client binary missing | `ls ts3_client_data/ | grep ts3client` |
| Xvfb not running | `ps aux \| grep Xvfb` |
| Wrong display | `echo $DISPLAY` should show `:99` |

### Voice not starting (text works)

This is the most common issue — PulseAudio devices don't match. Hermes dumps
all visible audio devices to the log when startup fails:

```
ERROR Available audio devices:
ERROR   [0] Built-in Microphone (in=2, out=0, hostapi=Core Audio)
ERROR   [1] Built-in Output (in=0, out=2, hostapi=Core Audio)
ERROR   [5] ts3_playback (in=0, out=2, hostapi=ALSA)
ERROR   [6] ts3_playback.monitor (in=2, out=0, hostapi=ALSA)
...
```

Verify your devices appear in this list. If they don't, your PulseAudio setup
is incorrect — rerun `./scripts/setup_audio.sh`.

### No audio / silent bot

| Cause | Fix |
|-------|-----|
| PulseAudio not running | `pactl info` — if fails: `pulseaudio --start` |
| Virtual devices missing | `pactl list short sinks \| grep ts3` and `grep bot_tts` |
| Devices not routed | Rerun `./scripts/setup_audio.sh` |
| TS3 client wrong device | Examine `ts3_client_data/settings.db` |

### Voice recognition not working

| Cause | Fix |
|-------|-----|
| Server not using Opus | Check TS3 server codec settings — must be Opus Voice |
| STT provider misconfigured | Check `config.yaml` voice.stt settings |
| sounddevice can't see monitor | `python3 -c "import sounddevice as sd; print(sd.query_devices())"` |
| VAD threshold too high | Voices too quiet? Set `TS3_VAD_THRESHOLD` lower |

### Bot responds to itself (echo)

| Cause | Fix |
|-------|-----|
| Audio paths crossed | TTS output playing to `ts3_playback` instead of `bot_tts_sink` |
| Echo prevention not working | Check the `ts3_playback.monitor` only sees other users' audio |

### Bot connected but won't speak

| Cause | Fix |
|-------|-----|
| TTS provider error | Check `config.yaml` voice.tts settings |
| ffmpeg missing | `ffmpeg -version` — install if missing |
| TTS sink muted | `pactl set-sink-mute bot_tts_sink 0` |
| Voice mode is `off` | Send `!voice on` or `!voice tts` |

### ServerQuery keeps disconnecting

| Cause | Fix |
|-------|-----|
| Keepalive interval too short | Set `TS3_RECONNECT_BASE` higher |
| Server firewall | Ensure TCP port 10011 is not blocked |
| Wrong credentials | Verify `TS3_SERVERQUERY_USER` and `TS3_SERVERQUERY_PASS` |

## Security

- Store your ServerQuery password in `~/.hermes/.env` with restrictive permissions: `chmod 600 ~/.hermes/.env`
- Always set `TS3_ALLOWED_USERS` in production — an empty list means anyone can interact
- The bot's TS3 identity is auto-generated and stored in `TS3_CLIENT_DATA_DIR/identity`
- ServerQuery passwords are excluded from log output and `repr()`
- Do not share your bot's identity file — it uniquely identifies your bot instance
