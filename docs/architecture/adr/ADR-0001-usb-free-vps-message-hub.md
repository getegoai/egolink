# ADR-0001: USB-Free VPS Message Hub For P0 Development

- Status: accepted
- Date: 2026-06-27
- Deciders: user, codex

## Context

Ego Link P0 already has useful PC Development Bridge evidence, but GNSS and
field testing expose a hard constraint: the device cannot depend on a host PC
USB cable while it is carried outdoors. The PC bridge is still valuable for
debugging, recording, quality gates, and replay, but it must not become the
runtime path that proves product behavior.

The project also has a public VPS available for P0 message-service deployment.
That VPS already hosts GitLab, which is out of scope for Ego Link message-hub
work and must not be modified by message-service tasks.

## Decision

P0 development adopts a USB-Free, VPS Message-First, Demo-Driven, Contract-First
Walking Skeleton flow:

- Formal runtime and field-test acceptance uses a device-to-VPS-to-Web message
  path, not USB serial or direct PC attachment.
- USB remains allowed for flashing, temporary debugging, and post-failure log
  export.
- The Public VPS Message Hub is the default target for P0 message-service,
  command-queue, dashboard, and field-test observation work.
- PC Simulator and PC Development Bridge remain development tools. They may
  connect to the VPS as clients or provide replay evidence, but they are not the
  product runtime dependency.
- Firmware, Server-Web, and Protocol work evolve as separate versioned tracks,
  with every release preserving a demonstrable end-to-end loop.
- Protocol changes must be documented before firmware, PC simulator, server, or
  web code consumes them.

## Consequences

- New work should be framed as R0-R4 Walking Skeleton tasks with explicit
  allowed paths, out-of-scope paths, and Definition of Done.
- Field-test evidence must come from the VPS, Web Dashboard, server logs, or
  exported reports. Serial logs may support debugging but cannot be the only
  acceptance evidence.
- Existing local MQTT and PC bridge behavior remains valid as development
  evidence, but future field tasks must migrate toward the VPS message path.
- The VPS deployment must protect existing GitLab services and must not store
  credentials, tokens, IP allowlists, or private device logs in the repository.

## Links

- `../../development/DEV_FLOW.md`
- `../../development/VPS_MESSAGE_HUB.md`
- `../../development/FIELD_TEST.md`
- `../../current/ROADMAP_EGOLINK_P0.md`
