from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


APP_NAME = "speech2text-net"


def detect_project_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file():
            return parent.resolve(strict=False)
    if len(here.parents) > 2:
        return here.parents[2].resolve(strict=False)
    return here.parent.resolve(strict=False)


PROJECT_ROOT = detect_project_root()
DEFAULT_CONFIG_NAME = "speech2text-net.conf"
ENV_PREFIX = "S2TNET_"


@dataclass(slots=True)
class AppConfig:
    project_root: Path
    config_file: Path
    config_found: bool

    model: str
    language: str
    device: str
    fp16: bool

    output_dir: Path
    model_dir: Path
    log_file: Path
    client_log_file: Path | None
    server_log_file: Path | None

    title_model: str
    title_maxlen: int
    auto_title: bool

    enable_media_mute: bool
    mute_only: bool
    enable_color: bool
    quiet: bool
    enable_clipboard: bool
    autodetect_local_server: bool
    record_backend: str
    record_device: str

    server_host: str
    server_port: int
    server_url: str
    api_token: str
    api_token_file: Path
    api_token_source: str

    clean_mode: str
    gpu_cleanup_path: Path


def parse_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def parse_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def resolve_path(value: str | Path, *, base_dir: Path) -> Path:
    expanded = Path(os.path.expandvars(os.path.expanduser(str(value).strip())))
    if not expanded.is_absolute():
        expanded = base_dir / expanded
    return expanded.resolve(strict=False)


def default_user_config_dir(env: Mapping[str, str] | None = None) -> Path:
    env_map = env or os.environ
    cwd = Path.cwd().resolve(strict=False)
    xdg_config_home = str(env_map.get("XDG_CONFIG_HOME", "")).strip()
    if xdg_config_home:
        base = resolve_path(xdg_config_home, base_dir=cwd)
    else:
        home = str(env_map.get("HOME", str(Path.home()))).strip() or str(Path.home())
        base = resolve_path(Path(home) / ".config", base_dir=cwd)
    return (base / APP_NAME).resolve(strict=False)


def is_source_checkout(project_root: Path) -> bool:
    return (project_root / "pyproject.toml").is_file() and (project_root / "src" / "speech2text_net").is_dir()


def discover_default_config_path(
    *,
    project_root: Path,
    env: Mapping[str, str] | None = None,
    cwd: Path | None = None,
) -> Path:
    env_map = env or os.environ
    current_dir = (cwd or Path.cwd()).resolve(strict=False)
    env_config = str(env_map.get(f"{ENV_PREFIX}CONFIG", "")).strip()
    if env_config:
        return resolve_path(env_config, base_dir=current_dir)

    cwd_candidate = current_dir / DEFAULT_CONFIG_NAME
    repo_candidate = project_root / DEFAULT_CONFIG_NAME
    user_candidate = default_user_config_dir(env_map) / DEFAULT_CONFIG_NAME

    if is_source_checkout(project_root):
        candidates = (cwd_candidate, repo_candidate, user_candidate)
    else:
        candidates = (user_candidate, cwd_candidate)

    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve(strict=False)

    if is_source_checkout(project_root):
        return repo_candidate.resolve(strict=False)
    return user_candidate.resolve(strict=False)


def load_config_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}

    allowed = {
        "MODEL",
        "LANGUAGE",
        "DEVICE",
        "FP16",
        "OUT_DIR",
        "MODEL_DIR",
        "LOG_FILE",
        "CLIENT_LOG_FILE",
        "SERVER_LOG_FILE",
        "TITLE_MODEL",
        "TITLE_MAXLEN",
        "AUTO_TITLE",
        "ENABLE_MEDIA_MUTE",
        "MUTE_ONLY",
        "ENABLE_COLOR",
        "QUIET",
        "ENABLE_CLIPBOARD",
        "AUTO_DETECT_LOCAL_SERVER",
        "RECORD_BACKEND",
        "RECORD_DEVICE",
        "SERVER_HOST",
        "SERVER_PORT",
        "SERVER_URL",
        "API_TOKEN",
        "API_TOKEN_FILE",
        "CLEAN_MODE",
        "GPU_CLEANUP_PATH",
    }

    data: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key in allowed:
            data[key] = value
    return data


