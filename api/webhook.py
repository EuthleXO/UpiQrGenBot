import sys
import os

# Make sure the project root is in the path so bot/ and config.py are importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import asyncio
import logging

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

_ptb_app = None


def get_ptb_app():
    global _ptb_app
    if _ptb_app is None:
        if not BOT_TOKEN:
            raise RuntimeError("BOT_TOKEN environment variable is not set.")
        _ptb_app = Application.builder().token(BOT_TOKEN).build()
        register_handlers(_ptb_app)
    return _ptb_app


async def _process(ptb_app, update):
    async with ptb_app:
        await ptb_app.process_update(update)


@app.route("/", methods=["GET"])
def index():
    return "UPI QR Bot is running.", 200


@app.route("/api/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json(force=True, silent=True)
        if not data:
            return Response("Bad Request", status=400)

        ptb_app = get_ptb_app()
        update = Update.de_json(data, ptb_app.bot)
        asyncio.run(_process(ptb_app, update))
        return Response("OK", status=200)

    except Exception as exc:
        logger.exception("Error processing update: %s", exc)
        return Response("OK", status=200)
      
