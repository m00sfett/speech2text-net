from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from . import __version__
from .client.api import candidate_server_urls, check_health
from .client.cli import register_client_subcommand
from .core.config import AppConfig, build_config, cli_overrides_from_namespace
from .core.logging import Logger
from .core.shell import command_exists
from .server.cli import register_server_subcommand


def register_doctor_subcommand(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "doctor",
        help="Inspect resolved project configuration and local project paths.",
    )
    parser.set_defaults(handler=run_doctor)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="speech2text-net",
        description="Network-capable speech-to-text project with unified client and server roles.",
    )
    parser.add_argument("--version", action="store_true", help="Show version and exit.")
    parser.add_argument("--config", help="Path to a config file.")
    parser.add_argument("--model", help="Whisper model name.")
    parser.add_argument("--language", help="Transcription language.")
    parser.add_argument("--device", help="Preferred transcription device.")
    parser.add_argument("--fp16", help="Use fp16 for Whisper execution (1/0, true/false).")
    parser.add_argument("--out-dir", help="Output directory for generated artifacts.")
    parser.add_argument("--model-dir", help="Directory containing Whisper model files.")
    parser.add_argument("--log-file", help="Log file path.")
    parser.add_argument("--client-log-file", help="Client log file path.")
    parser.add_argument("--server-log-file", help="Server log file path.")
    parser.add_argument("--title-model", help="Preferred Ollama model for title generation.")
    parser.add_argument("--title-maxlen", type=int, help="Maximum title slug length.")
    parser.add_argument("--record-backend", help="Recording backend: auto, parecord, pw-record, arecord.")
    parser.add_argument("--record-device", help="Recording device/source override for the selected backend.")
    parser.add_argument("--server-url", help="Remote server URL for the client.")
    parser.add_argument("--server-host", help="Bind host for the local server.")
    parser.add_argument("--server-port", type=int, help="Bind port for the local server.")
    parser.add_argument("--token", help="API token value.")
    parser.add_argument("--token-file", help="Path to the API token file.")
    parser.add_argument("-m", "--nomute", action="store_true", help="Do not pause or mute local media during recording.")
    parser.add_argument("-M", "--mute-only", action="store_true", help="Mute browser audio during recording without pausing MPRIS playback.")
    parser.add_argument("--color", action="store_true", help="Force color output.")
    parser.add_argument("--no-color", action="store_true", help="Disable color output.")
    parser.add_argument("--clipboard", action="store_true", help="Enable clipboard copy.")
    parser.add_argument("--no-clipboard", action="store_true", help="Disable clipboard copy.")
    parser.add_argument("--autodetect-local", action="store_true", help="Prefer automatic local server detection.")
    parser.add_argument("--no-autodetect-local", action="store_true", help="Disable automatic local server detection.")
    parser.add_argument("--quiet", action="store_true", help="Reduce normal status output.")

    subparsers = parser.add_subparsers(dest="command")
    register_server_subcommand(subparsers)
    register_client_subcommand(subparsers)
    register_doctor_subcommand(subparsers)
    return parser


def active_log_file_for_role(config: AppConfig, role: str | None) -> Path:
    if role == "client" and config.client_log_file is not None:
        return config.client_log_file
    if role == "server" and config.server_log_file is not None:
        return config.server_log_file
    return config.log_file


def create_logger(config: AppConfig, role: str | None) -> Logger:
    return Logger(
        log_file=active_log_file_for_role(config, role),
        enable_color=config.enable_color,
        quiet=config.quiet,
        tag="S2T-NET",
    )


def run_doctor(args: argparse.Namespace, config: AppConfig, logger: Logger) -> int:
    logger.line("Version", __version__)
    logger.line("Project", str(config.project_root))
    logger.line("Config", f"Config file: {config.config_file}")
    logger.line("Config", f"Config found: {'yes' if config.config_found else 'no'}")
    logger.line("Paths", f"Output directory: {config.output_dir}")
    logger.line("Paths", f"Model directory: {config.model_dir}")
    logger.line("Paths", f"Log file: {active_log_file_for_role(config, args.command)}")
    if config.client_log_file is not None:
        logger.line("Paths", f"Client log file: {config.client_log_file}")
    if config.server_log_file is not None:
        logger.line("Paths", f"Server log file: {config.server_log_file}")
    logger.line("Server", f"URL: {config.server_url}")
    logger.line("Server", f"Bind: {config.server_host}:{config.server_port}")
    logger.line("Auth", f"Token file: {config.api_token_file}")
    logger.line("Auth", f"Token configured: {'yes' if config.api_token else 'no'}")
    logger.line("Auth", f"Token source: {config.api_token_source}")
    logger.line("Behavior", f"Auto title: {'yes' if config.auto_title else 'no'}")
    logger.line("Behavior", f"Media mute enabled: {'yes' if config.enable_media_mute else 'no'}")
    logger.line("Behavior", f"Mute-only mode: {'yes' if config.mute_only else 'no'}")
    logger.line("GPU", f"Cleanup mode: {config.clean_mode or 'disabled'}")
    logger.line("GPU", f"Cleanup script: {config.gpu_cleanup_path}")
    logger.line("Behavior", f"Clipboard enabled: {'yes' if config.enable_clipboard else 'no'}")
    logger.line("Behavior", f"Local autodetect: {'yes' if config.autodetect_local_server else 'no'}")
    logger.line("Behavior", f"Record backend: {config.record_backend}")
    logger.line("Behavior", f"Record device: {config.record_device or 'default'}")
    logger.line("Checks", f"whisper: {'yes' if command_exists('whisper') else 'no'}")
    logger.line("Checks", f"parecord: {'yes' if command_exists('parecord') else 'no'}")
    logger.line("Checks", f"pw-record: {'yes' if command_exists('pw-record') else 'no'}")
    logger.line("Checks", f"ollama: {'yes' if command_exists('ollama') else 'no'}")
    logger.line("Checks", f"arecord: {'yes' if command_exists('arecord') else 'no'}")
    logger.line("Checks", f"pactl: {'yes' if command_exists('pactl') else 'no'}")
    logger.line("Checks", f"busctl: {'yes' if command_exists('busctl') else 'no'}")
    logger.line("Checks", f"playerctl: {'yes' if command_exists('playerctl') else 'no'}")
    logger.line("Checks", f"wl-copy: {'yes' if command_exists('wl-copy') else 'no'}")
    logger.line("Checks", f"Model dir exists: {'yes' if config.model_dir.exists() else 'no'}")
    logger.line("Checks", f"GPU cleanup script exists: {'yes' if config.gpu_cleanup_path.exists() else 'no'}")
    for url in candidate_server_urls(config):
        ok, data = check_health(url, config, timeout=1)
        if ok:
            version = data.get("version", "unknown")
            status = data.get("status", "ok")
            logger.line("Checks", f"Server reachable: yes ({url}, status={status}, version={version})")
        else:
            logger.line("Checks", f"Server reachable: no ({url})")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(f"speech2text-net {__version__}")
        return 0

    if not args.command:
        parser.print_help()
        return 0

    config = build_config(
        cli_overrides=cli_overrides_from_namespace(args),
        config_path=Path(args.config).expanduser() if args.config else None,
    )
    logger = create_logger(config, args.command)
    try:
        handler = getattr(args, "handler", None)
        if handler is None:
            parser.print_help()
            return 1
        return int(handler(args, config, logger))
    finally:
        logger.close()
