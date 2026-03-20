"""Shared protocol and model layer for speech2text-net."""

from .models import (
    ApiError,
    ArtifactPaths,
    HealthResponse,
    RegenerateTranscriptRequest,
    TimingSummary,
    TitleRequest,
    TitleResponse,
    TranscriptionAcceptedResponse,
    TranscriptionResponse,
    UploadMetadata,
)

__all__ = [
    "ApiError",
    "ArtifactPaths",
    "HealthResponse",
    "RegenerateTranscriptRequest",
    "TimingSummary",
    "TitleRequest",
    "TitleResponse",
    "TranscriptionAcceptedResponse",
    "TranscriptionResponse",
    "UploadMetadata",
]
