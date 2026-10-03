from telegram import (
    InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
)
from config import CHANNEL_ID


def main_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["📢 Advertisement", "💳 Buy Credits"],
            ["💰 Earn Credits", "👥 Users"],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def join_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "📢 Join Channel",
            url=f"https://t.me/{CHANNEL_ID.lstrip('@')}"
        )],
        [InlineKeyboardButton("✅ Verify", callback_data="verify_join")],
    ])


def cast_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 ON", callback_data="cast_on")],
        [InlineKeyboardButton("🔴 OFF", callback_data="cast_off")],
    ])


def buy_button_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 BUY", callback_data="buy_credits")],
    ])


def ad_earn_keyboard(deep_link: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👉 Tap & Earn 1 Credit", url=deep_link)],
    ])


def approve_reject_keyboard(order_id: int):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_{order_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_{order_id}"),
        ]
    ])
