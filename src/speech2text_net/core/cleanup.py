from __future__ import annotations

import os
import subprocess

from .config import AppConfig
from .logging import Logger
from .shell import run_capture


def run_gpu_cleanup_if_requested(config: AppConfig, logger: Logger, *, phase: str, requested_device: str) -> None:
    if not config.clean_mode:
        return
    if requested_device != "cuda":
        logger.warn("GPU cleanup requested but device is not cuda; skipping cleanup.")
        return

    cleanup = config.gpu_cleanup_path
    if not cleanup.exists():
        logger.warn(f"GPU cleanup script not found: {cleanup}")
        return
    if not os.access(cleanup, os.X_OK):
        logger.warn(f"GPU cleanup script is not executable: {cleanup}")
        return

    if config.clean_mode == "safe":
        logger.line("GPU", f"Running gpu-cleanup.sh --safe ({phase})...")
        rc, out, err = run_capture([str(cleanup), "--safe"])
        combined = (out or "") + (err or "")
        for line in combined.splitlines():
            if line.startswith("SUMMARY:"):
                logger.line("GPU", line)
        if rc != 0:
            logger.warn("gpu-cleanup.sh --safe failed; continuing.")
        return

    if config.clean_mode == "force":
        logger.line("GPU", f"Running gpu-cleanup.sh --force ({phase})...")
        rc = subprocess.call([str(cleanup), "--force"])
        if rc != 0:
            logger.warn("gpu-cleanup.sh --force failed; continuing.")
