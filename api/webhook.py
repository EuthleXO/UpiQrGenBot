"""
Vercel serverless webhook entry point.

Each request is handled statelessly. The python-telegram-bot Application
is built once per warm container and reused across invocations within
that same process; cold starts rebuild it.
"""

import asyncio
import logging
import os
import sys
from typing import Optional

# Make sure the project root is on the path when running in Vercel
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from flask import Flask, request, Response
from telegram import Update
from telegram.ext import Application

from config import BOT_TOKEN, validate_config
from bot.handlers import register_handlers

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

_ptb_app: Optional[Application] = None


def _get_ptb_app() -> Application:
    global _ptb_app
    if _ptb_app is None:
        validate_config()
        _ptb_app = Application.builder().token(BOT_TOKEN).updater(None).build()
        register_handlers(_ptb_app)
    return _ptb_app


@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json(force=True)
    except Exception:
        logger.warning("Received non-JSON payload on /webhook")
        return Response("Bad JSON", status=400)

    if not data:
        return Response("Empty payload", status=400)

    try:
        ptb = _get_ptb_app()
    except RuntimeError as exc:
        logger.error("Configuration error: %s", exc)
        return Response("Server misconfigured", status=500)

    update = Update.de_json(data, ptb.bot)

    async def process():
        async with ptb:
            await ptb.process_update(update)

    try:
        asyncio.run(process())
    except Exception:
        logger.exception("Error while processing update")
        # Return 200 anyway so Telegram does not retry-storm the webhook
        # on a transient internal error.
        return Response("ok", status=200)

    return Response("ok", status=200)


@app.route("/", methods=["GET"])
def health():
    return Response("UPI QR Bot is running.", status=200)


# Local dev only — Vercel imports `app` directly and never runs this.
if __name__ == "__main__":
    app.run(port=8080, debug=True)
