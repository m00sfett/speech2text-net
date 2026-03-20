from __future__ import annotations

import argparse
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from speech2text_net.client.cli import _interactive_change_loop, run_client
from speech2text_net.core.config import build_config
from speech2text_net.core.logging import Logger
from speech2text_net.core.recording import LocalRecordingResult


class ClientSmokeTests(unittest.TestCase):
    def test_existing_wav_flow(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            wav = root / "input.wav"
            wav.write_bytes(b"RIFF1234WAVEfmt ")
            cfg = build_config(
                cli_overrides={"ENABLE_CLIPBOARD": "0", "OUT_DIR": str(root / "out")},
                project_root=root,
            )
            logger = Logger(log_file=root / "client.log", enable_color=False, quiet=False, tag="TEST", stdout_is_tty=False)
            try:
                with patch("speech2text_net.client.cli.resolve_server_url", return_value=("http://127.0.0.1:9999", {"status": "ok", "auth_mode": "local-no-token", "version": "0.7.0"})):
                    with patch(
                        "speech2text_net.client.cli.upload_wav",
                        return_value={
                            "transcript": "Mock transcript.",
                            "title": "",
                            "artifacts": {"audio_path": "/srv/audio.wav", "text_path": "/srv/audio.txt"},
                            "timings": {
                                "transcribe_start": "t1",
                                "transcribe_stop": "t2",
                                "transcribe_duration_hms": "00:00:04",
                                "transcribe_duration_seconds": 4,
                            },
                        },
                    ):
                        rc = run_client(argparse.Namespace(input_wav=str(wav), seconds=None), cfg, logger)
                self.assertEqual(rc, 0)
            finally:
                logger.close()

    def test_local_recording_flow_summary(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            wav = root / "recorded.wav"
            wav.write_bytes(b"RIFF1234WAVEfmt ")
            cfg = build_config(
                cli_overrides={"ENABLE_CLIPBOARD": "0", "OUT_DIR": str(root / "out")},
                project_root=root,
            )
            logger = Logger(log_file=root / "client.log", enable_color=False, quiet=False, tag="TEST", stdout_is_tty=False)
            recording = LocalRecordingResult(
                wav_path=wav,
                start_human="start",
                stop_human="stop",
                duration_seconds=3,
                backend_used="parecord",
                device_used="@DEFAULT_SOURCE@",
            )
            try:
                with patch("speech2text_net.client.cli.record_timed", return_value=recording):
                    with patch("speech2text_net.client.cli.pause_media_playback", return_value={"mock": True}):
                        with patch("speech2text_net.client.cli.resume_media_playback"):
                            with patch("speech2text_net.client.cli.resolve_server_url", return_value=("http://127.0.0.1:9999", {"status": "ok", "auth_mode": "local-no-token"})):
                                with patch(
                                    "speech2text_net.client.cli.upload_wav",
                                    return_value={
                                        "transcript": "Mock transcript.",
                                        "title": "",
                                        "artifacts": {"audio_path": "/srv/audio.wav", "text_path": "/srv/audio.txt"},
                                        "timings": {
                                            "transcribe_start": "t1",
                                            "transcribe_stop": "t2",
                                            "transcribe_duration_hms": "00:00:04",
                                            "transcribe_duration_seconds": 4,
                                        },
                                    },
                                ):
                                    rc = run_client(argparse.Namespace(input_wav=None, seconds=3), cfg, logger)
                self.assertEqual(rc, 0)
            finally:
                logger.close()

    def test_interactive_regenerate_title_flow(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg = build_config(project_root=root)
            logger = Logger(log_file=root / "client.log", enable_color=False, quiet=False, tag="TEST", stdout_is_tty=False)
            response = {
                "transcript": "Mock transcript.",
                "title": "old-title",
                "artifacts": {"audio_path": "/srv/audio-old-title.wav", "text_path": "/srv/audio-old-title.txt"},
                "timings": {"transcribe_duration_seconds": 4, "transcribe_duration_hms": "00:00:04"},
            }
            try:
                with patch("speech2text_net.client.cli.sys.stdin.isatty", return_value=True):
                    with patch("builtins.input", side_effect=["1", "0"]):
                        with patch(
                            "speech2text_net.client.cli.update_title",
                            return_value={
                                "title": "new-title",
                                "artifacts": {"audio_path": "/srv/audio-new-title.wav", "text_path": "/srv/audio-new-title.txt"},
                            },
                        ):
                            out = _interactive_change_loop(
                                cfg,
                                logger,
                                server_url="http://127.0.0.1:9999",
                                local_recording=None,
                                response=response,
                            )
                self.assertEqual(out["title"], "new-title")
                self.assertEqual(out["artifacts"]["audio_path"], "/srv/audio-new-title.wav")
            finally:
                logger.close()

    def test_interactive_regenerate_transcript_flow(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg = build_config(project_root=root)
            logger = Logger(log_file=root / "client.log", enable_color=False, quiet=False, tag="TEST", stdout_is_tty=False)
            response = {
                "transcript": "Old transcript.",
                "title": "kept-title",
                "artifacts": {"audio_path": "/srv/audio-kept-title.wav", "text_path": "/srv/audio-kept-title.txt"},
                "timings": {"transcribe_duration_seconds": 4, "transcribe_duration_hms": "00:00:04"},
            }
            new_response = {
                "transcript": "New transcript.",
                "title": "kept-title",
                "artifacts": {"audio_path": "/srv/audio-kept-title.wav", "text_path": "/srv/audio-kept-title.txt"},
                "timings": {
                    "transcribe_start": "t1",
                    "transcribe_stop": "t2",
                    "transcribe_duration_seconds": 5,
                    "transcribe_duration_hms": "00:00:05",
                },
            }
            try:
                with patch("speech2text_net.client.cli.sys.stdin.isatty", return_value=True):
                    with patch("builtins.input", side_effect=["2", "0"]):
                        with patch("speech2text_net.client.cli.regenerate_transcript", return_value=new_response):
                            with patch("speech2text_net.client.cli._display_response") as display_mock:
                                with patch("speech2text_net.client.cli._copy_transcript_if_enabled") as copy_mock:
                                    out = _interactive_change_loop(
                                        cfg,
                                        logger,
                                        server_url="http://127.0.0.1:9999",
                                        local_recording=None,
                                        response=response,
                                    )
                self.assertEqual(out["transcript"], "New transcript.")
                display_mock.assert_called_once()
                copy_mock.assert_called_once()
            finally:
                logger.close()


if __name__ == "__main__":
    unittest.main()
