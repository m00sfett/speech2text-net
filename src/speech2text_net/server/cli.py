from __future__ import annotations

import argparse

from ..core.config import AppConfig
from ..core.logging import Logger
from .app import build_http_server
from .auth import auth_mode


def register_server_subcommand(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "server",
        help="Run the local or remote speech2text server role.",
    )
    parser.add_argument("--foreground", action="store_true", help="Stay in foreground mode.")
    parser.set_defaults(handler=run_server)


def run_server(args: argparse.Namespace, config: AppConfig, logger: Logger) -> int:
    if not args.foreground:
        logger.line("Server", "No background mode yet; starting in foreground.")

    try:
        server = build_http_server(config, logger)
    except ValueError as exc:
        logger.error(str(exc))
        return 2

    logger.line("Server", f"Listening on http://{config.server_host}:{config.server_port}")
    logger.line("Auth", f"Mode: {auth_mode(config)}")
    if config.api_token:
        logger.line("Auth", f"Token source: {config.api_token_source}")
    else:
        logger.warn("No API token configured. Server is allowed only on localhost.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.warn("Interrupted. Shutting down server.")
    finally:
        server.shutdown()
        server.server_close()
        logger.line("Server", "Stopped.")
    return 0
