from __future__ import annotations

import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .logging import Logger
from .shell import command_exists
from .utils import now_human, timestamp_slug


@dataclass(slots=True)
class LocalRecordingResult:
    wav_path: Path
    start_human: str
    stop_human: str
    duration_seconds: int


def _recordings_dir(base_dir: Path) -> Path:
    path = base_dir / "client-recordings"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _record_target(base_dir: Path) -> Path:
    return _recordings_dir(base_dir) / f"{timestamp_slug()}.wav"


def record_interactive(base_dir: Path, logger: Logger) -> LocalRecordingResult:
    if not command_exists("arecord"):
        raise RuntimeError("arecord not found (install alsa-utils).")

    wav_path = _record_target(base_dir)
    start_epoch = int(time.time())
    start_human = now_human()

    process = subprocess.Popen(
        ["arecord", "-q", "-f", "S16_LE", "-r", "16000", "-c1", str(wav_path)],
    )
    logger.line("Recording", "Recording started.")
    try:
        input(logger.prompt_prefix("Input", "Press Enter to stop recording:"))
    except KeyboardInterrupt as exc:
        try:
            process.send_signal(signal.SIGINT)
        except Exception:
            pass
        try:
            process.wait(timeout=2)
        except Exception:
            try:
                process.terminate()
            except Exception:
                pass
        if wav_path.exists():
            wav_path.unlink(missing_ok=True)
        raise exc

    try:
        process.send_signal(signal.SIGINT)
    except Exception:
        pass
    try:
        process.wait(timeout=2)
    except Exception:
        try:
            process.terminate()
        except Exception:
            pass
        process.wait(timeout=2)

    stop_epoch = int(time.time())
    stop_human = now_human()
    return LocalRecordingResult(
        wav_path=wav_path,
        start_human=start_human,
        stop_human=stop_human,
        duration_seconds=max(0, stop_epoch - start_epoch),
    )


def record_timed(base_dir: Path, logger: Logger, seconds: int) -> LocalRecordingResult:
    if not command_exists("arecord"):
        raise RuntimeError("arecord not found (install alsa-utils).")
    if seconds <= 0:
        raise RuntimeError("Recording duration must be greater than 0 seconds.")

    wav_path = _record_target(base_dir)
    start_epoch = int(time.time())
    start_human = now_human()
    logger.line("Recording", f"Recording for {seconds}s...")
    process = subprocess.Popen(
        ["arecord", "-q", "-f", "S16_LE", "-r", "16000", "-c1", "-d", str(seconds), str(wav_path)],
    )
    try:
        process.wait()
    except KeyboardInterrupt as exc:
        try:
            process.terminate()
        except Exception:
            pass
        if wav_path.exists():
            wav_path.unlink(missing_ok=True)
        raise exc

    stop_epoch = int(time.time())
    stop_human = now_human()
    return LocalRecordingResult(
        wav_path=wav_path,
        start_human=start_human,
        stop_human=stop_human,
        duration_seconds=max(0, stop_epoch - start_epoch),
    )
