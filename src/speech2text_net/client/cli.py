from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..core.clipboard import copy_text_to_clipboard
from ..core.config import AppConfig
from ..core.logging import Logger
from ..core.media import pause_media_playback, resume_media_playback
from ..core.recording import LocalRecordingResult, record_interactive, record_timed
from ..core.utils import format_hms
from .api import regenerate_transcript, resolve_server_url, update_title, upload_wav


def register_client_subcommand(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "client",
        help="Run the Linux client role.",
    )
    parser.add_argument("input_wav", nargs="?", help="Optional local WAV file to upload.")
    parser.add_argument("--seconds", type=int, help="Record locally for a fixed number of seconds before upload.")
    parser.set_defaults(handler=run_client)


def _resolve_input_wav(args: argparse.Namespace, config: AppConfig, logger: Logger) -> tuple[Path, LocalRecordingResult | None]:
    if args.input_wav:
        wav_path = Path(args.input_wav).expanduser().resolve(strict=False)
        if not wav_path.is_file():
            raise RuntimeError(f"Input WAV not found: {wav_path}")
        if wav_path.suffix.lower() != ".wav":
            raise RuntimeError("Input file must end with .wav")
        return wav_path, None

    if args.seconds is not None:
        media_state = pause_media_playback(config, logger)
        try:
            recording = record_timed(config, logger, args.seconds)
        finally:
            resume_media_playback(config, logger, media_state)
    else:
        media_state = pause_media_playback(config, logger)
        try:
            recording = record_interactive(config, logger)
        finally:
            resume_media_playback(config, logger, media_state)
    return recording.wav_path, recording


def input_with_prefill(prompt: str, default_text: str) -> str:
    try:
        import readline
    except Exception:
        return input(prompt)

    def hook() -> None:
        readline.insert_text(default_text)
        readline.redisplay()

    readline.set_startup_hook(hook)
    try:
        return input(prompt)
    finally:
        readline.set_startup_hook()


def _copy_transcript_if_enabled(config: AppConfig, logger: Logger, transcript: str) -> None:
    if config.enable_clipboard:
        if copy_text_to_clipboard(transcript):
            logger.line("Clipboard", "Transcript copied to clipboard.")
        else:
            logger.warn("Clipboard tool not found or clipboard copy failed.")
    else:
        logger.line("Clipboard", "Disabled via configuration.")


def _display_response(
    logger: Logger,
    response: dict,
    *,
    local_recording: LocalRecordingResult | None,
) -> None:
    transcript = str(response.get("transcript", "")).strip()
    title = str(response.get("title", "")).strip()
    artifacts = response.get("artifacts", {}) or {}
    timings = response.get("timings", {}) or {}
    transcribe_seconds = int(timings.get("transcribe_duration_seconds", 0) or 0)

    logger.line("Status", "Done.")
    logger.line("Mode", "Local client -> remote server transcription")
    if title:
        logger.title_value("Server title:", title)
    if transcript:
        logger.transcript_line(transcript)
    if local_recording:
        logger.line("Local", str(local_recording.wav_path))
        logger.line("Summary", f"Recording start: {local_recording.start_human}")
        logger.line("Summary", f"Recording stop: {local_recording.stop_human}")
        logger.line(
            "Summary",
            f"Recording duration: {format_hms(local_recording.duration_seconds)} ({local_recording.duration_seconds}s)",
        )
        if transcribe_seconds > 0:
            ratio = local_recording.duration_seconds / transcribe_seconds
            logger.line("Summary", f"Recording:Transcribe ratio: {ratio:.2f}:1")
    logger.line("Audio", str(artifacts.get("audio_path", "")))
    logger.line("Text", str(artifacts.get("text_path", "")))
    logger.line("Summary", f"Transcribe start: {timings.get('transcribe_start', '')}")
    logger.line("Summary", f"Transcribe stop: {timings.get('transcribe_stop', '')}")
    logger.line(
        "Summary",
        f"Transcribe duration: {timings.get('transcribe_duration_hms', '')} ({timings.get('transcribe_duration_seconds', '')}s)",
    )


