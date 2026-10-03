import asyncio
import logging
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

import database as db
from config import ADMIN_ID
from keyboards import main_keyboard, cast_keyboard
from states import MAIN_MENU, BROADCAST_CONTROL, BROADCAST_MESSAGE

logger = logging.getLogger(__name__)


async def cast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ You are not authorized.")
        return MAIN_MENU

    state = await db.get_broadcast_state()
    status = "🟢 ON" if state.get("is_on") == 1 else "🔴 OFF"

    await update.message.reply_text(
        f"🎛️ <b>Broadcast Control</b>\n\n"
        f"Current status: <b>{status}</b>\n\n"
        f"Choose an option:",
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
            "🟢 <b>Broadcast Mode</b>\n\n"
            "Send the message you want to broadcast.\n\n"
            "⚠️ It will be sent <b>once</b> to all users, then bot "
            "automatically returns to normal mode.",
            parse_mode=ParseMode.HTML,
        )
        return BROADCAST_MESSAGE

    elif data == "cast_off":
        await db.set_broadcast_state(0, "")
        await query.edit_message_text(
            "🔴 <b>Broadcast OFF</b>\n\nBot is now in normal mode.",
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

    # Get all users
    user_ids = await db.get_all_user_ids()

    # Status message
    status_msg = await update.message.reply_text(
        f"📤 Broadcasting to <b>{len(user_ids)}</b> users...",
        parse_mode=ParseMode.HTML,
    )

    success, failed = 0, 0

    # Send ONCE to every user
    for uid in user_ids:
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=message_text,
                parse_mode=ParseMode.HTML,
            )
            success += 1
            await asyncio.sleep(0.05)  # rate limit safety
        except Exception as e:
            logger.warning(f"Broadcast to {uid} failed: {e}")
            failed += 1

    # 🔥 AUTO RESET — broadcast off + message cleared
    # Isse message dobara kabhi repeat nahi hoga
    await db.set_broadcast_state(0, "")
    logger.info(f"✅ Broadcast done. Reset state. Success={success}, Failed={failed}")

    # Final status to admin
    try:
        await status_msg.edit_text(
            f"✅ <b>Broadcast Sent!</b>\n\n"
            f"✅ Success: <b>{success}</b>\n"
            f"❌ Failed: <b>{failed}</b>\n\n"
            f"🔴 Bot is now back to <b>normal mode</b>.\n"
            f"<i>Message will not be repeated to users.</i>",
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        await update.message.reply_text(
            f"✅ Broadcast sent!\nSuccess: {success}\nFailed: {failed}\n\n"
            f"Bot is back to normal mode.",
            reply_markup=main_keyboard(),
        )

    return MAIN_MENU
