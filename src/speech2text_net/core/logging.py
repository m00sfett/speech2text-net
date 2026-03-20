from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import TextIO


class Logger:
    ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")

    def __init__(
        self,
        *,
        log_file: Path,
        enable_color: bool = True,
        quiet: bool = False,
        tag: str = "S2T",
        stdout_is_tty: bool | None = None,
    ) -> None:
        self.log_file = log_file
        self.tag = tag
        self.quiet = quiet
        tty = sys.stdout.isatty() if stdout_is_tty is None else stdout_is_tty
        self.enable_color = bool(enable_color) and tty and os.environ.get("TERM", "") != "dumb"
        self._fh: TextIO | None = None
        self._open()

        self.c_reset = "\033[0m" if self.enable_color else ""
        self.c_bracket = "\033[38;5;196m" if self.enable_color else ""
        self.c_key = "\033[38;5;208m" if self.enable_color else ""
        self.c_text = "\033[37m" if self.enable_color else ""
        self.c_transcript = "\033[38;5;220m" if self.enable_color else ""
        self.c_title = "\033[38;5;202m" if self.enable_color else ""

    def _open(self) -> None:
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.log_file.open("w", encoding="utf-8", errors="replace")

    def close(self) -> None:
        if self._fh:
            self._fh.flush()
            self._fh.close()
            self._fh = None

    def _write(self, text: str, stream: TextIO | None = None) -> None:
        out_stream = stream or sys.stdout
        print(text, file=out_stream, flush=True)
        if self._fh:
            plain = self.ANSI_RE.sub("", text)
            self._fh.write(plain + "\n")
            self._fh.flush()

    def line(self, key: str, text: str, *, stderr: bool = False) -> None:
        if self.quiet:
            return
        out = (
            f"{self.c_bracket}[{self.tag}]{self.c_reset} "
            f"{self.c_key}{key}:{self.c_reset} "
            f"{self.c_text}{text}{self.c_reset}"
        )
        self._write(out, stream=sys.stderr if stderr else sys.stdout)

    def title_value(self, action: str, title: str) -> None:
        if self.quiet:
            return
        out = (
            f"{self.c_bracket}[{self.tag}]{self.c_reset} "
            f"{self.c_key}Title:{self.c_reset} "
            f"{self.c_text}{action}{self.c_reset} "
            f"{self.c_title}{title}{self.c_reset}"
        )
        self._write(out)

    def transcript_line(self, text: str) -> None:
        if self.quiet:
            return
        if self.enable_color:
            self._write(f"{self.c_transcript}{text}{self.c_reset}")
        else:
            self._write(text)

    def prompt_prefix(self, key: str, text: str) -> str:
        if self.quiet:
            return ""
        return (
            f"{self.c_bracket}[{self.tag}]{self.c_reset} "
            f"{self.c_key}{key}:{self.c_reset} "
            f"{self.c_text}{text}{self.c_reset} "
        )

    def warn(self, text: str) -> None:
        self.line("Warning", text, stderr=True)

    def error(self, text: str) -> None:
        self.line("Error", text, stderr=True)
