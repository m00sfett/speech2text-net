from __future__ import annotations

import json
import re
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Type
from urllib.parse import urlparse
from uuid import uuid4

from .. import __version__
from ..core.config import AppConfig
from ..core.logging import Logger
from ..core.transcribe import apply_title_operation, regenerate_transcript_for_existing_audio, transcribe_audio_file
from ..shared import (
    ApiError,
    ArtifactPaths,
    HealthResponse,
    TitleResponse,
    TimingSummary,
    TranscriptionResponse,
)
from ..shared.models import utc_now_iso
from .auth import auth_mode, is_request_authorized, validate_server_security


ALLOWED_AUDIO_TYPES = {
    "audio/wav",
    "audio/x-wav",
    "audio/wave",
    "application/octet-stream",
}
FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(slots=True)
class ServerContext:
    config: AppConfig
    logger: Logger


def sanitize_filename(value: str) -> str:
    cleaned = FILENAME_RE.sub("-", value.strip()).strip("-.")
    return cleaned or "audio.wav"


def _request_id(headers: dict[str, str]) -> str:
    value = headers.get("X-Request-Id", "").strip()
    return value or uuid4().hex


def _resolve_output_scoped_path(base_dir: Path, raw_path: str) -> Path:
    candidate = Path(str(raw_path).strip()).expanduser().resolve(strict=False)
    base = base_dir.resolve(strict=False)
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise RuntimeError(f"Path is outside server output directory: {candidate}") from exc
    return candidate


