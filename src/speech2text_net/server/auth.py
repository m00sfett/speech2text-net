from __future__ import annotations

from typing import Mapping

from ..core.config import AppConfig, is_loopback_host


def auth_mode(config: AppConfig) -> str:
    if config.api_token:
        return "bearer-token"
    return "local-no-token"


def validate_server_security(config: AppConfig) -> None:
    if config.api_token:
        return
    if not is_loopback_host(config.server_host):
        raise ValueError(
            "Refusing to start a non-local server without an API token. "
            "Set API_TOKEN/API_TOKEN_FILE or bind to localhost."
        )


def is_request_authorized(headers: Mapping[str, str], config: AppConfig) -> bool:
    if not config.api_token:
        return True
    header = headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return False
    token = header[7:].strip()
    return token == config.api_token
