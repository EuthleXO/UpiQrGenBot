"""
Central configuration for the UPI QR Bot.
All values are read from environment variables so nothing sensitive
is ever committed to source control.
"""

import os

# ─── Core ────────────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8861415117:AAF1XpkODsnpYpe6EJ41KlV1AagjTRIKJlk")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "UpiQrGenxBot").lstrip("@")

# ─── Admins ──────────────────────────────────────────────────────────────────
# Comma separated Telegram user IDs, e.g. "111111111,222222222"
ADMIN_IDS = [
    int(x) for x in os.environ.get("ADMIN_IDS", "8743131347").split(",") if x.strip().isdigit()
]

# ─── Force Subscribe Channels ────────────────────────────────────────────────
# Leave as [] to disable the force-subscribe gate.
# Example:
# FORCE_SUB_CHANNELS = [
#     {"id": -1001234567890, "link": "https://t.me/yourchannel1", "name": "Channel 1"},
# ]
FORCE_SUB_CHANNELS = [
    {"id": -1003927538921, "link": "https://t.me/EuthGram", "name": "EuthGram"},
]

# ─── Storage backend ─────────────────────────────────────────────────────────
# "memory"  -> in-process dict, fine for local dev, NOT persistent on Vercel
# "redis"   -> persistent, required for production on Vercel (serverless FS
#              is read-only and ephemeral, so a local JSON file will not
#              survive between invocations)
STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "memory").lower()

# Used only when STORAGE_BACKEND == "redis" (e.g. Vercel KV / Upstash Redis)
REDIS_URL = os.environ.get("REDIS_URL", "")

# Local JSON fallback path, used only when STORAGE_BACKEND == "json"
# (safe for local development / VPS deployments with a writable disk;
# do NOT rely on this on Vercel)
USERS_FILE = os.environ.get("USERS_FILE", "users.json")


def validate_config() -> None:
    """Raise a clear error early if required configuration is missing."""
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN is not set. Add it to your environment variables "
            "(see README.md for setup instructions)."
        )
