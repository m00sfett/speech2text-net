from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .cleanup import run_gpu_cleanup_if_requested
from .config import AppConfig
from .logging import Logger
from .shell import command_exists
from .title import generate_title_from_transcript, ollama_reachable, pick_default_title_model
from .utils import format_hms, now_human, slugify_title, timestamp_slug


@dataclass(slots=True)
class TranscriptionResult:
    transcript: str
    title: str
    audio_path: Path
    text_path: Path
    device_used: str
    title_model_used: str
    transcribe_start_human: str
    transcribe_stop_human: str
    transcribe_duration_seconds: int
    transcribe_duration_hms: str


@dataclass(slots=True)
class TitleOperationResult:
    title: str
    title_model_used: str
    audio_path: Path
    text_path: Path


def _run_whisper(
    config: AppConfig,
    logger: Logger,
    *,
    audio_path: Path,
    output_dir: Path,
    device: str,
    fp16: bool,
) -> tuple[int, str]:
    cmd = [
        "whisper",
        str(audio_path),
        "--model",
        config.model,
    ]
    if config.model_dir:
        cmd.extend(["--model_dir", str(config.model_dir)])
    cmd.extend(
        [
            "--device",
            device,
            "--language",
            config.language,
            "--task",
            "transcribe",
            "--output_dir",
            str(output_dir),
            "--output_format",
            "txt",
            "--fp16",
            "True" if fp16 else "False",
        ]
    )

    env = os.environ.copy()
    env["PYTHONWARNINGS"] = "ignore"
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )
    combined_lines: list[str] = []
    if process.stdout:
        for line in process.stdout:
            line = line.rstrip("\n")
            combined_lines.append(line)
            if line and line.lstrip().startswith("["):
                logger.transcript_line(line)
    rc = process.wait()
    return rc, "\n".join(combined_lines)


def _finalize_title_suffix(audio_path: Path, text_path: Path, title: str) -> tuple[Path, Path]:
    base = audio_path.with_suffix("")
    new_audio = base.with_name(f"{base.name}-{title}").with_suffix(".wav")
    new_text = text_path.with_name(f"{text_path.stem}-{title}").with_suffix(".txt")
    counter = 2
    while new_audio.exists() or new_text.exists():
        new_audio = base.with_name(f"{base.name}-{title}-{counter}").with_suffix(".wav")
        new_text = text_path.with_name(f"{text_path.stem}-{title}-{counter}").with_suffix(".txt")
        counter += 1
    audio_path.rename(new_audio)
    text_path.rename(new_text)
    return new_audio, new_text


def _remove_existing_title_suffix(audio_path: Path, text_path: Path, current_title: str) -> tuple[Path, Path]:
    if not current_title:
        return audio_path, text_path

    suffix = f"-{current_title}"
    audio_base = audio_path.stem
    text_base = text_path.stem
    if audio_base.endswith(suffix):
        audio_base = audio_base[: -len(suffix)]
    if text_base.endswith(suffix):
        text_base = text_base[: -len(suffix)]

    target_audio = audio_path.with_name(audio_base).with_suffix(".wav")
    target_text = text_path.with_name(text_base).with_suffix(".txt")
    if audio_path != target_audio:
        audio_path.rename(target_audio)
    if text_path != target_text:
        text_path.rename(target_text)
    return target_audio, target_text


def _run_transcription_core(
    config: AppConfig,
    logger: Logger,
    *,
    audio_path: Path,
    output_dir: Path,
    requested_device: str,
    log_label: str,
) -> tuple[Path, str, str, str, int, str]:
    run_gpu_cleanup_if_requested(config, logger, phase="pre", requested_device=requested_device)
    logger.line("Whisper", log_label)

    tx_start_epoch = int(time.time())
    tx_start_human = now_human()

    rc, combined_output = _run_whisper(
        config,
        logger,
        audio_path=audio_path,
        output_dir=output_dir,
        device=requested_device,
        fp16=config.fp16,
    )
    text_path = output_dir / f"{audio_path.stem}.txt"
    device_used = requested_device

    oom = bool(re.search(r"OutOfMemoryError|CUDA out of memory", combined_output, flags=re.I))
    if rc != 0 and requested_device == "cuda" and oom:
        logger.warn("CUDA OOM detected. Retrying once on CPU...")
        rc, combined_output = _run_whisper(
            config,
            logger,
            audio_path=audio_path,
            output_dir=output_dir,
            device="cpu",
            fp16=False,
        )
        device_used = "cpu"

    if rc != 0:
        raise RuntimeError("Whisper failed.")
    if not text_path.is_file():
        raise RuntimeError("Whisper finished without producing a transcript file.")

    tx_stop_epoch = int(time.time())
    tx_stop_human = now_human()
    transcript = text_path.read_text(encoding="utf-8", errors="replace").strip()
    duration_seconds = max(0, tx_stop_epoch - tx_start_epoch)
    return text_path, transcript, device_used, tx_start_human, duration_seconds, tx_stop_human


