# PBI-007: Docker Deployment

**Status:** Planned
**Priority:** Medium
**Created:** 2026-06-16
**Completed:**

## Description

Create Docker deployment artifacts for running the Hermes TS3 adapter on a headless Linux server. The container bundles Xvfb, PulseAudio, the official TS3 Linux client, and the Python adapter into a single deployable unit. This makes the bot trivially deployable on any Linux host with Docker, without manual dependency installation.

## Acceptance Criteria

- [ ] `Dockerfile` based on `python:3.12-slim`:
  - [ ] Installs system dependencies: Xvfb, PulseAudio, ffmpeg, libopus0, portaudio19-dev, libportaudio2, espeak-ng
  - [ ] Downloads and installs official TS3 Linux client (via PBI-003's download script)
  - [ ] Installs `hermes-agent[voice,messaging]` and `hermes-agent-ts3` packages
  - [ ] Creates non-root user (`hermes`) for running the gateway
  - [ ] Configures PulseAudio to run in system mode or socket-activated
- [ ] `docker-compose.yml`:
  - [ ] Maps TS3 data volumes: identity file, TS3 client config, Hermes config
  - [ ] Passes required environment variables: `TS3_SERVER_HOST`, `TS3_SERVERQUERY_PORT`, `TS3_HOME_CHANNEL`, `TS3_ALLOWED_USERS`, `TS3_ALLOWED_CHANNELS`, Hermes API keys
  - [ ] Enables `stdin_open: true` and `tty: true` for interactive debugging
  - [ ] Optional X11 forwarding for VNC debugging (x11vnc)
- [ ] `docker/entrypoint.sh`:
  - [ ] Starts Xvfb on `:99`
  - [ ] Runs PBI-003's `setup_audio.sh` to configure PulseAudio
  - [ ] Starts PulseAudio daemon
  - [ ] Executes `hermes gateway` with the TS3 adapter
  - [ ] Handles graceful shutdown (SIGTERM → stop gateway, stop Xvfb, cleanup PulseAudio)
- [ ] `docker/healthcheck.sh`: verifies Xvfb running, PulseAudio daemon reachable, TS3 client connected
- [ ] README section: Docker deployment instructions with example `docker-compose.yml`

## Linked Files

- `Dockerfile` — new: container image
- `docker-compose.yml` — new: orchestration
- `docker/entrypoint.sh` — new: startup script
- `docker/healthcheck.sh` — new: container health check

## Comments and Notes

- PulseAudio in Docker requires either socket passthrough from host or running a PulseAudio daemon inside the container. For simplicity, the container runs its own PulseAudio daemon (no host audio dependency).
- The TS3 client connects over the network to the TS3 server — no host networking tricks needed, just outbound TCP/UDP.
- Xvfb runs on display `:99` with a minimal screen (1280x1024x24). The TS3 client's GUI is invisible but functional.
- Container health check validates the full stack: Xvfb → PulseAudio → TS3 client connected → ServerQuery reachable.

## Depends On

- PBI-003 — TS3 client download script and audio setup script
- PBI-005 — adapter must be functional to test end-to-end in Docker
