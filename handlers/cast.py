import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

import database as db
from config import ADMIN_ID
from keyboards import main_keyboard, cast_keyboard
from states import MAIN_MENU, BROADCAST_CONTROL, BROADCAST_MESSAGE


async def cast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ You are not authorized.")
        return MAIN_MENU

    await update.message.reply_text(
        "🎛️ <b>Broadcast Control</b>\n\nChoose an option:",
        parse_mode=ParseMode.HTML,
        reply_markup=cast_keyboard(),
    )
    return BROADCAST_CONTROL


async def cast_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_ID:
        await query.answer("⛔ Not authorized!", show_alert=True)
        return

    data = query.data

    if data == "cast_on":
        await db.set_broadcast_state(1, "")
        await query.edit_message_text(
            "🟢 <b>Broadcast ON</b>\n\n"
            "Send the message you want to broadcast to all users:",
            parse_mode=ParseMode.HTML,
        )
        return BROADCAST_MESSAGE

    elif data == "cast_off":
        await db.set_broadcast_state(0, "")
        await query.edit_message_text(
            "🔴 <b>Broadcast OFF</b>\n\n"
            "Bot is now in normal mode. User links will be shown again.",
            parse_mode=ParseMode.HTML,
        )
        await context.bot.send_message(
            chat_id=query.from_user.id,
            text="Menu ready 👇",
            reply_markup=main_keyboard(),
        )
        return MAIN_MENU


async def broadcast_message_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return MAIN_MENU

    message_text = update.message.text
    state = await db.get_broadcast_state()
    if state["is_on"] != 1:
        await update.message.reply_text("Broadcast is OFF. Use /cast to enable.")
        return MAIN_MENU

    await db.set_broadcast_state(1, message_text)

    user_ids = await db.get_all_user_ids()
    success, failed = 0, 0
    for uid in user_ids:
        try:
            await context.bot.send_message(
                chat_id=uid, text=message_text, parse_mode=ParseMode.HTML,
            )
            success += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1

    await update.message.reply_text(
        f"✅ <b>Broadcast Sent!</b>\n\n"
        f"✅ Success: {success}\n"
        f"❌ Failed: {failed}",
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(),
    )
    return MAIN_MENU
