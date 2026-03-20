from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class ApiError:
    code: str
    message: str
    request_id: str
    details: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class HealthResponse:
    service: str
    version: str
    status: str
    request_id: str
    server_time: str
    auth_mode: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class UploadMetadata:
    filename: str
    content_type: str
    bytes_received: int
    stored_path: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class TranscriptionAcceptedResponse:
    service: str
    version: str
    status: str
    request_id: str
    server_time: str
    message: str
    upload: UploadMetadata

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["upload"] = self.upload.to_dict()
        return payload


@dataclass(slots=True)
class TimingSummary:
    transcribe_start: str
    transcribe_stop: str
    transcribe_duration_seconds: int
    transcribe_duration_hms: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class ArtifactPaths:
    audio_path: str
    text_path: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class TranscriptionResponse:
    service: str
    version: str
    status: str
    request_id: str
    server_time: str
    transcript: str
    title: str
    model: str
    language: str
    device_used: str
    title_model_used: str
    timings: TimingSummary
    artifacts: ArtifactPaths

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["timings"] = self.timings.to_dict()
        payload["artifacts"] = self.artifacts.to_dict()
        return payload


@dataclass(slots=True)
class RegenerateTranscriptRequest:
    audio_path: str
    current_title: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class TitleRequest:
    audio_path: str
    text_path: str
    current_title: str = ""
    mode: str = "auto"
    custom_title: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class TitleResponse:
    service: str
    version: str
    status: str
    request_id: str
    server_time: str
    title: str
    title_model_used: str
    artifacts: ArtifactPaths

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["artifacts"] = self.artifacts.to_dict()
        return payload
