#!/usr/bin/env bash
# Registers the Telegram webhook for this bot.
#
# Usage:
#   BOT_TOKEN=xxx VERCEL_URL=https://your-app.vercel.app ./setup_webhook.sh
set -euo pipefail

TOKEN="${BOT_TOKEN:?Set BOT_TOKEN env var, e.g. BOT_TOKEN=xxx VERCEL_URL=https://yourapp.vercel.app ./setup_webhook.sh}"
URL="${VERCEL_URL:?Set VERCEL_URL env var, e.g. BOT_TOKEN=xxx VERCEL_URL=https://yourapp.vercel.app ./setup_webhook.sh}"

# Strip a trailing slash if present so we don't end up with a double slash.
URL="${URL%/}"

echo "Setting webhook to ${URL}/webhook ..."
curl -s "https://api.telegram.org/bot${TOKEN}/setWebhook?url=${URL}/webhook" | python3 -m json.tool

echo ""
echo "Current webhook info:"
curl -s "https://api.telegram.org/bot${TOKEN}/getWebhookInfo" | python3 -m json.tool
