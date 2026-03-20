from __future__ import annotations

import http.client
import json
from pathlib import Path
from urllib.parse import urlparse

from ..core.config import AppConfig
from ..shared import RegenerateTranscriptRequest, TitleRequest


def _headers(config: AppConfig) -> dict[str, str]:
    headers: dict[str, str] = {}
    if config.api_token:
        headers["Authorization"] = f"Bearer {config.api_token}"
    return headers


def candidate_server_urls(config: AppConfig) -> list[str]:
    urls: list[str] = []
    local_url = f"http://127.0.0.1:{config.server_port}"
    if config.autodetect_local_server:
        urls.append(local_url)
    configured = config.server_url.strip()
    if configured and configured not in urls:
        urls.append(configured)
    if not urls:
        urls.append(local_url)
    return urls


def check_health(url: str, config: AppConfig, timeout: int = 3) -> tuple[bool, dict]:
    parsed = urlparse(url)
    connection = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=timeout)
    try:
        connection.request("GET", "/health", headers=_headers(config))
        response = connection.getresponse()
        body = response.read().decode("utf-8", errors="replace")
        data = json.loads(body) if body else {}
        return response.status == 200, data
    except Exception:
        return False, {}
    finally:
        connection.close()


def resolve_server_url(config: AppConfig) -> tuple[str, dict]:
    for url in candidate_server_urls(config):
        ok, data = check_health(url, config)
        if ok:
            return url, data
    raise RuntimeError("No reachable speech2text-net server found.")


def upload_wav(url: str, config: AppConfig, wav_path: Path, timeout: int = 300) -> dict:
    parsed = urlparse(url)
    connection = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=timeout)
    body = wav_path.read_bytes()
    headers = _headers(config)
    headers.update(
        {
            "Content-Type": "audio/wav",
            "Content-Length": str(len(body)),
            "X-S2T-Filename": wav_path.name,
        }
    )
    try:
        connection.request("POST", "/v1/transcriptions", body=body, headers=headers)
        response = connection.getresponse()
        payload = response.read().decode("utf-8", errors="replace")
        data = json.loads(payload) if payload else {}
        if response.status != 200:
            raise RuntimeError(data.get("message") or data.get("code") or f"Server returned HTTP {response.status}")
        return data
    finally:
        connection.close()


def _post_json(url: str, config: AppConfig, endpoint: str, payload: dict, timeout: int = 300) -> dict:
    parsed = urlparse(url)
    connection = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=timeout)
    body = json.dumps(payload).encode("utf-8")
    headers = _headers(config)
    headers.update(
        {
            "Content-Type": "application/json",
            "Content-Length": str(len(body)),
        }
    )
    try:
        connection.request("POST", endpoint, body=body, headers=headers)
        response = connection.getresponse()
        raw = response.read().decode("utf-8", errors="replace")
        data = json.loads(raw) if raw else {}
        if response.status != 200:
            raise RuntimeError(data.get("message") or data.get("code") or f"Server returned HTTP {response.status}")
        return data
    finally:
        connection.close()


def regenerate_transcript(url: str, config: AppConfig, *, audio_path: str, current_title: str) -> dict:
    payload = RegenerateTranscriptRequest(audio_path=audio_path, current_title=current_title)
    return _post_json(url, config, "/v1/transcriptions/regenerate", payload.to_dict())


def update_title(
    url: str,
    config: AppConfig,
    *,
    audio_path: str,
    text_path: str,
    current_title: str,
    mode: str,
    custom_title: str = "",
) -> dict:
    payload = TitleRequest(
        audio_path=audio_path,
        text_path=text_path,
        current_title=current_title,
        mode=mode,
        custom_title=custom_title,
    )
    return _post_json(url, config, "/v1/titles", payload.to_dict())
