from __future__ import annotations

import re
import time
from datetime import datetime


def now_human() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")


def format_hms(total: int) -> str:
    hours = total // 3600
    minutes = (total % 3600) // 60
    seconds = total % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def timestamp_slug() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def slugify_title(text: str, max_len: int) -> str:
    value = text.replace("\r", "").replace("\n", " ")
    value = value.replace('"', "").replace("'", "")
    replacements = {
        "ä": "a",
        "ö": "o",
        "ü": "u",
        "Ä": "a",
        "Ö": "o",
        "Ü": "u",
        "ß": "ss",
    }
    for source, target in replacements.items():
        value = value.replace(source, target)
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"^-+|-+$", "", value)
    value = re.sub(r"-{2,}", "-", value)
    if not value:
        value = "untitled"
    return value[:max_len]
