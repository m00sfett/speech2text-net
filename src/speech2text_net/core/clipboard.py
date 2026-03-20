from __future__ import annotations

import subprocess

from .shell import command_exists


def copy_text_to_clipboard(text: str) -> bool:
    payload = text.encode("utf-8")
    if command_exists("wl-copy"):
        process = subprocess.Popen(["wl-copy"], stdin=subprocess.PIPE)
        process.communicate(payload)
        return process.returncode == 0
    if command_exists("xclip"):
        process = subprocess.Popen(["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE)
        process.communicate(payload)
        return process.returncode == 0
    if command_exists("xsel"):
        process = subprocess.Popen(["xsel", "--clipboard", "--input"], stdin=subprocess.PIPE)
        process.communicate(payload)
        return process.returncode == 0
    return False
