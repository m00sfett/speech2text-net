# speech2text-net

Network-capable successor project for `speech2text`.

## Status
- Working version: `0.8.0`
- Public-repo preparation in progress
- Local reference project remains untouched in `~/speech2text`
- One shared Python codebase for client and server roles

## Goal
Build one Python project that supports:
- secure server mode on the main workstation
- Linux CLI client mode on other machines
- future Android app support via the same backend API

## Roles
- `client` — local recording and WAV upload from a Linux machine
- `server` — authenticated transcription API backend
- `doctor` — local diagnostics and resolved-config inspection
- internal package layers:
  - `core`
  - `client`
  - `server`
  - `shared`

## Repository Layout
- `src/speech2text_net/` — Python package
- `tests/` — automated tests
- `configs/` — public example configurations
- `docs/` — additional notes
- `output/` — runtime artifacts, not committed
- `releases/` — future release artifacts, not committed
- `speech2text-net.conf.example` — repo-local development example
- `install.sh` — interactive installer for client, server, or combined workstation use

## Local Files Not Meant For Git
These stay local and are ignored by git:
- `speech2text-net.conf`
- `.secrets/`
- `speech2text-net.log`
- `output/*`
- `releases/*`
- `project-notes.md`

## Configuration Discovery
By default the application looks for its config in this order:
1. `--config /path/to/file.conf`
2. `S2TNET_CONFIG=/path/to/file.conf`
3. `./speech2text-net.conf` in the current working directory
4. `speech2text-net.conf` in the repo root when running from a checkout
5. `~/.config/speech2text-net/speech2text-net.conf`

Value precedence remains:
1. CLI arguments
2. config file
3. environment variables

Relative paths inside a config file are resolved against the directory of that config file.

Useful advanced options:
- `CLIENT_LOG_FILE` / `SERVER_LOG_FILE` for separated logs in combined setups
- `RECORD_BACKEND=auto|parecord|pw-record|arecord`
- `RECORD_DEVICE=` to override the backend-specific input source/device

## Quick Start From A Git Checkout
Development-style invocation:

```bash
cd ~/speech2text-net
PYTHONPATH=src python3 -m speech2text_net --version
PYTHONPATH=src python3 -m speech2text_net doctor
PYTHONPATH=src python3 -m speech2text_net server --foreground
PYTHONPATH=src python3 -m speech2text_net client /path/to/input.wav
PYTHONPATH=src python3 -m speech2text_net client
PYTHONPATH=src python3 -m speech2text_net client --seconds 5
PYTHONPATH=src python3 -m speech2text_net -m client
PYTHONPATH=src python3 -m speech2text_net -M client
```

## Install For Real Usage
The repo now includes an installer:

```bash
./install.sh
```

It installs into user space:
- command wrapper: `~/.local/bin/speech2text-net`
- virtualenv: `~/.local/share/speech2text-net/venv`
- config: `~/.config/speech2text-net/speech2text-net.conf`
- token file: `~/.config/speech2text-net/.secrets/speech2text-net.token`
- runtime/log defaults: under `~/.local/share/speech2text-net/` and `~/.local/state/speech2text-net/`

Installer profiles:
- `client`
- `server`
- `all`

You can also pass the profile directly:

```bash
./install.sh client
./install.sh server
./install.sh all
```

## Example Configs
Public-safe example configs are included in:
- `configs/client.example.conf`
- `configs/server-local.example.conf`
- `configs/server-tailscale.example.conf`
- `configs/workstation.example.conf`

## Current Capabilities
- `client` can upload a WAV file to a reachable server
- `client` can record locally when no WAV is given, then upload that recording
- the client now prefers Pulse/PipeWire recording backends over raw ALSA when available
- clearly silent recordings are detected before upload to avoid repeated Whisper hallucinations
- `client` copies the returned transcript to the local clipboard when enabled
- `client` supports media handling modes during recording:
  - default: pause + mute where possible
  - `-M` / `--mute-only`: mute without MPRIS pause
  - `-m` / `--nomute`: leave PC audio unchanged
- `client` includes an interactive post-run loop:
  - `0` OK
  - `1` Regenerate title
  - `2` Regenerate transcript
  - `3` Enter title
- `server` exposes:
  - `GET /health`
  - `POST /v1/transcriptions`
  - `POST /v1/transcriptions/regenerate`
  - `POST /v1/titles`
- WAV uploads are accepted and transcribed synchronously
- the server uses Whisper directly, with optional Ollama title generation and optional GPU cleanup
- when GPU cleanup is enabled it runs:
  - before transcription
  - between transcription and title generation
  - after title generation / rename
- responses include transcript text, timing data, and output artifact paths
- `doctor` reports toolchain, path readiness, and candidate server reachability

## Security Model
- If an API token is configured, requests require `Authorization: Bearer ...`
- If no token is configured, the server is only allowed to bind to localhost
- This keeps development mode safe without opening an unauthenticated remote endpoint
- Preferred remote transport is Tailscale, not an open internet listener

## Security direction
- prefer Tailscale
- no open unauthenticated network endpoint
- SSH remains for admin/debug, not normal speech workflow

## Tailscale Test Flow
On the main workstation:

```bash
speech2text-net doctor
speech2text-net server --foreground
```

On the laptop:

```bash
speech2text-net doctor
speech2text-net client
```

For a remote laptop client:
- install with `./install.sh client`
- set `SERVER_URL` to the server's Tailscale URL or IP
- place the shared API token into `~/.config/speech2text-net/.secrets/speech2text-net.token`
- keep `AUTO_DETECT_LOCAL_SERVER=1` if you also want the same config to work on the workstation itself

## Tests
Run the current automated test suite with:

```bash
cd ~/speech2text-net
PYTHONPATH=src python3 -m unittest discover -s tests -v
```
