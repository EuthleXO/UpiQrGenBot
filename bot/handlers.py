"""
bot/handlers.py  —  All Telegram command / callback / message handlers.

FIXES vs. the broken original:
  1. Every handler is a proper `async def` with correct signatures.
  2. ConversationHandler states are defined as module-level constants
     so they don't get re-created on every cold-start.
  3. back_keyboard() had an unused parameter — removed.
  4. /admin now reads from the storage layer, not a hardcoded file path.
  5. All bot text uses HTML parse_mode (bold/italic) consistently.
  6. Force-subscribe check is awaited properly.
  7. Group math shortcut uses a proper MessageFilter.
"""

import re
import logging
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

from bot.storage import get_storage
from bot.qr_generator import generate_qr_image
from bot.force_sub import check_force_sub
from config import ADMIN_IDS, BOT_USERNAME, FORCE_SUB_CHANNELS

logger = logging.getLogger(__name__)

# ── Watermark appended to every bot message ─────────────────────────────────
WATERMARK = "\n\n<i>Made by Euthle</i>"

# ── ConversationHandler states ───────────────────────────────────────────────
(
    MENU,
    ENTER_UPI,
    ENTER_AMOUNT,
    NUPI_ENTER_ID,
    NUPI_ENTER_AMOUNT,
) = range(5)


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────

def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Generate QR (saved UPI)", callback_data="gen_upi")],
        [InlineKeyboardButton("Generate QR (any UPI)", callback_data="gen_nupi")],
        [InlineKeyboardButton("Set / Change my UPI ID", callback_data="set_upi")],
        [InlineKeyboardButton("Help", callback_data="help")],
    ])


def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Back to Menu", callback_data="back_menu")],
    ])


