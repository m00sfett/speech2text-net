from __future__ import annotations

import unittest
from pathlib import Path

from speech2text_net.core.config import build_config
from speech2text_net.server.auth import is_request_authorized, validate_server_security


class ServerAuthTests(unittest.TestCase):
    def test_non_local_without_token_is_rejected(self) -> None:
        cfg = build_config(
            cli_overrides={"SERVER_HOST": "100.100.100.100", "SERVER_PORT": 8765},
            project_root=Path("/tmp/s2t-test"),
        )
        with self.assertRaises(ValueError):
            validate_server_security(cfg)

    def test_local_without_token_is_allowed(self) -> None:
        cfg = build_config(
            cli_overrides={"SERVER_HOST": "127.0.0.1", "SERVER_PORT": 8765},
            project_root=Path("/tmp/s2t-test"),
        )
        validate_server_security(cfg)

    def test_bearer_token_check(self) -> None:
        cfg = build_config(
            cli_overrides={"SERVER_HOST": "100.100.100.100", "API_TOKEN": "abc123"},
            project_root=Path("/tmp/s2t-test"),
        )
        validate_server_security(cfg)
        self.assertFalse(is_request_authorized({}, cfg))
        self.assertFalse(is_request_authorized({"Authorization": "Bearer wrong"}, cfg))
        self.assertTrue(is_request_authorized({"Authorization": "Bearer abc123"}, cfg))


if __name__ == "__main__":
    unittest.main()
