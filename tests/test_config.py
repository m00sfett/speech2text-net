from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from speech2text_net.core.config import build_config, discover_default_config_path


class ConfigTests(unittest.TestCase):
    def test_precedence_cli_over_config_over_env(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config_path = root / "speech2text-net.conf"
            config_path.write_text(
                "\n".join(
                    [
                        "MODEL=base",
                        "DEVICE=cpu",
                        "OUT_DIR=config-output",
                        "SERVER_PORT=9999",
                    ]
                ),
                encoding="utf-8",
            )
            env = {
                "S2TNET_MODEL": "tiny",
                "S2TNET_DEVICE": "cuda",
                "S2TNET_OUT_DIR": "env-output",
                "S2TNET_SERVER_PORT": "8888",
            }

            cfg = build_config(
                cli_overrides={"MODEL": "turbo", "SERVER_PORT": 7777},
                config_path=config_path,
                env=env,
                project_root=root,
            )

            self.assertEqual(cfg.model, "turbo")
            self.assertEqual(cfg.device, "cpu")
            self.assertEqual(cfg.output_dir, (root / "config-output").resolve())
            self.assertEqual(cfg.server_port, 7777)

    def test_token_file_is_used_when_value_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            token_file = root / ".secrets" / "speech2text-net.token"
            token_file.parent.mkdir(parents=True, exist_ok=True)
            token_file.write_text("secret-token\n", encoding="utf-8")
            config_path = root / "speech2text-net.conf"
            config_path.write_text(f"API_TOKEN_FILE={token_file}\n", encoding="utf-8")

            cfg = build_config(config_path=config_path, project_root=root)

            self.assertEqual(cfg.api_token, "secret-token")
            self.assertEqual(cfg.api_token_source, "file")

    def test_explicit_relative_config_path_uses_current_working_directory(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workdir = root / "work"
            repo = root / "repo"
            workdir.mkdir()
            repo.mkdir()
            config_path = workdir / "custom.conf"
            config_path.write_text("SERVER_PORT=4321\n", encoding="utf-8")

            cfg = build_config(
                config_path=Path("custom.conf"),
                project_root=repo,
                cwd=workdir,
            )

            self.assertEqual(cfg.config_file, config_path.resolve())
            self.assertEqual(cfg.server_port, 4321)

    def test_default_config_falls_back_to_xdg_config_dir_outside_repo_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            home = root / "home"
            home.mkdir()
            project_root = root / "installed"
            project_root.mkdir()
            xdg_config_home = home / ".config"
            user_config_dir = xdg_config_home / "speech2text-net"
            user_config_dir.mkdir(parents=True)
            config_path = user_config_dir / "speech2text-net.conf"
            config_path.write_text("DEVICE=cpu\n", encoding="utf-8")

            env = {"HOME": str(home)}
            discovered = discover_default_config_path(
                project_root=project_root,
                env=env,
                cwd=root,
            )
            cfg = build_config(project_root=project_root, env=env, cwd=root)

            self.assertEqual(discovered, config_path.resolve())
            self.assertEqual(cfg.config_file, config_path.resolve())
            self.assertEqual(cfg.device, "cpu")

    def test_installed_mode_prefers_user_config_over_cwd_config(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            home = root / "home"
            cwd = root / "work"
            project_root = root / "site-packages"
            home.mkdir()
            cwd.mkdir()
            project_root.mkdir()

            cwd_config = cwd / "speech2text-net.conf"
            cwd_config.write_text("DEVICE=cpu\n", encoding="utf-8")

            user_config_dir = home / ".config" / "speech2text-net"
            user_config_dir.mkdir(parents=True)
            user_config = user_config_dir / "speech2text-net.conf"
            user_config.write_text("DEVICE=cuda\n", encoding="utf-8")

            env = {"HOME": str(home)}
            cfg = build_config(project_root=project_root, env=env, cwd=cwd)

            self.assertEqual(cfg.config_file, user_config.resolve())
            self.assertEqual(cfg.device, "cuda")

    def test_checkout_mode_prefers_cwd_config(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            project_root = root / "repo"
            cwd = project_root / "nested"
            home = root / "home"
            (project_root / "src" / "speech2text_net").mkdir(parents=True)
            (project_root / "pyproject.toml").write_text("[project]\nname='speech2text-net'\n", encoding="utf-8")
            cwd.mkdir(parents=True)
            home.mkdir()

            cwd_config = cwd / "speech2text-net.conf"
            cwd_config.write_text("DEVICE=cpu\n", encoding="utf-8")

            user_config_dir = home / ".config" / "speech2text-net"
            user_config_dir.mkdir(parents=True)
            user_config = user_config_dir / "speech2text-net.conf"
            user_config.write_text("DEVICE=cuda\n", encoding="utf-8")

            env = {"HOME": str(home)}
            cfg = build_config(project_root=project_root, env=env, cwd=cwd)

            self.assertEqual(cfg.config_file, cwd_config.resolve())
            self.assertEqual(cfg.device, "cpu")


if __name__ == "__main__":
    unittest.main()
