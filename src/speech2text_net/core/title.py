from __future__ import annotations

import re
import shlex
from pathlib import Path

from .config import AppConfig
from .shell import command_exists, run_capture
from .utils import slugify_title


def pick_default_title_model() -> str:
    if not command_exists("ollama"):
        return ""
    rc, out, _ = run_capture(["bash", "-lc", "timeout 3s ollama list 2>/dev/null || ollama list 2>/dev/null"])
    if rc != 0 or not out.strip():
        return ""
    models: list[str] = []
    for index, line in enumerate(out.splitlines()):
        if index == 0:
            continue
        cols = line.split()
        if cols:
            models.append(cols[0])
    if not models:
        return ""
    patterns = [
        r"(qwen2\.5|qwen2|qwen):.*instruct",
        r"(llama3\.2|llama3\.1|llama3):.*instruct",
        r"(mistral|mixtral).*instruct",
        r"(phi3|phi4).*",
    ]
    for pattern in patterns:
        for model in models:
            if re.search(pattern, model):
                return model
    return models[0]


def ollama_reachable() -> bool:
    if not command_exists("ollama"):
        return False
    rc, _, _ = run_capture(["bash", "-lc", "timeout 2s ollama list >/dev/null 2>&1 || ollama list >/dev/null 2>&1"])
    return rc == 0


def generate_title_from_transcript(config: AppConfig, transcript_path: Path, *, chosen_model: str) -> str:
    text = transcript_path.read_text(encoding="utf-8", errors="replace").replace("\n", " ")[:3000]
    prompt = (
        "You generate short filename suffixes.\n"
        "Return ONLY the title, single line, no quotes, no punctuation.\n"
        "Requirements:\n"
        "- German, very short (2-6 words)\n"
        "- ASCII only (no umlauts), lowercase\n"
        "- No file extension\n"
        "- Use spaces or hyphens only\n\n"
        f"Transcript:\n{text}\n"
    )
    cmd = [
        "bash",
        "-lc",
        f"timeout 20s ollama run {shlex.quote(chosen_model)} {shlex.quote(prompt)} 2>/dev/null || true",
    ]
    rc, out, _ = run_capture(cmd)
    if rc != 0 and not out:
        return ""
    raw = out.splitlines()[0] if out.splitlines() else ""
    return slugify_title(raw, config.title_maxlen)