def transcribe_audio_file(
    config: AppConfig,
    logger: Logger,
    *,
    input_wav: Path,
    request_id: str,
) -> TranscriptionResult:
    if not command_exists("whisper"):
        raise RuntimeError("whisper command not found.")
    if not input_wav.is_file():
        raise RuntimeError(f"Input audio file not found: {input_wav}")

    config.output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = timestamp_slug()
    base_stem = f"{timestamp}-{request_id[:8]}"
    final_audio_path = config.output_dir / f"{base_stem}.wav"
    input_wav.replace(final_audio_path)

    requested_device = config.device
    text_path, transcript, device_used, tx_start_human, duration_seconds, tx_stop_human = _run_transcription_core(
        config,
        logger,
        audio_path=final_audio_path,
        output_dir=config.output_dir,
        requested_device=requested_device,
        log_label="Transcribing...",
    )

    run_gpu_cleanup_if_requested(config, logger, phase="between", requested_device=requested_device)

    title = ""
    title_model_used = ""
    if config.auto_title:
        if not ollama_reachable():
            logger.warn("Ollama not reachable; skipping auto title.")
        else:
            title_model_used = config.title_model or pick_default_title_model()
            if title_model_used:
                logger.line("Title", "Generating short title via Ollama...")
                if not config.title_model:
                    logger.line("Title", f"Using default Ollama model: {title_model_used}")
                title = generate_title_from_transcript(config, text_path, chosen_model=title_model_used)
                if title:
                    final_audio_path, text_path = _finalize_title_suffix(final_audio_path, text_path, title)
                    logger.title_value("Renamed files with:", title)
                else:
                    logger.warn("Auto title returned empty; skipping rename.")
            else:
                logger.warn("No installed Ollama models found; skipping auto title.")

    run_gpu_cleanup_if_requested(config, logger, phase="post", requested_device=requested_device)
    return TranscriptionResult(
        transcript=transcript,
        title=title,
        audio_path=final_audio_path,
        text_path=text_path,
        device_used=device_used,
        title_model_used=title_model_used,
        transcribe_start_human=tx_start_human,
        transcribe_stop_human=tx_stop_human,
        transcribe_duration_seconds=duration_seconds,
        transcribe_duration_hms=format_hms(duration_seconds),
    )


def regenerate_transcript_for_existing_audio(
    config: AppConfig,
    logger: Logger,
    *,
    audio_path: Path,
    current_title: str = "",
) -> TranscriptionResult:
    if not command_exists("whisper"):
        raise RuntimeError("whisper command not found.")
    if not audio_path.is_file():
        raise RuntimeError(f"Input audio file not found: {audio_path}")
    if audio_path.suffix.lower() != ".wav":
        raise RuntimeError("Input audio file must end with .wav")

    output_dir = audio_path.parent
    text_path = audio_path.with_suffix(".txt")
    if text_path.exists():
        text_path.unlink()

    requested_device = config.device
    text_path, transcript, device_used, tx_start_human, duration_seconds, tx_stop_human = _run_transcription_core(
        config,
        logger,
        audio_path=audio_path,
        output_dir=output_dir,
        requested_device=requested_device,
        log_label="Regenerating transcript...",
    )

    run_gpu_cleanup_if_requested(config, logger, phase="between", requested_device=requested_device)
    run_gpu_cleanup_if_requested(config, logger, phase="post", requested_device=requested_device)

    return TranscriptionResult(
        transcript=transcript,
        title=current_title,
        audio_path=audio_path,
        text_path=text_path,
        device_used=device_used,
        title_model_used="",
        transcribe_start_human=tx_start_human,
        transcribe_stop_human=tx_stop_human,
        transcribe_duration_seconds=duration_seconds,
        transcribe_duration_hms=format_hms(duration_seconds),
    )


def apply_title_operation(
    config: AppConfig,
    logger: Logger,
    *,
    audio_path: Path,
    text_path: Path,
    current_title: str = "",
    mode: str = "auto",
    custom_title: str = "",
) -> TitleOperationResult:
    if not audio_path.is_file():
        raise RuntimeError(f"Audio file not found: {audio_path}")
    if not text_path.is_file():
        raise RuntimeError(f"Transcript file not found: {text_path}")

    mode = mode.strip().lower()
    title_model_used = ""
    if mode == "auto":
        if not ollama_reachable():
            raise RuntimeError("Ollama not reachable.")
        title_model_used = config.title_model or pick_default_title_model()
        if not title_model_used:
            raise RuntimeError("No installed Ollama models found.")
        logger.line("Title", "Regenerating title via Ollama...")
        if not config.title_model:
            logger.line("Title", f"Using default Ollama model: {title_model_used}")
        title = generate_title_from_transcript(config, text_path, chosen_model=title_model_used)
        if not title:
            raise RuntimeError("Auto title returned empty.")
    elif mode == "custom":
        title = slugify_title(custom_title, config.title_maxlen)
        if not title:
            raise RuntimeError("Custom title is empty after normalization.")
        logger.line("Title", "Applying custom title...")
    else:
        raise RuntimeError(f"Unsupported title mode: {mode}")

    base_audio, base_text = _remove_existing_title_suffix(audio_path, text_path, current_title)
    new_audio, new_text = _finalize_title_suffix(base_audio, base_text, title)
    logger.title_value("Renamed files with:", title)
    run_gpu_cleanup_if_requested(config, logger, phase="post", requested_device=config.device)
    return TitleOperationResult(
        title=title,
        title_model_used=title_model_used,
        audio_path=new_audio,
        text_path=new_text,
    )