async def force_sub_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Return True if user passes the force-subscribe gate (or gate is disabled)."""
    if not FORCE_SUB_CHANNELS:
        return True
    user_id = update.effective_user.id
    missing = await check_force_sub(context.bot, user_id)
    if not missing:
        return True

    buttons = [[InlineKeyboardButton(f"Join {ch['name']}", url=ch["link"])] for ch in missing]
    buttons.append([InlineKeyboardButton("I joined — check again", callback_data="recheck_sub")])
    msg = (
        "<b>Please join our channel(s) to use this bot:</b>"
        + WATERMARK
    )
    await update.effective_message.reply_html(msg, reply_markup=InlineKeyboardMarkup(buttons))
    return False


# ────────────────────────────────────────────────────────────────────────────
# /start
# ────────────────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await force_sub_check(update, context):
        return ConversationHandler.END

    storage = get_storage()
    user = update.effective_user
    storage.get_or_create_user(user.id, user.username or user.first_name)

    text = (
        f"<b>Welcome to UPI QR Generator Bot, {user.first_name}!</b>\n\n"
        "<i>Generate beautiful, themed UPI payment QR codes instantly.</i>"
        + WATERMARK
    )
    await update.message.reply_html(text, reply_markup=main_keyboard())
    return MENU


# ────────────────────────────────────────────────────────────────────────────
# /help
# ────────────────────────────────────────────────────────────────────────────

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "<b>Available commands:</b>\n\n"
        "<b>/start</b> — Open the main menu\n"
        "<b>/upi &lt;amount&gt;</b> — Generate QR from your saved UPI ID\n"
        "<b>/nupi &lt;upi_id&gt; &lt;amount&gt;</b> — Generate QR for any UPI ID\n"
        "<b>/setupi &lt;upi_id&gt;</b> — Save your UPI ID\n"
        "<b>/admin</b> — Admin panel (admins only)\n\n"
        "<i>You can also send a math expression like </i><b>50+50</b><i> in a group.</i>"
        + WATERMARK
    )
    await update.effective_message.reply_html(text, reply_markup=back_keyboard())


# ────────────────────────────────────────────────────────────────────────────
# /setupi — save UPI ID
# ────────────────────────────────────────────────────────────────────────────

async def set_upi_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_html(
            "<b>Usage:</b> <code>/setupi your@upi</code>" + WATERMARK
        )
        return
    upi_id = context.args[0].strip()
    storage = get_storage()
    user = update.effective_user
    storage.get_or_create_user(user.id, user.username or user.first_name)
    storage.set_upi(user.id, upi_id)
    await update.message.reply_html(
        f"<b>UPI ID saved:</b> <code>{upi_id}</code>" + WATERMARK
    )


# ────────────────────────────────────────────────────────────────────────────
# /upi <amount>  — generate QR from saved UPI
# ────────────────────────────────────────────────────────────────────────────

async def upi_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await force_sub_check(update, context):
        return

    user = update.effective_user
    storage = get_storage()
    user_data = storage.get_or_create_user(user.id, user.username or user.first_name)
    upi_id = user_data.get("upi_id")

    if not upi_id:
        await update.message.reply_html(
            "<b>You have not saved a UPI ID yet.</b>\n"
            "Use <code>/setupi your@upi</code> first." + WATERMARK
        )
        return

    if not context.args:
        await update.message.reply_html(
            "<b>Usage:</b> <code>/upi &lt;amount&gt;</code>\nExample: <code>/upi 100</code>"
            + WATERMARK
        )
        return

    try:
        amount = float(context.args[0])
    except ValueError:
        await update.message.reply_html("<b>Invalid amount.</b>" + WATERMARK)
        return

    await _send_qr(update, context, upi_id, amount)


# ────────────────────────────────────────────────────────────────────────────
# /nupi <upi_id> <amount>  — generate QR for any UPI
# ────────────────────────────────────────────────────────────────────────────

async def nupi_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await force_sub_check(update, context):
        return

    if len(context.args) < 2:
        await update.message.reply_html(
            "<b>Usage:</b> <code>/nupi upi_id amount</code>\n"
            "Example: <code>/nupi someone@upi 250</code>" + WATERMARK
        )
        return

    upi_id = context.args[0].strip()
    try:
        amount = float(context.args[1])
    except ValueError:
        await update.message.reply_html("<b>Invalid amount.</b>" + WATERMARK)
        return

    await _send_qr(update, context, upi_id, amount)


# ────────────────────────────────────────────────────────────────────────────
# Shared QR generation + send
# ────────────────────────────────────────────────────────────────────────────

async def _send_qr(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    upi_id: str,
    amount: float,
) -> None:
    user = update.effective_user
    msg = await update.effective_message.reply_html(
        "<i>Generating your QR code...</i>" + WATERMARK
    )

    # Try to get the user's profile photo as the centre logo
    profile_photo = None
    try:
        photos = await context.bot.get_user_profile_photos(user.id, limit=1)
        if photos.photos:
            file = await photos.photos[0][-1].get_file()
            profile_photo = await file.download_as_bytearray()
    except Exception:
        pass

    try:
        img_bytes = generate_qr_image(upi_id, amount, profile_photo)
    except Exception as exc:
        logger.exception("QR generation failed: %s", exc)
        await msg.edit_text("<b>Failed to generate QR. Please try again.</b>" + WATERMARK, parse_mode="HTML")
        return

    storage = get_storage()
    storage.increment_qr_count(user.id)

    caption = (
        f"<b>UPI:</b> <code>{upi_id}</code>\n"
        f"<b>Amount:</b> ₹{amount:.2f}"
        + WATERMARK
    )
    await update.effective_message.reply_photo(photo=img_bytes, caption=caption, parse_mode="HTML")
    await msg.delete()


# ────────────────────────────────────────────────────────────────────────────
# /admin
# ────────────────────────────────────────────────────────────────────────────

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        await update.message.reply_html("<b>Admins only.</b>" + WATERMARK)
        return

    storage = get_storage()
    stats = storage.get_stats()
    text = (
        "<b>Admin Panel</b>\n\n"
        f"<b>Total users:</b> {stats['total_users']}\n"
        f"<b>Total QRs generated:</b> {stats['total_qrs']}"
        + WATERMARK
    )
    await update.message.reply_html(text)


# ────────────────────────────────────────────────────────────────────────────
# Inline button callbacks
# ────────────────────────────────────────────────────────────────────────────

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "back_menu":
        await query.edit_message_text(
            "<b>Main Menu</b>" + WATERMARK,
            parse_mode="HTML",
            reply_markup=main_keyboard(),
        )
        return MENU

    if data == "help":
        text = (
            "<b>Commands:</b>\n\n"
            "<b>/upi &lt;amount&gt;</b> — QR from saved UPI\n"
            "<b>/nupi &lt;upi_id&gt; &lt;amount&gt;</b> — QR for any UPI\n"
            "<b>/setupi &lt;upi_id&gt;</b> — Save your UPI ID"
            + WATERMARK
        )
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=back_keyboard())
        return MENU

    if data == "set_upi":
        await query.edit_message_text(
            "<b>Send your UPI ID</b> (e.g. <code>name@upi</code>):" + WATERMARK,
            parse_mode="HTML",
            reply_markup=back_keyboard(),
        )
        return ENTER_UPI

    if data == "gen_upi":
        user = update.effective_user
        storage = get_storage()
        user_data = storage.get_or_create_user(user.id, user.username or user.first_name)
        if not user_data.get("upi_id"):
            await query.edit_message_text(
                "<b>No UPI ID saved.</b> Use /setupi first." + WATERMARK,
                parse_mode="HTML",
                reply_markup=back_keyboard(),
            )
            return MENU
        await query.edit_message_text(
            "<b>Enter the amount (₹):</b>" + WATERMARK,
            parse_mode="HTML",
            reply_markup=back_keyboard(),
        )
        return ENTER_AMOUNT

    if data == "gen_nupi":
        await query.edit_message_text(
            "<b>Enter the UPI ID</b> (e.g. <code>name@upi</code>):" + WATERMARK,
            parse_mode="HTML",
            reply_markup=back_keyboard(),
        )
        return NUPI_ENTER_ID

    if data == "recheck_sub":
        if await force_sub_check(update, context):
            await query.edit_message_text(
                "<b>You are now subscribed!</b> Use /start to begin." + WATERMARK,
                parse_mode="HTML",
            )
        return MENU

    return MENU


# ────────────────────────────────────────────────────────────────────────────
# ConversationHandler message steps
# ────────────────────────────────────────────────────────────────────────────

async def receive_upi_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    upi_id = update.message.text.strip()
    storage = get_storage()
    user = update.effective_user
    storage.get_or_create_user(user.id, user.username or user.first_name)
    storage.set_upi(user.id, upi_id)
    await update.message.reply_html(
        f"<b>UPI ID saved:</b> <code>{upi_id}</code>" + WATERMARK,
        reply_markup=main_keyboard(),
    )
    return MENU


async def receive_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        amount = float(update.message.text.strip())
    except ValueError:
        await update.message.reply_html("<b>Please enter a valid number.</b>" + WATERMARK)
        return ENTER_AMOUNT

    user = update.effective_user
    storage = get_storage()
    user_data = storage.get_or_create_user(user.id, user.username or user.first_name)
    upi_id = user_data.get("upi_id")

    if not upi_id:
        await update.message.reply_html(
            "<b>UPI ID not found. Please set it first.</b>" + WATERMARK,
            reply_markup=main_keyboard(),
        )
        return MENU

    await _send_qr(update, context, upi_id, amount)
    return MENU


async def nupi_receive_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["nupi_id"] = update.message.text.strip()
    await update.message.reply_html(
        "<b>Enter the amount (₹):</b>" + WATERMARK,
        reply_markup=back_keyboard(),
    )
    return NUPI_ENTER_AMOUNT


async def nupi_receive_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        amount = float(update.message.text.strip())
    except ValueError:
        await update.message.reply_html("<b>Please enter a valid number.</b>" + WATERMARK)
        return NUPI_ENTER_AMOUNT

    upi_id = context.user_data.get("nupi_id", "")
    await _send_qr(update, context, upi_id, amount)
    return MENU


# ────────────────────────────────────────────────────────────────────────────
# Group math shortcut:  "50+50" → "100"
# ────────────────────────────────────────────────────────────────────────────

_MATH_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*\+\s*(\d+(?:\.\d+)?)\s*$")


async def group_math(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    match = _MATH_RE.match(update.message.text or "")
    if match:
        result = float(match.group(1)) + float(match.group(2))
        # Format cleanly: drop .0 for whole numbers
        display = int(result) if result == int(result) else result
        await update.message.reply_text(str(display))


# ────────────────────────────────────────────────────────────────────────────
# Register everything with the Application
# ────────────────────────────────────────────────────────────────────────────

def register_handlers(application: Application) -> None:
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MENU: [CallbackQueryHandler(button_callback)],
            ENTER_UPI: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_upi_id),
                CallbackQueryHandler(button_callback),
            ],
            ENTER_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_amount),
                CallbackQueryHandler(button_callback),
            ],
            NUPI_ENTER_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, nupi_receive_id),
                CallbackQueryHandler(button_callback),
            ],
            NUPI_ENTER_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, nupi_receive_amount),
                CallbackQueryHandler(button_callback),
            ],
        },
        fallbacks=[CommandHandler("start", start)],
        # IMPORTANT for serverless: use per_message=False (default)
        # and per_chat=True (default). Do NOT set per_user=False unless intended.
        per_message=False,
    )

    application.add_handler(conv)

    # Standalone commands (work outside ConversationHandler too)
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("upi", upi_command))
    application.add_handler(CommandHandler("nupi", nupi_command))
    application.add_handler(CommandHandler("setupi", set_upi_command))
    application.add_handler(CommandHandler("admin", admin_command))

    # Catch-all callback for buttons outside a conversation
    application.add_handler(CallbackQueryHandler(button_callback))

    # Group math — only in groups, not private
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & (filters.ChatType.GROUP | filters.ChatType.SUPERGROUP),
            group_math,
        )
                              )
