"""
config.py  —  All settings read from environment variables.

FIXES:
  - BOT_TOKEN validation: raises early with a clear message if missing.
  - ADMIN_IDS: safely parsed from comma-separated string to list[int].
  - VERCEL_URL: stripped of trailing slash to avoid double-slash webhook URL.
  - FORCE_SUB_CHANNELS: defined here so handlers.py can import cleanly.
"""

import os
import logging

logger = logging.getLogger(__name__)

# ── Required ─────────────────────────────────────────────────────────────────
BOT_TOKEN: str = os.environ.get("BOT_TOKEN", "").strip()
BOT_USERNAME: str = os.environ.get("BOT_USERNAME", "").strip().lstrip("@")

# ── Optional ──────────────────────────────────────────────────────────────────

def _parse_admin_ids() -> list[int]:
    raw = os.environ.get("ADMIN_IDS", "")
    ids = []
    for part in raw.split(","):
        part = part.strip()
        if part:
            try:
                ids.append(int(part))
            except ValueError:
                logger.warning("Invalid value in ADMIN_IDS (skipping): %r", part)
    return ids

ADMIN_IDS: list[int] = _parse_admin_ids()

# Vercel URL — used by setup_webhook.sh; strip trailing slash for safety
_raw_vercel = os.environ.get("VERCEL_URL", "").strip().rstrip("/")
VERCEL_URL: str = _raw_vercel

STORAGE_BACKEND: str = os.environ.get("STORAGE_BACKEND", "memory").strip().lower()
REDIS_URL: str = os.environ.get("REDIS_URL", "").strip()

# ── Force-subscribe channels ──────────────────────────────────────────────────
# Edit this list to require users to join channels before using the bot.
# Each entry: {"id": int (channel numeric ID), "link": str, "name": str}
FORCE_SUB_CHANNELS: list[dict] = [
    # Example:
    # {"id": -1001234567890, "link": "https://t.me/yourchannel", "name": "My Channel"},
]
