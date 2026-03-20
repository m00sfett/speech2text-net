from __future__ import annotations

import re
from dataclasses import dataclass, field

from .config import AppConfig
from .logging import Logger
from .shell import command_exists, run_capture


@dataclass(slots=True)
class MediaState:
    paused_players: list[str] = field(default_factory=list)
    muted_sink_inputs: list[str] = field(default_factory=list)
    mpris_backend: str = ""


def list_mpris_bus_services() -> list[str]:
    if not command_exists("busctl"):
        return []
    rc, out, _ = run_capture(["busctl", "--user", "--no-pager", "list"])
    if rc != 0:
        return []
    services: list[str] = []
    for line in out.splitlines():
        cols = line.split()
        if cols and cols[0].startswith("org.mpris.MediaPlayer2."):
            services.append(cols[0])
    return services


def get_mpris_status_dbus(service: str) -> str:
    rc, out, _ = run_capture(
        [
            "busctl",
            "--user",
            "get-property",
            service,
            "/org/mpris/MediaPlayer2",
            "org.mpris.MediaPlayer2.Player",
            "PlaybackStatus",
        ]
    )
    if rc != 0:
        return ""
    match = re.search(r'"([^"]+)"', out)
    return match.group(1) if match else ""


def call_mpris_dbus(service: str, method: str) -> bool:
    rc, _, _ = run_capture(
        [
            "busctl",
            "--user",
            "call",
            service,
            "/org/mpris/MediaPlayer2",
            "org.mpris.MediaPlayer2.Player",
            method,
        ]
    )
    return rc == 0


def collect_browser_sink_inputs_detailed() -> list[dict]:
    if not command_exists("pactl"):
        return []
    rc, out, _ = run_capture(["pactl", "list", "sink-inputs"])
    if rc != 0:
        return []

    items: list[dict] = []
    current: dict | None = None
    for line in out.splitlines():
        match = re.match(r"^Sink Input #(\d+)", line)
        if match:
            if current and current.get("is_browser"):
                items.append(current)
            current = {
                "id": match.group(1),
                "state": "unknown",
                "mute": "unknown",
                "corked": "unknown",
                "is_browser": False,
            }
            continue
        if current is None:
            continue
        stripped = line.strip()
        if stripped.startswith("State:"):
            current["state"] = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("Mute:"):
            current["mute"] = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("Corked:"):
            current["corked"] = stripped.split(":", 1)[1].strip()
        elif (
            'application.name = "Google Chrome"' in stripped
            or 'application.name = "Chromium"' in stripped
            or 'application.name = "Brave"' in stripped
            or 'application.name = "Firefox"' in stripped
        ):
            current["is_browser"] = True
        elif (
            'application.process.binary = "chrome"' in stripped
            or 'application.process.binary = "chromium"' in stripped
            or 'application.process.binary = "brave"' in stripped
            or 'application.process.binary = "firefox"' in stripped
        ):
            current["is_browser"] = True
    if current and current.get("is_browser"):
        items.append(current)
    return items


def collect_browser_sink_input_ids() -> list[str]:
    return [item["id"] for item in collect_browser_sink_inputs_detailed()]


def mute_browser_sink_inputs(logger: Logger, state: MediaState, *, include_inactive: bool = False) -> None:
    state.muted_sink_inputs = []
    if not command_exists("pactl"):
        logger.warn("pactl not found, browser-stream mute unavailable.")
        return

    muted = 0
    skipped_inactive = 0
    skipped_muted = 0
    for item in collect_browser_sink_inputs_detailed():
        sink_id = item["id"]
        sink_state = item.get("state", "")
        corked = item.get("corked", "")
        mute = item.get("mute", "")

        if (not include_inactive) and (sink_state != "RUNNING" or str(corked).lower() == "yes"):
            skipped_inactive += 1
            continue
        if str(mute).lower() == "yes":
            skipped_muted += 1
            continue

        rc, _, _ = run_capture(["pactl", "set-sink-input-mute", sink_id, "1"])
        if rc == 0:
            state.muted_sink_inputs.append(sink_id)
            muted += 1

    if muted > 0:
        logger.line("Media", f"Muted {muted} browser audio stream(s) via pactl.")
    elif skipped_inactive > 0 and not include_inactive:
        logger.line("Media", f"Detected {skipped_inactive} inactive/paused browser audio stream(s); skipping mute.")
    else:
        if include_inactive:
            logger.line("Media", "No browser audio stream detected for mute-only.")
        else:
            logger.line("Media", "No active browser audio stream detected.")

    if skipped_muted > 0:
        logger.line("Media", f"Detected {skipped_muted} already-muted browser audio stream(s).")


