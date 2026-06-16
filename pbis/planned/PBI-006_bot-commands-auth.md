# PBI-006: Bot Commands & Authorization

**Status:** Planned
**Priority:** Medium
**Created:** 2026-06-16
**Completed:**

## Description

Implement the bot command system and authorization checks. Users interact with the bot via text commands (`!summon`, `!leave`, `!voice on/off`, `!status`) in TS3 channel chat. Authorization enforces allowed users and allowed channels, with the summon mechanic allowing the bot to be called into permitted channels and a configurable home channel for default idle position.

## Acceptance Criteria

- [ ] Command parser: detects `!` prefixed commands in channel text messages, routes to handler
- [ ] `!summon` — user invokes from a channel; if channel is in `TS3_ALLOWED_CHANNELS` and user is in `TS3_ALLOWED_USERS`, bot moves to user's channel via `client_move` and announces arrival with a text message
- [ ] `!summon` to disallowed channel — bot sends text reply: "I cannot join #channel — this channel is not in my allowed channels list."
- [ ] `!summon` by disallowed user — silently ignored (no response)
- [ ] `!leave` — bot leaves current summoned channel and returns to home channel; announces departure
- [ ] `!voice on` / `!voice off` / `!voice tts` — toggles voice processing modes, matching Hermes voice mode semantics
- [ ] `!status` — replies with current channel, voice mode, uptime, active speakers count
- [ ] `!help` — lists available commands with brief descriptions
- [ ] Authorization checks at two levels:
  - User level: `TS3_ALLOWED_USERS` env var (comma-separated client nicknames or database IDs)
  - Channel level: `TS3_ALLOWED_CHANNELS` env var (comma-separated channel names or IDs)
- [ ] Home channel configuration via `TS3_HOME_CHANNEL` env var or config; bot auto-joins on startup
- [ ] Bot ignores non-command text (does not respond to every message) unless addressed by name (configurable)

## Linked Files

- `src/hermes_agent_ts3/commands.py` — new: command parser, handlers, authorization helpers
- `src/hermes_agent_ts3/config.py` — modify: add command prefix, mention gating config
- `src/hermes_agent_ts3/adapter.py` — modify: wire `handle_message()` to command parser before agent dispatch

## Comments and Notes

- Commands are text-based because TS3 has no native slash command system. The `!` prefix avoids conflicts with existing TS3 bots.
- Authorization is checked at the adapter level — unauthorized users' text and voice are dropped before reaching the agent.
- The home channel concept matches Discord's `DISCORD_HOME_CHANNEL` for cron delivery, but extended: the bot physically sits in this channel when idle.
- Auto-return to home after configurable idle timeout (default: 5 minutes of silence) prevents the bot from lingering in summoned channels indefinitely.

## Depends On

- PBI-002 — ServerQuery client (to send messages and move client)
- PBI-005 — TeamSpeakAdapter (to wire commands into message handling)
