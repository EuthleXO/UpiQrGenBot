import io
import logging
import random
import re
from typing import Optional

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ContextTypes, ConversationHandler, filters,
)
from telegram.constants import ParseMode

from config import BOT_USERNAME, ADMIN_IDS, FORCE_SUB_CHANNELS
from bot.storage import get_user, save_user, increment_qr_count, all_users
from bot.force_sub import check_membership, build_force_sub_keyboard, FORCE_SUB_TEXT
from bot.qr_generator import generate_qr_image, THEMES

logger = logging.getLogger(__name__)

WATERMARK = "<i>Made by Euthle</i>"

# ─── ConversationHandler states ──────────────────────────────────────────────
SETUP_UPI, SETUP_NAME, SETUP_HIDE = range(3)


# ─── Keyboards ───────────────────────────────────────────────────────────────
def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Profile", callback_data="profile"),
            InlineKeyboardButton("Settings", callback_data="settings"),
        ],
        [
            InlineKeyboardButton("Stats", callback_data="stats"),
            InlineKeyboardButton("Help", callback_data="help"),
        ],
        [InlineKeyboardButton("Donate Stars", callback_data="donate_stars")],
    ])


def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Back", callback_data="back_main")],
    ])


def _with_watermark(body: str) -> str:
    return f"{body}\n\n{WATERMARK}"


def _home_text() -> str:
    return _with_watermark(
        "<b>Advanced QR Engine</b>\n\n"
        "<i>Generate stunning UPI payment QR codes instantly.</i>\n"
        "Manage your profile and settings below."
    )


