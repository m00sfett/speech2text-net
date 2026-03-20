# AGENTS.md — speech2text-net

This file is for coding agents/bots working in `/home/tobias/speech2text-net`.
It defines the project-specific rules, goals, structure, and next-step architecture for the network-enabled successor to the local `speech2text` project.

## Project Identity
- Project name: `speech2text-net`
- Status: new working directory for the network-capable fork
- Start version: `0.7.0`
- Source lineage: forked conceptually from the local `speech2text` project in `/home/tobias/speech2text`
- Important: do not modify `/home/tobias/speech2text` unless the user explicitly asks for it

## Mission
Build a secure client-server speech-to-text system that:
- keeps the current local UX spirit
- supports a Linux client first
- is designed so Android can be added later as an app client
- works well over Tailscale
- remains safe by default

The local single-machine project remains the stable reference.
This new project is where the network architecture is built.

## High-Level Product Goal
The final system should behave like one cohesive tool:
- on a Linux client, the user runs a CLI command and gets nearly the same experience as the current local tool
- the client records locally, sends audio securely to the server, receives the transcript back, and copies it to the local clipboard
- on the main workstation, the same client should also work out of the box and prefer a local server when available
- later, an Android app should be able to talk to the same backend API

## Core Architecture Decision
Do not build two unrelated programs.
Build one Python project with clearly separated internal roles:

1. `core`
   Shared logic:
   - config loading
   - logging/output formatting
   - transcript/title data structures
   - whisper/ollama/gpu-cleanup orchestration
   - shared validation and security helpers

2. `server`
   Backend worker/API:
   - accepts uploads/jobs from clients
   - runs whisper, ollama, gpu-cleanup
   - returns transcript, title, status, timing, file metadata
   - must be secure by default

3. `client`
   Linux CLI client:
   - records locally
   - uploads audio to server
   - shows progress/result in terminal
   - copies returned transcript to the local clipboard
   - should feel as close as practical to the local tool UX

4. `shared`
   Shared protocol/schema layer:
   - request/response models
   - transport-neutral DTOs
   - future-proof foundation for Android

## Network Strategy
- Primary remote transport: HTTP API over Tailscale
- Primary admin/debug transport: SSH
- Do not use SSH as the normal user-facing speech workflow
- No open unauthenticated LAN/Internet exposure
- Security matters more than convenience

## Connectivity Rules
- The client should first be able to check whether a local server is available
- On the main workstation, local server use should work with minimal or no extra configuration
- If no local server is found, remote configuration should be possible
- Tailscale is the preferred remote path
- The system must be designed so later Android clients can reuse the same API

## Scope Order
Build in this order unless the user redirects:

1. Shared project structure and clean boundaries
2. Core refactor/import of reusable logic from the local project
3. Minimal secure server API
4. Linux CLI client
5. Local-server autodetection and config flow
6. Tailscale-oriented hardening
7. Android readiness in protocol/API design

## Explicit Non-Goals For The First Iterations
- No Android app yet
- No browser UI yet
- No public Internet exposure
- No live streaming transport as the first implementation
- No duplicate codebase for local vs remote if shared modules can avoid it

## Implementation Guidance
- Prefer a package layout under `src/speech2text_net/`
- Keep the code modular from the start
- Avoid large monolithic scripts
- Keep interfaces explicit and typed where practical
- Treat the old local `speech2text` project as the behavioral reference, not as a file that must be copied wholesale

## Suggested Initial Module Responsibilities
- `core/config.py`
  - config precedence and path handling
- `core/logging.py`
  - terminal output and logfile behavior
- `core/transcribe.py`
  - whisper execution and fallback behavior
- `core/title.py`
  - ollama title generation and slug handling
- `core/media.py`
  - optional local-only media pause/mute helpers
- `core/cleanup.py`
  - gpu-cleanup integration
- `shared/models.py`
  - request/response models
- `server/app.py`
  - API startup and route registration
- `client/cli.py`
  - client entrypoint and CLI UX

## Security Requirements
- Secure by default
- No unauthenticated remote transcription endpoint
- Plan for token-based auth
- Prefer bind-to-localhost or explicit trusted interface binding
- Tailscale is preferred over exposing raw LAN services
- Keep secrets out of logs and chat output

## UX Requirements
- Preserve the "speech2text feeling" where practical
- Remote mode should still show useful status lines
- Client should copy the returned transcript to the local clipboard by default
- Remote behavior should be explicit in output so the user knows where the job is running

## Local vs Remote Behavior
- The old local-only project remains the stable baseline in `/home/tobias/speech2text`
- This project may later include a local mode as well, but the design target is client/server first
- On the main machine, using the same client as remote Linux clients is preferred

## Versioning
- Start from `0.7.0` in this new project because it forks from the current local project state conceptually
- Do not create release archives until the user explicitly asks

## Directory Rules
- `src/` contains the Python package
- `tests/` contains tests
- `docs/` contains architecture notes and protocol docs
- `output/` may be used for runtime/output artifacts when helpful during development
- `releases/` stays empty until release work is explicitly requested

## Change Workflow Expectations
When modifying this project:
1. Make backups under `/home/tobias/.agent/backup/<YYYY-MM-DD>/` before changing existing files.
2. Keep diffs small and intentional.
3. Keep `README.md`, `AGENTS.md`, config defaults, and CLI behavior aligned.
4. Run validation that matches the work performed.
5. Verify ownership/perms after file operations.
6. Document work in `/home/tobias/.agent/workspace/logs/` and `/home/tobias/.agent/protocols/`.

## Immediate Plan For This Project
The next implementation steps should follow this plan:

1. Establish the package skeleton and project metadata
2. Define shared config and protocol models
3. Build a minimal authenticated server endpoint for WAV upload
4. Build a Linux CLI client that uploads a WAV and receives a transcript
5. Add local clipboard copy on the client side
6. Add local-server autodetection before remote fallback
7. Add Tailscale-friendly configuration and docs

## Command Expectations
Eventually the project should expose role-aware commands such as:
- `speech2text-net server`
- `speech2text-net client`
- `speech2text-net doctor`

The exact CLI may evolve, but the project should remain one unified tool.