def read_token_file(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def is_loopback_host(host: str) -> bool:
    return host.strip().lower() in {"127.0.0.1", "localhost", "::1"}


def cli_overrides_from_namespace(args: Any) -> dict[str, Any]:
    overrides: dict[str, Any] = {}

    mapping = {
        "model": "MODEL",
        "language": "LANGUAGE",
        "device": "DEVICE",
        "fp16": "FP16",
        "out_dir": "OUT_DIR",
        "model_dir": "MODEL_DIR",
        "log_file": "LOG_FILE",
        "client_log_file": "CLIENT_LOG_FILE",
        "server_log_file": "SERVER_LOG_FILE",
        "title_model": "TITLE_MODEL",
        "title_maxlen": "TITLE_MAXLEN",
        "record_backend": "RECORD_BACKEND",
        "record_device": "RECORD_DEVICE",
        "server_host": "SERVER_HOST",
        "server_port": "SERVER_PORT",
        "server_url": "SERVER_URL",
        "token": "API_TOKEN",
        "token_file": "API_TOKEN_FILE",
    }
    for attr, key in mapping.items():
        value = getattr(args, attr, None)
        if value not in (None, ""):
            overrides[key] = value

    if getattr(args, "color", False):
        overrides["ENABLE_COLOR"] = "1"
    if getattr(args, "no_color", False):
        overrides["ENABLE_COLOR"] = "0"
    if getattr(args, "nomute", False):
        overrides["ENABLE_MEDIA_MUTE"] = "0"
        overrides["MUTE_ONLY"] = "0"
    if getattr(args, "mute_only", False):
        overrides["ENABLE_MEDIA_MUTE"] = "1"
        overrides["MUTE_ONLY"] = "1"
    if getattr(args, "clipboard", False):
        overrides["ENABLE_CLIPBOARD"] = "1"
    if getattr(args, "no_clipboard", False):
        overrides["ENABLE_CLIPBOARD"] = "0"
    if getattr(args, "autodetect_local", False):
        overrides["AUTO_DETECT_LOCAL_SERVER"] = "1"
    if getattr(args, "no_autodetect_local", False):
        overrides["AUTO_DETECT_LOCAL_SERVER"] = "0"
    if getattr(args, "quiet", False):
        overrides["QUIET"] = "1"

    return overrides


def build_config(
    *,
    cli_overrides: Mapping[str, Any] | None = None,
    config_path: Path | None = None,
    env: Mapping[str, str] | None = None,
    project_root: Path | None = None,
    cwd: Path | None = None,
) -> AppConfig:
    env_map = env or os.environ
    root = (project_root or PROJECT_ROOT).resolve(strict=False)
    current_dir = (cwd or Path.cwd()).resolve(strict=False)

    if config_path is not None:
        resolved_config_path = resolve_path(config_path, base_dir=current_dir)
    else:
        resolved_config_path = discover_default_config_path(
            project_root=root,
            env=env_map,
            cwd=current_dir,
        )
    cfg_data = load_config_file(resolved_config_path)
    config_base_dir = resolved_config_path.parent
    cli_data = dict(cli_overrides or {})

    defaults: dict[str, Any] = {
        "MODEL": "turbo",
        "LANGUAGE": "German",
        "DEVICE": "cuda",
        "FP16": "1",
        "OUT_DIR": "output",
        "MODEL_DIR": "models",
        "LOG_FILE": "speech2text-net.log",
        "CLIENT_LOG_FILE": "",
        "SERVER_LOG_FILE": "",
        "TITLE_MODEL": "",
        "TITLE_MAXLEN": "40",
        "AUTO_TITLE": "1",
        "ENABLE_MEDIA_MUTE": "1",
        "MUTE_ONLY": "0",
        "ENABLE_COLOR": "1",
        "QUIET": "0",
        "ENABLE_CLIPBOARD": "1",
        "AUTO_DETECT_LOCAL_SERVER": "1",
        "RECORD_BACKEND": "auto",
        "RECORD_DEVICE": "",
        "SERVER_HOST": "127.0.0.1",
        "SERVER_PORT": "8765",
        "SERVER_URL": "http://127.0.0.1:8765",
        "API_TOKEN": "",
        "API_TOKEN_FILE": ".secrets/speech2text-net.token",
        "CLEAN_MODE": "",
        "GPU_CLEANUP_PATH": "gpu-cleanup.sh",
    }

    def pick(key: str) -> Any:
        env_key = f"{ENV_PREFIX}{key}"
        if key in cli_data:
            return cli_data[key]
        if key in cfg_data:
            return cfg_data[key]
        if env_key in env_map:
            return env_map[env_key]
        return defaults[key]

    resolved_token_file = resolve_path(str(pick("API_TOKEN_FILE")), base_dir=config_base_dir)
    direct_token = str(pick("API_TOKEN")).strip()
    token_source = "none"
    effective_token = direct_token
    if effective_token:
        token_source = "value"
    else:
        file_token = read_token_file(resolved_token_file)
        if file_token:
            effective_token = file_token
            token_source = "file"

    client_log_file_raw = str(pick("CLIENT_LOG_FILE")).strip()
    server_log_file_raw = str(pick("SERVER_LOG_FILE")).strip()

    return AppConfig(
        project_root=root,
        config_file=resolved_config_path,
        config_found=resolved_config_path.is_file(),
        model=str(pick("MODEL")),
        language=str(pick("LANGUAGE")),
        device=str(pick("DEVICE")),
        fp16=parse_bool(pick("FP16"), True),
        output_dir=resolve_path(str(pick("OUT_DIR")), base_dir=config_base_dir),
        model_dir=resolve_path(str(pick("MODEL_DIR")), base_dir=config_base_dir),
        log_file=resolve_path(str(pick("LOG_FILE")), base_dir=config_base_dir),
        client_log_file=resolve_path(client_log_file_raw, base_dir=config_base_dir) if client_log_file_raw else None,
        server_log_file=resolve_path(server_log_file_raw, base_dir=config_base_dir) if server_log_file_raw else None,
        title_model=str(pick("TITLE_MODEL")),
        title_maxlen=parse_int(pick("TITLE_MAXLEN"), 40),
        auto_title=parse_bool(pick("AUTO_TITLE"), True),
        enable_media_mute=parse_bool(pick("ENABLE_MEDIA_MUTE"), True),
        mute_only=parse_bool(pick("MUTE_ONLY"), False),
        enable_color=parse_bool(pick("ENABLE_COLOR"), True),
        quiet=parse_bool(pick("QUIET"), False),
        enable_clipboard=parse_bool(pick("ENABLE_CLIPBOARD"), True),
        autodetect_local_server=parse_bool(pick("AUTO_DETECT_LOCAL_SERVER"), True),
        record_backend=str(pick("RECORD_BACKEND")).strip().lower() or "auto",
        record_device=str(pick("RECORD_DEVICE")).strip(),
        server_host=str(pick("SERVER_HOST")),
        server_port=parse_int(pick("SERVER_PORT"), 8765),
        server_url=str(pick("SERVER_URL")),
        api_token=effective_token,
        api_token_file=resolved_token_file,
        api_token_source=token_source,
        clean_mode=str(pick("CLEAN_MODE")).strip().lower(),
        gpu_cleanup_path=resolve_path(str(pick("GPU_CLEANUP_PATH")), base_dir=config_base_dir),
    )
