# PBI-001: Project Scaffolding & Hermes Plugin Registration

**Status:** Planned
**Priority:** High
**Created:** 2026-06-16
**Completed:**

## Description

Create the `hermes-agent-ts3` Python package skeleton with proper project structure, build configuration, and Hermes plugin registration. This establishes the foundation all other PBIs build upon — directory layout, `pyproject.toml`, plugin metadata, and environment variable declarations.

## Acceptance Criteria

- [ ] `pyproject.toml` with package metadata, Hermes entry point (`[project.entry-points."hermes.platforms"]`), and dependencies (`hermes-agent>=0.16.0`)
- [ ] `src/hermes_agent_ts3/__init__.py` with package version
- [ ] `src/hermes_agent_ts3/plugin.yaml` declaring platform name (`teamspeak3`), label, emoji, required env vars, and `register()` entry point
- [ ] `src/hermes_agent_ts3/config.py` with `TS3Config` dataclass holding all configuration (server host/port, identity path, home channel, allowed users list, allowed channels list, voice settings)
- [ ] Environment variables declared: `TS3_SERVER_HOST`, `TS3_SERVERQUERY_PORT`, `TS3_VOICE_PORT`, `TS3_HOME_CHANNEL`, `TS3_ALLOWED_USERS`, `TS3_ALLOWED_CHANNELS`, `TS3_IDENTITY_FILE`
- [ ] `README.md` with project overview, prerequisites (Xvfb, PulseAudio, TS3 Linux client), and quickstart
- [ ] `.gitignore` covering Python artifacts, virtual envs, and generated TS3 identity files
- [ ] Package installs cleanly: `pip install -e .`

## Linked Files

- `pyproject.toml` — new: build config, dependencies, entry points
- `src/hermes_agent_ts3/__init__.py` — new: version, package docs
- `src/hermes_agent_ts3/plugin.yaml` — new: Hermes plugin metadata
- `src/hermes_agent_ts3/config.py` — new: TS3Config dataclass
- `README.md` — new: project documentation
- `.gitignore` — new: Python/IDE artifacts

## Comments and Notes

- Hermes plugin discovery works via pip entry points: `hermes.platforms` group with a `register()` function that calls `ctx.register_platform()`
- `plugin.yaml` declares env vars, allowed users env, emoji, label — Hermes gateway auto-wires these
- `TS3Config` consolidates all configuration; loaded from env vars with defaults where sensible

## Depends On

- None (foundation PBI)
