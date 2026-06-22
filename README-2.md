# UPI QR Generator Bot

A Telegram bot that generates premium, themed UPI payment QR codes on demand.
Built with `python-telegram-bot`, rendered with Pillow, and deployed as a
serverless webhook on Vercel.

Made by Euthle.

---

## Features

- `/upi <amount>` — generate a QR from your saved UPI ID
- `/nupi <upi_id> <amount>` — generate a QR for any UPI ID on the fly
- 5 visual themes: Neon Green, Cyber Blue, Gold Premium, Purple Galaxy, Red Alert
- Telegram profile photo embedded as the center logo on the QR
- Optional force-subscribe gate (require users to join channels first)
- Group math shortcut: send `50+50` in a group and the bot replies with `100`
- `/admin` panel for admins (total users, total QRs generated)
- Guided UPI setup flow via inline buttons
- "Made by Euthle" watermark on every generated QR card and every bot message

---

## What changed in this build

The original project had two issues that would have broken it in production
on Vercel, both fixed here:

1. **User data was stored in a local JSON file.** Vercel serverless
   functions run on a read-only, ephemeral filesystem — writes either fail
   or vanish the moment the container recycles, silently losing every
   user's profile and QR count. Storage is now a pluggable backend
   (`memory`, `json`, or `redis`); use `redis` in production. See
   [Storage backend](#storage-backend) below.
2. **Fonts were loaded from system paths** (`/usr/share/fonts/...`) that do
   not exist on Vercel's minimal Python runtime. Every QR card would have
   silently fallen back to a tiny, unstyled bitmap font. Two bold (and
   bold-italic) TrueType fonts are now bundled in `/fonts` and shipped with
   the function via `vercel.json`, so rendering is identical everywhere.

Smaller fixes: removed emoji from all bot UI text and buttons, made every
piece of bot text consistently bold/italic via Telegram's HTML formatting,
fixed an unused parameter in `back_keyboard()`, fixed the `/admin` command to
read from the storage layer instead of a hardcoded file path, added
input validation for `BOT_TOKEN`/`ADMIN_IDS`, and added `.env.example` /
`.gitignore`.

---

## File Structure

```
upi-qr-bot/
├── api/
│   └── webhook.py        # Flask webhook — Vercel entry point
├── bot/
│   ├── __init__.py
│   ├── handlers.py        # Commands, callbacks, conversation flow
│   ├── qr_generator.py    # Pillow QR card renderer (5 themes)
│   ├── force_sub.py       # Multi-channel membership checker
│   └── storage.py         # Pluggable user store (memory / json / redis)
├── fonts/
│   ├── DejaVuSansMono-Bold.ttf
│   └── DejaVuSansMono-BoldOblique.ttf
├── config.py               # Reads all settings from environment variables
├── requirements.txt
├── vercel.json
├── setup_webhook.sh
├── .env.example
├── .gitignore
└── README.md
```

---

## Setup

### 1. Create your bot

Message [@BotFather](https://t.me/BotFather) on Telegram, create a bot, and
note your `BOT_TOKEN` and `BOT_USERNAME`.

### 2. Local development

```bash
git clone <your-repo-url>
cd upi-qr-bot
pip install -r requirements.txt
cp .env.example .env
# edit .env and fill in BOT_TOKEN, BOT_USERNAME, ADMIN_IDS
```

Run it locally:

```bash
export $(grep -v '^#' .env | xargs)   # load .env into your shell
python api/webhook.py
```

This starts a Flask dev server on `http://localhost:8080`. To receive real
Telegram updates locally, expose it with a tunnel (e.g.
[ngrok](https://ngrok.com)):

```bash
ngrok http 8080
BOT_TOKEN=xxx VERCEL_URL=https://<your-ngrok-id>.ngrok.io ./setup_webhook.sh
```

### 3. Deploy to Vercel

```bash
npm i -g vercel
vercel login
cd upi-qr-bot
vercel
```

### 4. Set environment variables

In the Vercel dashboard (Project → Settings → Environment Variables):

| Variable          | Required | Example                          |
|-------------------|----------|-----------------------------------|
| `BOT_TOKEN`       | Yes      | token from BotFather               |
| `BOT_USERNAME`    | Yes      | `UpiQrGenBot` (no `@`)             |
| `ADMIN_IDS`       | No       | `111111111,222222222`              |
| `STORAGE_BACKEND` | Recommended | `redis`                         |
| `REDIS_URL`       | If using redis | `redis://default:pass@host:6379` |

### 5. Register the webhook

```bash
BOT_TOKEN=xxx VERCEL_URL=https://your-app.vercel.app ./setup_webhook.sh
```

### 6. (Optional) Force-subscribe channels

Edit `config.py`:

```python
FORCE_SUB_CHANNELS = [
    {"id": -1001234567890, "link": "https://t.me/yourchannel", "name": "My Channel"},
]
```

To get a channel's numeric `id`, add the bot as admin to the channel and
forward any message from the channel to
[@JsonDumpBot](https://t.me/JsonDumpBot) (or similar), or call
`getChat` on the Bot API with the channel's `@username`.

---

## Storage backend

Set `STORAGE_BACKEND` in your environment:

- **`memory`** (default) — data lives only in process memory. Fine for a
  quick local test, but a Vercel cold start wipes everything. Do not use
  this in production.
- **`json`** — writes to `users.json` on local disk. Works for local
  development or a traditional VPS with a persistent filesystem. Will
  **not** work reliably on Vercel.
- **`redis`** — persistent and safe for serverless. Works with
  [Vercel KV](https://vercel.com/docs/storage/vercel-kv), [Upstash
  Redis](https://upstash.com/), or any Redis-compatible service — just
  point `REDIS_URL` at it. This is the recommended backend for any real
  deployment.

---

## Customization

**Add a new QR theme** — open `bot/qr_generator.py` and add an entry to the
`THEMES` list with `bg`, `border`, `text`, `dim_text`, `qr_fill`, and
`qr_back` RGB tuples. A random theme is chosen on every QR generated.

**Change fonts** — replace the files in `/fonts` and update `FONT_BOLD` /
`FONT_BOLD_ITALIC` in `bot/qr_generator.py`. Keep both a bold and a
bold-italic variant so all card text stays bold/italic.

**Change the watermark text** — edit `WATERMARK_TEXT` in
`bot/qr_generator.py` (QR cards) and `WATERMARK` in `bot/handlers.py` (bot
messages).

**Change card size** — edit `card_w`, `card_h`, and `qr_size` near the top
of `generate_qr_image()` in `bot/qr_generator.py`.

**Add a new command** — write an `async def` handler in `bot/handlers.py`
following the existing pattern, then register it with
`app.add_handler(CommandHandler("yourcommand", your_handler))` inside
`register_handlers()`.

---

## QR Themes Reference

| Theme         | Background | Accent     |
|---------------|------------|------------|
| Neon Green    | `#080A08`  | `#00FF64`  |
| Cyber Blue    | `#050814`  | `#00B4FF`  |
| Gold Premium  | `#0A0802`  | `#D4AF37`  |
| Purple Galaxy | `#080212`  | `#B432FF`  |
| Red Alert     | `#0C0202`  | `#FF2828`  |

---

## Troubleshooting

- **Bot doesn't respond after deploying** — check `getWebhookInfo` (run
  `setup_webhook.sh` again, it prints this) for a `last_error_message`.
  Usually means `BOT_TOKEN` is missing/wrong in Vercel's environment
  variables, or the webhook URL is wrong.
- **QR text looks tiny/garbled in production but fine locally** — the
  `fonts/` directory wasn't included in the deployed function bundle.
  Confirm `vercel.json` still has the `includeFiles: "fonts/**"` config
  and redeploy.
- **User data resets after a while** — you're on `STORAGE_BACKEND=memory`
  or `json` on Vercel. Switch to `redis` (see above).
- **`/admin` says "Admins only" even for you** — your numeric Telegram
  user ID isn't in `ADMIN_IDS`. Message
  [@userinfobot](https://t.me/userinfobot) to get your ID.
