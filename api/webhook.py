"""
api/webhook.py  —  Vercel serverless entry point for the Telegram bot.

ROOT CAUSE OF "BOT NOT RESPONDING":
  python-telegram-bot v20+ uses asyncio throughout. On Vercel (and any
  serverless platform) each request runs in a fresh Python process.
  The common mistake is calling Application.initialize() / .start() /
  .process_update() without properly managing the event loop, OR not
  awaiting the coroutine at all, which silently drops every update.

  This file fixes that with a clean asyncio.run() pattern and explicit
  Application lifecycle per request.
"""

import sys
import os

# Fix import path so bot/ and config.py are always found on Vercel
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import logging
from typing import Optional

from flask import Flask, request, Response
from telegram import Update
from telegram.ext import Application

from bot.handlers import register_handlers
from config import BOT_TOKEN

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Build the PTB Application once per cold-start and reuse it.
# We must NOT call app.run_polling() — we drive updates manually.
# ---------------------------------------------------------------------------
_ptb_app: Optional[Application] = None  # Compatible with Python 3.9


def get_ptb_app() -> Application:
    global _ptb_app
    if _ptb_app is None:
        if not BOT_TOKEN:
            raise RuntimeError("BOT_TOKEN environment variable is not set.")
        builder = Application.builder().token(BOT_TOKEN)
        _ptb_app = builder.build()
        register_handlers(_ptb_app)
    return _ptb_app


# ---------------------------------------------------------------------------
# Async processing helper
# ---------------------------------------------------------------------------
async def _process(ptb_app: Application, update: Update) -> None:
    """Initialize → process one update → shutdown (graceful per-request lifecycle)."""
    async with ptb_app:
        await ptb_app.process_update(update)


# ---------------------------------------------------------------------------
# Flask routes
# ---------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def index():
    return "UPI QR Bot is running.", 200


@app.route("/api/webhook", methods=["POST"])
def webhook():
    """Telegram calls this URL for every update."""
    try:
        data = request.get_json(force=True, silent=True)
        if not data:
            logger.warning("Received empty or non-JSON payload")
            return Response("Bad Request", status=400)

        ptb_app = get_ptb_app()
        update = Update.de_json(data, ptb_app.bot)

        # Run the coroutine in a fresh event loop each time.
        # asyncio.run() is safe here: Vercel gives each request its own thread.
        asyncio.run(_process(ptb_app, update))

        return Response("OK", status=200)

    except Exception as exc:
        logger.exception("Error processing update: %s", exc)
        # Always return 200 so Telegram doesn't keep retrying a broken payload.
        return Response("OK", status=200)


# ---------------------------------------------------------------------------
# Local dev runner (not used by Vercel)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=True)
    
