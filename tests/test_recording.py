from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from speech2text_net.core.config import build_config
from speech2text_net.core.recording import _choose_recording_backend


class RecordingTests(unittest.TestCase):
    def test_auto_prefers_parecord_when_pulse_is_available(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg = build_config(project_root=root, cwd=root)
            with patch("speech2text_net.core.recording.command_exists") as exists_mock:
                with patch("speech2text_net.core.recording._pulse_recording_available", return_value=True):
                    exists_mock.side_effect = lambda cmd: cmd in {"parecord", "pw-record", "arecord", "pactl"}
                    backend = _choose_recording_backend(cfg)
            self.assertEqual(backend, "parecord")

    def test_auto_falls_back_to_arecord(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg = build_config(project_root=root, cwd=root)
            with patch("speech2text_net.core.recording.command_exists") as exists_mock:
                with patch("speech2text_net.core.recording._pulse_recording_available", return_value=False):
                    exists_mock.side_effect = lambda cmd: cmd == "arecord"
                    backend = _choose_recording_backend(cfg)
            self.assertEqual(backend, "arecord")

    def test_explicit_backend_must_exist(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg = build_config(
                project_root=root,
                cwd=root,
                cli_overrides={"RECORD_BACKEND": "parecord"},
            )
            with patch("speech2text_net.core.recording.command_exists", return_value=False):
                with self.assertRaises(RuntimeError):
                    _choose_recording_backend(cfg)


if __name__ == "__main__":
    unittest.main()
