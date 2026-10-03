from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

import database as db
from keyboards import main_keyboard
from states import MAIN_MENU


async def show_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    count = await db.get_user_count()
    await update.message.reply_text(
        f"👥 <b>Total Users in Bot:</b> <b>{count}</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(),
    )
    return MAIN_MENU
