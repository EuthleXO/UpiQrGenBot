from typing import List, Dict

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError

from config import FORCE_SUB_CHANNELS


async def check_membership(bot: Bot, user_id: int) -> List[Dict]:
    """Returns list of channels the user has NOT joined."""
    not_joined = []
    for channel in FORCE_SUB_CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=channel["id"], user_id=user_id)
            if member.status in ("left", "kicked", "banned"):
                not_joined.append(channel)
        except TelegramError:
            not_joined.append(channel)
    return not_joined


def build_force_sub_keyboard(not_joined: List[Dict]) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(f"Join {ch['name']}", url=ch["link"])]
        for ch in not_joined
    ]
    buttons.append([InlineKeyboardButton("Verify Membership", callback_data="verify_joined")])
    return InlineKeyboardMarkup(buttons)


FORCE_SUB_TEXT = (
    "<b>Access Restricted</b>\n\n"
    "<i>Join all required channels below, then tap Verify Membership to continue.</i>"
)
