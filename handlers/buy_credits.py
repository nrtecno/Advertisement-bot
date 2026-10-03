import os
import logging
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

import database as db
from config import (
    CREDITS_PER_RUPEE, VIEWS_PER_CREDIT, PAY_IMAGE_PATH, ADMIN_CHANNEL_ID,
)
from keyboards import main_keyboard, buy_button_keyboard, approve_reject_keyboard
from states import MAIN_MENU, BUY_CREDITS_INPUT, BUY_SCREENSHOT_INPUT

logger = logging.getLogger(__name__)


async def buy_credits_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = await db.get_user(user.id)
    credits = db_user["credits"] if db_user else 0
    max_views = credits * VIEWS_PER_CREDIT
    mobile = db_user.get("mobile") if db_user else None

    text = (
        f"💳 <b>Your Account Details</b>\n\n"
        f"🆔 Telegram ID: <code>{user.id}</code>\n"
        f"👤 Username: @{user.username or 'Not set'}\n"
        f"📱 Mobile: {mobile or 'Not set'}\n\n"
        f"💰 Available Credits: <b>{credits}</b>\n"
        f"👁️ Views you can get: <b>{max_views}</b>\n\n"
        f"Click BUY to purchase more credits."
    )

    await update.message.reply_text(
        text, parse_mode=ParseMode.HTML,
        reply_markup=buy_button_keyboard(),
    )
    return MAIN_MENU


async def buy_credits_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    pending = await db.get_user_pending_orders(user_id)
    if pending:
        await query.edit_message_text(
            "⏳ <b>You already have a pending payment!</b>\n\n"
            "Please wait for admin approval before placing a new order.",
            parse_mode=ParseMode.HTML,
        )
        return MAIN_MENU

    await query.edit_message_text(
        "💰 <b>How many credits do you want to buy?</b>\n\n"
        "Send a number 👇",
        parse_mode=ParseMode.HTML,
    )
    return BUY_CREDITS_INPUT


async def buy_credits_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        credits_to_buy = int(update.message.text.strip())
        if credits_to_buy <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Please send a valid positive number.")
        return BUY_CREDITS_INPUT

    amount_rupees = credits_to_buy / CREDITS_PER_RUPEE
    context.user_data["buy_credits"] = credits_to_buy
    context.user_data["buy_amount"] = amount_rupees

    if not os.path.exists(PAY_IMAGE_PATH):
        logger.error(f"pay.png not found at {PAY_IMAGE_PATH}")
        await update.message.reply_text(
            "❌ Payment QR not available right now. Please contact admin.",
            reply_markup=main_keyboard(),
        )
        return MAIN_MENU

    caption = (
        f"💳 <b>Payment Details</b>\n\n"
        f"💰 Amount to pay: <b>₹{amount_rupees:.2f}</b>\n"
        f"💳 Credits you'll get: <b>{credits_to_buy}</b>\n\n"
        f"📸 <b>Scan the QR above with PhonePe / any UPI app and pay ₹{amount_rupees:.2f}.</b>\n\n"
        f"After payment, <b>send the payment screenshot here</b> for verification.\n\n"
        f"⚠️ <i>Send exact amount — otherwise verification may fail.</i>"
    )

    try:
        with open(PAY_IMAGE_PATH, "rb") as photo:
            await update.message.reply_photo(
                photo=photo,
                caption=caption,
                parse_mode=ParseMode.HTML,
            )
    except Exception as e:
        logger.error(f"Failed to send pay.png: {e}")
        await update.message.reply_text(
            "❌ Failed to send payment QR. Please try again.",
            reply_markup=main_keyboard(),
        )
        return MAIN_MENU

    return BUY_SCREENSHOT_INPUT


async def buy_screenshot_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    if not update.message.photo:
        await update.message.reply_text(
            "❌ Please send a <b>screenshot (photo)</b> of your payment.",
            parse_mode=ParseMode.HTML,
        )
        return BUY_SCREENSHOT_INPUT

    credits_to_buy = context.user_data.get("buy_credits")
    amount = context.user_data.get("buy_amount")
    if not credits_to_buy or not amount:
        await update.message.reply_text(
            "❌ Session expired. Please start again from Buy Credits.",
            reply_markup=main_keyboard(),
        )
        return MAIN_MENU

    file_id = update.message.photo[-1].file_id
    order_id = await db.create_pending_order(
        user_id, credits_to_buy, amount, file_id
    )

    await update.message.reply_text(
        f"✅ <b>Screenshot received!</b>\n\n"
        f"🆔 Order ID: <code>#{order_id}</code>\n"
        f"💳 Credits: <b>{credits_to_buy}</b>\n"
        f"💰 Amount: <b>₹{amount:.2f}</b>\n\n"
        f"⏳ Your payment is pending admin approval. "
        f"You'll be notified once verified.",
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(),
    )

    if ADMIN_CHANNEL_ID:
        caption = (
            f"🔔 <b>NEW PAYMENT REQUEST</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🆔 Order ID: <code>#{order_id}</code>\n"
            f"👤 Name: {user.first_name}\n"
            f"🔗 Username: @{user.username or 'N/A'}\n"
            f"🆔 User ID: <code>{user.id}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💳 Credits Requested: <b>{credits_to_buy}</b>\n"
            f"💰 Payment Amount: <b>₹{amount:.2f}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⏳ Status: <b>PENDING</b>"
        )

        try:
            admin_msg = await context.bot.send_photo(
                chat_id=ADMIN_CHANNEL_ID,
                photo=file_id,
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=approve_reject_keyboard(order_id),
            )
            await db.set_order_admin_message(order_id, admin_msg.message_id)
        except Exception as e:
            logger.error(f"Admin channel send error: {e}")

    context.user_data.pop("buy_credits", None)
    context.user_data.pop("buy_amount", None)
    return MAIN_MENU