def create_handler(context: ServerContext) -> Type[BaseHTTPRequestHandler]:
    class Speech2TextRequestHandler(BaseHTTPRequestHandler):
        server_version = "speech2text-net"
        sys_version = ""

        def log_message(self, fmt: str, *args) -> None:
            context.logger.line("HTTP", fmt % args)

        def _send_json(self, status_code: int, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_error(self, status_code: int, request_id: str, code: str, message: str, **details: str) -> None:
            payload = ApiError(
                code=code,
                message=message,
                request_id=request_id,
                details={k: str(v) for k, v in details.items() if v not in (None, "")},
            )
            self._send_json(status_code, payload.to_dict())

        def _require_auth(self, request_id: str) -> bool:
            if is_request_authorized(self.headers, context.config):
                return True
            self._send_error(401, request_id, "unauthorized", "Missing or invalid bearer token.")
            return False

        def _read_body(self, request_id: str) -> bytes | None:
            raw_length = self.headers.get("Content-Length", "").strip()
            if not raw_length:
                self._send_error(411, request_id, "length-required", "Content-Length header is required.")
                return None
            try:
                length = int(raw_length)
            except ValueError:
                self._send_error(400, request_id, "bad-length", "Invalid Content-Length header.")
                return None
            if length <= 0:
                self._send_error(400, request_id, "empty-body", "Request body is empty.")
                return None
            return self.rfile.read(length)

        def _read_json_body(self, request_id: str) -> dict | None:
            body = self._read_body(request_id)
            if body is None:
                return None
            try:
                payload = json.loads(body.decode("utf-8"))
            except Exception:
                self._send_error(400, request_id, "invalid-json", "Request body is not valid JSON.")
                return None
            if not isinstance(payload, dict):
                self._send_error(400, request_id, "invalid-json", "JSON body must be an object.")
                return None
            return payload

        def do_GET(self) -> None:
            request_id = _request_id(dict(self.headers.items()))
            path = urlparse(self.path).path
            if path != "/health":
                self._send_error(404, request_id, "not-found", "Unknown endpoint.")
                return
            if not self._require_auth(request_id):
                return
            payload = HealthResponse(
                service="speech2text-net",
                version=__version__,
                status="ok",
                request_id=request_id,
                server_time=utc_now_iso(),
                auth_mode=auth_mode(context.config),
            )
            self._send_json(200, payload.to_dict())

        def do_POST(self) -> None:
            request_id = _request_id(dict(self.headers.items()))
            path = urlparse(self.path).path
            if not self._require_auth(request_id):
                return

            if path == "/v1/transcriptions":
                self._handle_transcription_upload(request_id)
                return
            if path == "/v1/transcriptions/regenerate":
                self._handle_regenerate_transcript(request_id)
                return
            if path == "/v1/titles":
                self._handle_title_operation(request_id)
                return
            self._send_error(404, request_id, "not-found", "Unknown endpoint.")

        def _handle_transcription_upload(self, request_id: str) -> None:

            content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if content_type not in ALLOWED_AUDIO_TYPES:
                self._send_error(
                    415,
                    request_id,
                    "unsupported-media-type",
                    "Only WAV-style uploads are supported at the moment.",
                    received=content_type or "none",
                )
                return

            body = self._read_body(request_id)
            if body is None:
                return

            incoming_dir = context.config.output_dir / "incoming"
            incoming_dir.mkdir(parents=True, exist_ok=True)
            hinted_name = self.headers.get("X-S2T-Filename", "audio.wav")
            filename = sanitize_filename(hinted_name)
            stored_path = incoming_dir / f"{request_id}-{filename}"
            stored_path.write_bytes(body)

            context.logger.line("Server", f"Accepted upload {filename} ({len(body)} bytes).")

            try:
                result = transcribe_audio_file(
                    context.config,
                    context.logger,
                    input_wav=stored_path,
                    request_id=request_id,
                )
            except Exception as exc:
                context.logger.error(f"Transcription failed: {exc}")
                self._send_error(500, request_id, "transcription-failed", str(exc), stored_path=str(stored_path))
                return

            response = TranscriptionResponse(
                service="speech2text-net",
                version=__version__,
                status="ok",
                request_id=request_id,
                server_time=utc_now_iso(),
                transcript=result.transcript,
                title=result.title,
                model=context.config.model,
                language=context.config.language,
                device_used=result.device_used,
                title_model_used=result.title_model_used,
                timings=TimingSummary(
                    transcribe_start=result.transcribe_start_human,
                    transcribe_stop=result.transcribe_stop_human,
                    transcribe_duration_seconds=result.transcribe_duration_seconds,
                    transcribe_duration_hms=result.transcribe_duration_hms,
                ),
                artifacts=ArtifactPaths(
                    audio_path=str(result.audio_path),
                    text_path=str(result.text_path),
                ),
            )
            self._send_json(200, response.to_dict())

        def _handle_regenerate_transcript(self, request_id: str) -> None:
            payload = self._read_json_body(request_id)
            if payload is None:
                return

            try:
                audio_path = _resolve_output_scoped_path(context.config.output_dir, str(payload.get("audio_path", "")))
                current_title = str(payload.get("current_title", "")).strip()
                result = regenerate_transcript_for_existing_audio(
                    context.config,
                    context.logger,
                    audio_path=audio_path,
                    current_title=current_title,
                )
            except Exception as exc:
                context.logger.error(f"Transcript regeneration failed: {exc}")
                self._send_error(500, request_id, "regenerate-transcript-failed", str(exc))
                return

            response = TranscriptionResponse(
                service="speech2text-net",
                version=__version__,
                status="ok",
                request_id=request_id,
                server_time=utc_now_iso(),
                transcript=result.transcript,
                title=result.title,
                model=context.config.model,
                language=context.config.language,
                device_used=result.device_used,
                title_model_used=result.title_model_used,
                timings=TimingSummary(
                    transcribe_start=result.transcribe_start_human,
                    transcribe_stop=result.transcribe_stop_human,
                    transcribe_duration_seconds=result.transcribe_duration_seconds,
                    transcribe_duration_hms=result.transcribe_duration_hms,
                ),
                artifacts=ArtifactPaths(
                    audio_path=str(result.audio_path),
                    text_path=str(result.text_path),
                ),
            )
            self._send_json(200, response.to_dict())

        def _handle_title_operation(self, request_id: str) -> None:
            payload = self._read_json_body(request_id)
            if payload is None:
                return

            try:
                audio_path = _resolve_output_scoped_path(context.config.output_dir, str(payload.get("audio_path", "")))
                text_path = _resolve_output_scoped_path(context.config.output_dir, str(payload.get("text_path", "")))
                current_title = str(payload.get("current_title", "")).strip()
                mode = str(payload.get("mode", "auto")).strip().lower()
                custom_title = str(payload.get("custom_title", ""))
                result = apply_title_operation(
                    context.config,
                    context.logger,
                    audio_path=audio_path,
                    text_path=text_path,
                    current_title=current_title,
                    mode=mode,
                    custom_title=custom_title,
                )
            except Exception as exc:
                context.logger.error(f"Title operation failed: {exc}")
                self._send_error(500, request_id, "title-operation-failed", str(exc))
                return

            response = TitleResponse(
                service="speech2text-net",
                version=__version__,
                status="ok",
                request_id=request_id,
                server_time=utc_now_iso(),
                title=result.title,
                title_model_used=result.title_model_used,
                artifacts=ArtifactPaths(
                    audio_path=str(result.audio_path),
                    text_path=str(result.text_path),
                ),
            )
            self._send_json(200, response.to_dict())

    return Speech2TextRequestHandler


def build_http_server(config: AppConfig, logger: Logger) -> ThreadingHTTPServer:
    validate_server_security(config)
    config.output_dir.mkdir(parents=True, exist_ok=True)
    handler = create_handler(ServerContext(config=config, logger=logger))
    return ThreadingHTTPServer((config.server_host, config.server_port), handler)
