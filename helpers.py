import logging
from telegram.constants import ParseMode
import database as db
from config import CHANNEL_ID, ADMIN_ID, ADMIN_CHANNEL_ID
from keyboards import join_keyboard

logger = logging.getLogger(__name__)


async def is_user_joined(context, user_id):
    try:
        member = await context.bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception as e:
        logger.error(f"Join check error: {e}")
        return False


async def log_to_admin_channel(context, text):
    if ADMIN_CHANNEL_ID:
        try:
            await context.bot.send_message(
                chat_id=ADMIN_CHANNEL_ID,
                text=text,
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            logger.error(f"Admin log error: {e}")


async def ensure_user(update, context):
    user = update.effective_user
    db_user = await db.get_user(user.id)
    if not db_user:
        db_user = await db.create_user(user.id, user.username, user.first_name)
        await log_to_admin_channel(
            context,
            f"🆕 <b>New User</b>\n"
            f"ID: <code>{user.id}</code>\n"
            f"Name: {user.first_name}\n"
            f"Username: @{user.username or 'N/A'}",
        )
    return db_user


async def check_join_and_proceed(update, context):
    user = update.effective_user
    if user.id == ADMIN_ID:
        return True
    if await is_user_joined(context, user.id):
        return True
    text = (
        "⚠️ <b>You must join our channel to use this bot!</b>\n\n"
        "Please join and then click Verify."
    )
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode=ParseMode.HTML, reply_markup=join_keyboard(),
        )
    else:
        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML, reply_markup=join_keyboard(),
        )
    return False
