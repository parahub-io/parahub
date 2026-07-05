"""
Skystore transport: SSH command execution and rsync with retry/backoff.

Everything the processor does on skystore (Home PT, <SKYSTORE_IP> via WireGuard)
goes through these two helpers — see their docstrings for the retry semantics
(exit 255 = transport, retried; TimeoutExpired = never retried).
"""

import logging
import subprocess
import time

from .constants import SKYSTORE_SSH

logger = logging.getLogger(__name__)


def _skystore_ssh(cmd: str, timeout: int = 60, retries: int = 5) -> subprocess.CompletedProcess:
    """Run a command on skystore via SSH with retry on SSH connection failure (exit 255).

    Retry backoff 5/10/20/40s bridges the short WireGuard/CGNAT flaps observed
    2026-06-12 (sub-minute drops killed two runs at 3x5s). ServerAlive makes a
    LONG-lived ssh (docker wait holds one for hours) detect a dead peer in
    <=10min instead of hanging until its own timeout — a skystore power-loss
    left docker-wait hung on a dead TCP for 5h before this.

    NOTE: TimeoutExpired is NOT retried — local SSH timeout doesn't kill remote process,
    so retry would spawn duplicate concurrent runs. Caller must set adequate timeout.
    """
    for attempt in range(1, retries + 1):
        try:
            return subprocess.run(
                ["ssh", "-o", "ConnectTimeout=10",
                 "-o", "ServerAliveInterval=60", "-o", "ServerAliveCountMax=10",
                 SKYSTORE_SSH, cmd],
                timeout=timeout, check=True,
                capture_output=True, text=True,
            )
        except subprocess.TimeoutExpired:
            logger.error(
                f'Skystore SSH command timed out after {timeout}s. '
                f'Remote process may still be running — DO NOT retry to avoid duplicates.'
            )
            raise
        except subprocess.CalledProcessError as e:
            # Log stderr/stdout for debugging remote command failures
            if e.returncode != 255:
                if e.stderr:
                    logger.error(f'Skystore SSH command stderr (last 2000 chars): {e.stderr[-2000:]}')
                if e.stdout:
                    logger.info(f'Skystore SSH command stdout (last 1000 chars): {e.stdout[-1000:]}')
            # Only retry SSH connection failures (exit 255), not remote command errors
            if e.returncode == 255 and attempt < retries:
                backoff = 5 * (2 ** (attempt - 1))  # 5, 10, 20, 40s
                logger.warning(
                    f'Skystore SSH attempt {attempt}/{retries} connection failed, retrying in {backoff}s...')
                time.sleep(backoff)
            else:
                if e.returncode == 255 and e.stderr:
                    # 255 is also AUTH failure, not just transport — surface it
                    # (a root-without-key unit burned 3 runs looking like "flaps")
                    logger.error(f'Skystore SSH final failure stderr: {e.stderr[-500:]}')
                raise



def _skystore_rsync(src: str, dst: str, timeout: int = 600, delete: bool = False, retries: int = 3):
    """Rsync local path to skystore with retry on connection failure."""
    cmd = ["rsync", "-a"]
    if delete:
        cmd.append("--delete")
    cmd.extend([src, f"{SKYSTORE_SSH}:{dst}"])
    for attempt in range(1, retries + 1):
        try:
            subprocess.run(cmd, timeout=timeout, check=True, capture_output=True, text=True)
            return
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            if attempt < retries:
                logger.warning(f'Skystore rsync attempt {attempt}/{retries} failed: {e}, retrying in 5s...')
                time.sleep(5)
            else:
                raise