def _interactive_change_loop(
    config: AppConfig,
    logger: Logger,
    *,
    server_url: str,
    local_recording: LocalRecordingResult | None,
    response: dict,
) -> dict:
    current = dict(response)
    if not sys.stdin.isatty():
        return current
    while True:
        choice = input(
            logger.prompt_prefix(
                "Prompt",
                "Change anything? [0=OK,1=Regenerate title,2=Regenerate transcript,3=Enter title]",
            )
        ).strip()
        if choice in {"", "0"}:
            return current

        artifacts = current.get("artifacts", {}) or {}
        current_title = str(current.get("title", "")).strip()
        audio_path = str(artifacts.get("audio_path", "")).strip()
        text_path = str(artifacts.get("text_path", "")).strip()

        if choice == "1":
            logger.line("Title", "Regenerating title via server...")
            try:
                title_response = update_title(
                    server_url,
                    config,
                    audio_path=audio_path,
                    text_path=text_path,
                    current_title=current_title,
                    mode="auto",
                )
            except Exception as exc:
                logger.warn(str(exc))
                continue
            current["title"] = title_response.get("title", current_title)
            current["artifacts"] = title_response.get("artifacts", artifacts)
            if current.get("title"):
                logger.title_value("Server title:", str(current.get("title", "")))
            logger.line("Audio", str((current.get("artifacts", {}) or {}).get("audio_path", "")))
            logger.line("Text", str((current.get("artifacts", {}) or {}).get("text_path", "")))
            continue

        if choice == "2":
            logger.line("Whisper", "Regenerating transcript via server...")
            try:
                current = regenerate_transcript(
                    server_url,
                    config,
                    audio_path=audio_path,
                    current_title=current_title,
                )
            except Exception as exc:
                logger.warn(str(exc))
                continue
            _display_response(logger, current, local_recording=local_recording)
            _copy_transcript_if_enabled(config, logger, str(current.get("transcript", "")).strip())
            continue

        if choice == "3":
            raw = input_with_prefill(logger.prompt_prefix("Prompt", "Enter custom title:"), current_title)
            if not raw.strip():
                logger.warn("Custom title is empty; skipping.")
                continue
            logger.line("Title", "Applying custom title via server...")
            try:
                title_response = update_title(
                    server_url,
                    config,
                    audio_path=audio_path,
                    text_path=text_path,
                    current_title=current_title,
                    mode="custom",
                    custom_title=raw,
                )
            except Exception as exc:
                logger.warn(str(exc))
                continue
            current["title"] = title_response.get("title", current_title)
            current["artifacts"] = title_response.get("artifacts", artifacts)
            if current.get("title"):
                logger.title_value("Server title:", str(current.get("title", "")))
            logger.line("Audio", str((current.get("artifacts", {}) or {}).get("audio_path", "")))
            logger.line("Text", str((current.get("artifacts", {}) or {}).get("text_path", "")))
            continue

        logger.warn(f"Unknown choice: {choice}")


def run_client(args: argparse.Namespace, config: AppConfig, logger: Logger) -> int:
    try:
        wav_path, local_recording = _resolve_input_wav(args, config, logger)
    except KeyboardInterrupt:
        print("", flush=True)
        logger.warn("Recording interrupted.")
        return 130
    except Exception as exc:
        logger.error(str(exc))
        return 2

    try:
        server_url, health = resolve_server_url(config)
    except Exception as exc:
        logger.error(str(exc))
        return 2

    logger.line("Client", f"Using server: {server_url}")
    if health:
        logger.line("Client", f"Server status: {health.get('status', 'unknown')}")
        logger.line("Client", f"Server auth mode: {health.get('auth_mode', 'unknown')}")
        if health.get("version"):
            logger.line("Client", f"Server version: {health.get('version')}")
    if local_recording:
        logger.line("Recording", f"Local WAV: {local_recording.wav_path}")
    logger.line("Client", f"Uploading WAV: {wav_path}")

    try:
        response = upload_wav(server_url, config, wav_path)
    except KeyboardInterrupt:
        print("", flush=True)
        logger.warn("Upload/transcription interrupted.")
        return 130
    except Exception as exc:
        logger.error(f"Upload/transcription failed: {exc}")
        return 1

    _display_response(logger, response, local_recording=local_recording)
    _copy_transcript_if_enabled(config, logger, str(response.get("transcript", "")).strip())
    response = _interactive_change_loop(
        config,
        logger,
        server_url=server_url,
        local_recording=local_recording,
        response=response,
    )
    return 0
