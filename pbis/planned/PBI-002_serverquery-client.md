# PBI-002: TS3 ServerQuery Client

**Status:** Planned
**Priority:** High
**Created:** 2026-06-16
**Completed:**

## Description

Implement an async Python client for the TeamSpeak 3 ServerQuery protocol (TCP port 10011). This provides the control plane for the adapter — connecting to the server, moving the bot client between channels, sending/receiving text messages, listing clients, and monitoring events. Pure protocol work with no dependency on other PBIs.

## Acceptance Criteria

- [ ] `TS3ServerQuery` async context manager class with `connect()`, `disconnect()`, and `execute(command)` methods
- [ ] Connection handshake: receive welcome banner, send `login` with credentials, send `use` to select virtual server
- [ ] Client operations: `client_move(client_id, channel_id)`, `client_list()`, `client_info(client_id)`, `client_get_id_by_nickname(nickname)`
- [ ] Channel operations: `channel_list()`, `channel_info(channel_id)`, `channel_find(name)`
- [ ] Messaging: `send_text_message(target_mode, target_id, message)` supporting channel and private messages
- [ ] Event registration: `servernotifyregister` for text messages and client events
- [ ] Async event iterator: yields parsed events (`text message`, `client enter view`, `client left view`, `client moved`) as structured dataclasses
- [ ] Automatic keep-alive: `whoami` or empty command sent periodically to prevent connection timeout
- [ ] Auto-reconnect on connection loss with configurable backoff (initial 1s, max 60s, exponential)
- [ ] Error handling: raises typed exceptions for ServerQuery error codes (`error id=1541 msg=invalid\sparameter` → `TS3QueryError`), connection errors (`TS3ConnectionError`)
- [ ] Response parsing: handles TS3's `key=value key=value|key=value` pipe-delimited format, returns list of dicts

## Linked Files

- `src/hermes_agent_ts3/server_query.py` — new: TS3ServerQuery class, event parsing, reconnection
- `src/hermes_agent_ts3/server_query_types.py` — new: dataclasses for events, errors, responses

## Comments and Notes

- ServerQuery uses a telnet-like text protocol (escape sequences, pipe/space delimiters). Existing Python libraries exist (`teamspeak3-python-api`) but are synchronous and query-only (no voice). We build a lightweight async implementation focused on the operations the adapter needs.
- TS3 ServerQuery can be locked behind a `serverquery_password` or API key — config must support both.
- Keep-alive interval: 120s (server default timeout is typically 300s).

## Depends On

- None (protocol-level work, independent)