def unmute_browser_sink_inputs(logger: Logger, state: MediaState) -> None:
    if not command_exists("pactl") or not state.muted_sink_inputs:
        return

    okay = 0
    failed = 0
    for sink_id in state.muted_sink_inputs:
        rc, _, _ = run_capture(["pactl", "set-sink-input-mute", sink_id, "0"])
        if rc == 0:
            okay += 1
        else:
            failed += 1

    if okay > 0:
        logger.line("Media", f"Unmuted {okay} browser audio stream(s).")

    if failed > 0:
        fallback = 0
        for sink_id in collect_browser_sink_input_ids():
            rc, _, _ = run_capture(["pactl", "set-sink-input-mute", sink_id, "0"])
            if rc == 0:
                fallback += 1
        if fallback > 0:
            logger.line("Media", f"Unmuted {fallback} browser audio stream(s) (fallback).")


def pause_media_playback(config: AppConfig, logger: Logger) -> MediaState:
    state = MediaState()
    if not config.enable_media_mute:
        logger.line("Media", "--nomute active (PC audio stays unchanged).")
        return state
    if config.mute_only:
        logger.line("Media", "--mute-only active (no MPRIS pause/resume).")
        mute_browser_sink_inputs(logger, state, include_inactive=True)
        return state

    if command_exists("playerctl"):
        rc, out, _ = run_capture(["playerctl", "-l"])
        if rc == 0:
            for player in out.splitlines():
                player = player.strip()
                if not player:
                    continue
                rc2, status, _ = run_capture(["playerctl", "-p", player, "status"])
                if rc2 == 0 and status.strip() == "Playing":
                    rc3, _, _ = run_capture(["playerctl", "-p", player, "pause"])
                    if rc3 == 0:
                        state.paused_players.append(player)
        state.mpris_backend = "playerctl"
        if state.paused_players:
            logger.line("Media", f"Paused {len(state.paused_players)} MPRIS player(s) via playerctl.")
        else:
            logger.line("Media", "No active MPRIS player detected.")
    elif command_exists("busctl"):
        for service in list_mpris_bus_services():
            if get_mpris_status_dbus(service) == "Playing":
                if call_mpris_dbus(service, "Pause"):
                    state.paused_players.append(service)
        state.mpris_backend = "busctl"
        if state.paused_players:
            logger.line("Media", f"Paused {len(state.paused_players)} MPRIS player(s) via busctl.")
        else:
            logger.line("Media", "No active MPRIS player detected.")
    else:
        logger.warn("Neither playerctl nor busctl found; skipping MPRIS pause.")

    mute_browser_sink_inputs(logger, state)
    return state


def resume_media_playback(config: AppConfig, logger: Logger, state: MediaState) -> None:
    if not config.enable_media_mute:
        return
    if config.mute_only:
        unmute_browser_sink_inputs(logger, state)
        return

    if state.paused_players:
        if state.mpris_backend == "playerctl" and command_exists("playerctl"):
            for player in state.paused_players:
                run_capture(["playerctl", "-p", player, "play"])
            logger.line("Media", f"Resumed {len(state.paused_players)} MPRIS player(s).")
        elif state.mpris_backend == "busctl" and command_exists("busctl"):
            for service in state.paused_players:
                call_mpris_dbus(service, "Play")
            logger.line("Media", f"Resumed {len(state.paused_players)} MPRIS player(s).")

    unmute_browser_sink_inputs(logger, state)