# ─── Force-sub gate ──────────────────────────────────────────────────────────
async def _force_sub_gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Returns True if user passes (or no channels configured). Sends warning if not."""
    if not FORCE_SUB_CHANNELS:
        return True
    user_id = update.effective_user.id
    not_joined = await check_membership(context.bot, user_id)
    if not not_joined:
        return True
    kb = build_force_sub_keyboard(not_joined)
    msg = update.message or (update.callback_query and update.callback_query.message)
    if msg:
        await msg.reply_text(_with_watermark(FORCE_SUB_TEXT), reply_markup=kb, parse_mode=ParseMode.HTML)
    return False


# ─── /start ──────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _force_sub_gate(update, context):
        return
    await update.message.reply_text(
        _home_text(),
        reply_markup=main_menu_keyboard(),
        parse_mode=ParseMode.HTML,
    )


# ─── Callback: main menu buttons ─────────────────────────────────────────────
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "back_main":
        await query.edit_message_text(
            _home_text(),
            reply_markup=main_menu_keyboard(),
            parse_mode=ParseMode.HTML,
        )

    elif data == "profile":
        user = get_user(query.from_user.id)
        upi = user.get("upi") or "Not set"
        name = user.get("name") or "Not set"
        hide = user.get("hide_upi", True)
        visibility = "Hidden" if hide else "Shown"
        await query.edit_message_text(
            _with_watermark(
                "<b>Your Profile</b>\n\n"
                f"<i>UPI ID:</i> <code>{upi}</code>\n"
                f"<i>Name:</i> <b>{name}</b>\n"
                f"<i>Visibility:</i> <b>{visibility}</b>\n"
                "<i>Logo source:</i> <b>Telegram profile photo</b>"
            ),
            reply_markup=back_keyboard(),
            parse_mode=ParseMode.HTML,
        )

    elif data == "stats":
        user = get_user(query.from_user.id)
        count = user.get("qr_count", 0)
        encouragement = "Generate your first QR to get started!" if count == 0 else "Keep it up!"
        await query.edit_message_text(
            _with_watermark(
                "<b>Your Statistics</b>\n\n"
                f"<i>Total QRs Generated:</i> <b>{count}</b>\n"
                f"<i>{encouragement}</i>"
            ),
            reply_markup=back_keyboard(),
            parse_mode=ParseMode.HTML,
        )

    elif data == "help":
        await query.edit_message_text(
            _with_watermark(
                "<b>Help &amp; Commands</b>\n\n"
                "<code>/upi &lt;amount&gt;</code> <i>— Generate your QR</i>\n"
                "<code>/nupi &lt;upi_id&gt; &lt;amount&gt;</code> <i>— Custom QR</i>\n"
                f"<code>@{BOT_USERNAME} &lt;amount&gt;</code> <i>— Invoice Mode</i>\n"
                "<code>/admin</code> <i>— Admin panel</i>\n"
                "<code>50+50</code> <i>— Auto math in groups</i>"
            ),
            reply_markup=back_keyboard(),
            parse_mode=ParseMode.HTML,
        )

    elif data == "settings":
        await query.edit_message_text(
            _with_watermark(
                "<b>Settings Menu</b>\n"
                "<i>Manage your configuration here.</i>"
            ),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Set up UPI", callback_data="setup_upi")],
                [InlineKeyboardButton("Back", callback_data="back_main")],
            ]),
            parse_mode=ParseMode.HTML,
        )

    elif data == "donate_stars":
        await query.edit_message_text(
            _with_watermark(
                "<b>Donate Stars</b>\n\n"
                "<i>Support this bot by sending Telegram Stars.</i>\n"
                "Every star helps keep the bot running."
            ),
            reply_markup=back_keyboard(),
            parse_mode=ParseMode.HTML,
        )

    elif data == "verify_joined":
        not_joined = await check_membership(context.bot, query.from_user.id)
        if not_joined:
            kb = build_force_sub_keyboard(not_joined)
            await query.edit_message_text(_with_watermark(FORCE_SUB_TEXT), reply_markup=kb, parse_mode=ParseMode.HTML)
        else:
            await query.edit_message_text(
                _with_watermark("<b>Verified!</b>\n\n<i>Use /start to begin.</i>"),
                parse_mode=ParseMode.HTML,
            )

    elif data == "close_qr":
        await query.message.delete()


# ─── UPI Setup Conversation ───────────────────────────────────────────────────
async def setup_upi_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        _with_watermark("<b>UPI Setup</b>\n\n<i>Send me your UPI ID:</i>"),
        parse_mode=ParseMode.HTML,
    )
    return SETUP_UPI


async def setup_receive_upi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    upi_id = update.message.text.strip()
    context.user_data["setup_upi"] = upi_id
    await update.message.reply_text(
        _with_watermark(
            f"<b>UPI saved:</b> <code>{upi_id}</code>\n\n"
            "<i>Now send your Display Name:</i>"
        ),
        parse_mode=ParseMode.HTML,
    )
    return SETUP_NAME


async def setup_receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    context.user_data["setup_name"] = name
    await update.message.reply_text(
        _with_watermark(
            f"<b>Name saved:</b> <b>{name}</b>\n\n"
            "<i>Hide your actual UPI ID on the QR code?</i>"
        ),
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Hide UPI", callback_data="hide_upi_yes"),
                InlineKeyboardButton("Show UPI", callback_data="hide_upi_no"),
            ]
        ]),
        parse_mode=ParseMode.HTML,
    )
    return SETUP_HIDE


async def setup_hide_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    hide = query.data == "hide_upi_yes"
    user_id = query.from_user.id
    user = get_user(user_id)
    user["upi"] = context.user_data.get("setup_upi", "")
    user["name"] = context.user_data.get("setup_name", "")
    user["hide_upi"] = hide
    save_user(user_id, user)
    await query.edit_message_text(
        _with_watermark(
            "<b>Profile setup complete!</b>\n\n"
            f"<i>UPI:</i> <code>{user['upi']}</code>\n"
            f"<i>Name:</i> <b>{user['name']}</b>\n"
            f"<i>Visibility:</i> <b>{'Hidden' if hide else 'Shown'}</b>\n\n"
            "Now use <code>/upi &lt;amount&gt;</code> to generate your QR!"
        ),
        parse_mode=ParseMode.HTML,
    )
    context.user_data.clear()
    return ConversationHandler.END


async def setup_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        _with_watermark("<i>Setup cancelled. Use /start to begin again.</i>"),
        parse_mode=ParseMode.HTML,
    )
    return ConversationHandler.END


# ─── QR Generation helpers ────────────────────────────────────────────────────
async def _fetch_profile_photo(context, user_id: int) -> Optional[bytes]:
    try:
        photos = await context.bot.get_user_profile_photos(user_id, limit=1)
        if photos.total_count == 0:
            return None
        file = await photos.photos[0][0].get_file()
        buf = io.BytesIO()
        await file.download_to_memory(buf)
        return buf.getvalue()
    except Exception:
        return None


async def _send_qr(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    upi_id: str,
    display_name: str,
    amount: str,
    hide_upi: bool,
    user_id: int,
):
    profile_bytes = await _fetch_profile_photo(context, user_id)
    theme = random.choice(THEMES)
    img_bytes = generate_qr_image(
        upi_id=upi_id,
        display_name=display_name,
        amount=amount,
        hide_upi=hide_upi,
        profile_photo_bytes=profile_bytes,
        bot_username=BOT_USERNAME,
        theme=theme,
    )
    increment_qr_count(user_id)
    caption = _with_watermark(f"<b>QR Code for ₹{amount}</b>")
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Close", callback_data="close_qr")]])
    target = update.message or update.callback_query.message
    await target.reply_photo(
        photo=io.BytesIO(img_bytes),
        caption=caption,
        reply_markup=kb,
        parse_mode=ParseMode.HTML,
    )


# ─── /upi <amount> ───────────────────────────────────────────────────────────
async def cmd_upi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _force_sub_gate(update, context):
        return
    args = context.args
    if not args:
        await update.message.reply_text(
            _with_watermark(
                "<i>Usage:</i> <code>/upi &lt;amount&gt;</code>\n"
                "<i>Example:</i> <code>/upi 500</code>"
            ),
            parse_mode=ParseMode.HTML,
        )
        return
    amount = args[0]
    try:
        float(amount)
    except ValueError:
        await update.message.reply_text(
            _with_watermark("<i>Invalid amount. Use a number like</i> <code>/upi 100</code>."),
            parse_mode=ParseMode.HTML,
        )
        return
    user_id = update.effective_user.id
    user = get_user(user_id)
    if not user.get("upi"):
        await update.message.reply_text(
            _with_watermark(
                "<i>You haven't set up your UPI yet.</i>\n\n"
                "Use /start → Settings → Set up UPI."
            ),
            parse_mode=ParseMode.HTML,
        )
        return
    await _send_qr(
        update, context,
        upi_id=user["upi"],
        display_name=user.get("name", ""),
        amount=amount,
        hide_upi=user.get("hide_upi", True),
        user_id=user_id,
    )


# ─── /nupi <upi_id> <amount> ─────────────────────────────────────────────────
async def cmd_nupi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _force_sub_gate(update, context):
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            _with_watermark(
                "<i>Usage:</i> <code>/nupi &lt;upi_id&gt; &lt;amount&gt;</code>\n"
                "<i>Example:</i> <code>/nupi user@bank 250</code>"
            ),
            parse_mode=ParseMode.HTML,
        )
        return
    upi_id, amount = args[0], args[1]
    try:
        float(amount)
    except ValueError:
        await update.message.reply_text(
            _with_watermark("<i>Invalid amount.</i>"),
            parse_mode=ParseMode.HTML,
        )
        return
    user_id = update.effective_user.id
    user = get_user(user_id)
    await _send_qr(
        update, context,
        upi_id=upi_id,
        display_name=user.get("name", upi_id),
        amount=amount,
        hide_upi=False,
        user_id=user_id,
    )


# ─── Group math: 50+50 auto-calc ─────────────────────────────────────────────
_MATH_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\+(\d+(?:\.\d+)?)")


async def group_math(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    text = update.message.text.strip()
    match = _MATH_PATTERN.fullmatch(text.replace(" ", ""))
    if match:
        a, b = float(match.group(1)), float(match.group(2))
        result = a + b
        result_str = str(int(result)) if result == int(result) else str(result)
        await update.message.reply_text(
            f"<code>{text}</code> = <b>{result_str}</b>",
            parse_mode=ParseMode.HTML,
        )


# ─── /admin ───────────────────────────────────────────────────────────────────
async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text(
            _with_watermark("<i>Admins only.</i>"),
            parse_mode=ParseMode.HTML,
        )
        return
    users = all_users()
    total_users = len(users)
    total_qrs = sum(u.get("qr_count", 0) for u in users.values())
    await update.message.reply_text(
        _with_watermark(
            "<b>Admin Panel</b>\n\n"
            f"<i>Total Users:</i> <b>{total_users}</b>\n"
            f"<i>Total QRs Generated:</i> <b>{total_qrs}</b>"
        ),
        parse_mode=ParseMode.HTML,
    )


# ─── Register all handlers ────────────────────────────────────────────────────
def register_handlers(app: Application):
    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(setup_upi_start, pattern="^setup_upi$")],
        states={
            SETUP_UPI: [MessageHandler(filters.TEXT & ~filters.COMMAND, setup_receive_upi)],
            SETUP_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, setup_receive_name)],
            SETUP_HIDE: [
                CallbackQueryHandler(setup_hide_choice, pattern="^hide_upi_(yes|no)$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", setup_cancel)],
        per_message=False,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("upi", cmd_upi))
    app.add_handler(CommandHandler("nupi", cmd_nupi))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS,
        group_math,
    ))
