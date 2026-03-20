from __future__ import annotations

import signal
import subprocess
import struct
import time
import wave
from dataclasses import dataclass
from pathlib import Path

from .config import AppConfig
from .logging import Logger
from .shell import command_exists, run_capture
from .utils import now_human, timestamp_slug


@dataclass(slots=True)
class LocalRecordingResult:
    wav_path: Path
    start_human: str
    stop_human: str
    duration_seconds: int
    backend_used: str
    device_used: str


def _recordings_dir(base_dir: Path) -> Path:
    path = base_dir / "client-recordings"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _record_target(base_dir: Path) -> Path:
    return _recordings_dir(base_dir) / f"{timestamp_slug()}.wav"


def _pulse_recording_available() -> bool:
    if not command_exists("pactl"):
        return False
    rc, out, _ = run_capture(["pactl", "info"], timeout=2)
    return rc == 0 and "Server Name:" in out


def _choose_recording_backend(config: AppConfig) -> str:
    requested = config.record_backend.strip().lower() or "auto"
    valid = {"auto", "parecord", "pw-record", "arecord"}
    if requested not in valid:
        raise RuntimeError(f"Unsupported recording backend: {requested}")

    if requested != "auto":
        if not command_exists(requested):
            raise RuntimeError(f"Requested recording backend not found: {requested}")
        return requested

    if command_exists("parecord") and _pulse_recording_available():
        return "parecord"
    if command_exists("pw-record"):
        return "pw-record"
    if command_exists("arecord"):
        return "arecord"
    raise RuntimeError("No supported recording backend found (parecord, pw-record, or arecord).")


def _build_record_command(config: AppConfig, wav_path: Path, backend: str) -> tuple[list[str], str]:
    device = config.record_device.strip()
    if backend == "parecord":
        device_label = device or "@DEFAULT_SOURCE@"
        return (
            [
                "parecord",
                f"--device={device_label}",
                "--rate=16000",
                "--channels=1",
                "--format=s16le",
                "--file-format=wav",
                str(wav_path),
            ],
            device_label,
        )
    if backend == "pw-record":
        cmd = ["pw-record", "--rate", "16000", "--channels", "1", "--format", "s16"]
        if device:
            cmd.extend(["--target", device])
        cmd.append(str(wav_path))
        return cmd, device or "auto"
    if backend == "arecord":
        cmd = ["arecord", "-q", "-f", "S16_LE", "-r", "16000", "-c1"]
        if device:
            cmd.extend(["-D", device])
        cmd.append(str(wav_path))
        return cmd, device or "default"
    raise RuntimeError(f"Unsupported recording backend: {backend}")


def _analyze_wav(path: Path) -> tuple[float, int, int]:
    with wave.open(str(path), "rb") as wav_file:
        frame_count = wav_file.getnframes()
        sample_rate = wav_file.getframerate()
        sample_width = wav_file.getsampwidth()
        channels = wav_file.getnchannels()
        raw = wav_file.readframes(frame_count)

    if frame_count <= 0 or sample_rate <= 0:
        return 0.0, 0, 0
    if sample_width != 2:
        return frame_count / sample_rate, -1, -1

    total = 0
    total_sq = 0
    max_amp = 0
    for (sample,) in struct.iter_unpack("<h", raw):
        amp = abs(sample)
        if amp > max_amp:
            max_amp = amp
        total_sq += sample * sample
        total += 1

    rms = int((total_sq / total) ** 0.5) if total else 0
    duration = frame_count / sample_rate
    if channels > 1:
        return duration, rms, max_amp
    return duration, rms, max_amp


def _ensure_recording_has_signal(wav_path: Path, logger: Logger, *, backend: str, device: str) -> None:
    duration, rms, max_amp = _analyze_wav(wav_path)
    logger.line("Recording", f"Signal check: duration={duration:.2f}s rms={rms} max={max_amp}")
    if max_amp == 0:
        raise RuntimeError(
            f"Recording appears silent. Backend={backend}, device={device}. "
            "Please select a working input source or backend."
        )


def _stop_recording_process(process: subprocess.Popen[str]) -> None:
    try:
        process.send_signal(signal.SIGINT)
    except Exception:
        pass
    try:
        process.wait(timeout=2)
        return
    except Exception:
        pass
    try:
        process.terminate()
    except Exception:
        pass
    process.wait(timeout=2)


def record_interactive(config: AppConfig, logger: Logger) -> LocalRecordingResult:
    backend = _choose_recording_backend(config)
    wav_path = _record_target(config.output_dir)
    cmd, device_used = _build_record_command(config, wav_path, backend)

    start_epoch = int(time.time())
    start_human = now_human()

    process = subprocess.Popen(cmd)
    logger.line("Recording", f"Recording started via {backend} ({device_used}).")
    try:
        input(logger.prompt_prefix("Input", "Press Enter to stop recording:"))
    except KeyboardInterrupt as exc:
        _stop_recording_process(process)
        if wav_path.exists():
            wav_path.unlink(missing_ok=True)
        raise exc

    _stop_recording_process(process)
    if process.returncode not in (0, None, -2):
        raise RuntimeError(f"Recording backend failed with exit code {process.returncode}.")
    if not wav_path.exists():
        raise RuntimeError("Recording finished without creating a WAV file.")
    _ensure_recording_has_signal(wav_path, logger, backend=backend, device=device_used)

    stop_epoch = int(time.time())
    stop_human = now_human()
    return LocalRecordingResult(
        wav_path=wav_path,
        start_human=start_human,
        stop_human=stop_human,
        duration_seconds=max(0, stop_epoch - start_epoch),
        backend_used=backend,
        device_used=device_used,
    )


def record_timed(config: AppConfig, logger: Logger, seconds: int) -> LocalRecordingResult:
    if seconds <= 0:
        raise RuntimeError("Recording duration must be greater than 0 seconds.")

    backend = _choose_recording_backend(config)
    wav_path = _record_target(config.output_dir)
    cmd, device_used = _build_record_command(config, wav_path, backend)
    start_epoch = int(time.time())
    start_human = now_human()
    logger.line("Recording", f"Recording for {seconds}s via {backend} ({device_used})...")
    process = subprocess.Popen(cmd)
    try:
        process.wait(timeout=seconds)
    except subprocess.TimeoutExpired:
        _stop_recording_process(process)
    except KeyboardInterrupt as exc:
        try:
            process.terminate()
        except Exception:
            pass
        if wav_path.exists():
            wav_path.unlink(missing_ok=True)
        raise exc
    if process.returncode not in (0, None, -2):
        raise RuntimeError(f"Recording backend failed with exit code {process.returncode}.")
    if not wav_path.exists():
        raise RuntimeError("Recording finished without creating a WAV file.")
    _ensure_recording_has_signal(wav_path, logger, backend=backend, device=device_used)

    stop_epoch = int(time.time())
    stop_human = now_human()
    return LocalRecordingResult(
        wav_path=wav_path,
        start_human=start_human,
        stop_human=stop_human,
        duration_seconds=max(0, stop_epoch - start_epoch),
        backend_used=backend,
        device_used=device_used,
    )
