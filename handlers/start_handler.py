from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

import database as db
from config import ADMIN_ID, VIEWS_PER_CREDIT
from keyboards import main_keyboard
from helpers import (
    is_user_joined, ensure_user, log_to_admin_channel,
)
from states import MAIN_MENU


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # Deep-link click tracking: /start ad_<link_id>
    if context.args:
        arg = context.args[0]
        if arg.startswith("ad_"):
            try:
                link_id = int(arg.replace("ad_", ""))
                from handlers.advertisement import handle_ad_click
                await handle_ad_click(update, context, link_id)
                return MAIN_MENU
            except (ValueError, IndexError):
                pass

    db_user = await ensure_user(update, context)

    if user.id != ADMIN_ID and not await is_user_joined(context, user.id):
        from keyboards import join_keyboard
        await update.message.reply_text(
            "🔒 <b>Access Restricted</b>\n\n"
            "You must join our channel to use this bot.",
            parse_mode=ParseMode.HTML,
            reply_markup=join_keyboard(),
        )
        return MAIN_MENU

    state = await db.get_broadcast_state()
    if state and state.get("is_on") == 1 and state.get("message"):
        await update.message.reply_text(
            state["message"],
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(),
        )
        return MAIN_MENU

    credits = db_user["credits"]
    max_views = credits * VIEWS_PER_CREDIT
    await update.message.reply_text(
        f"👋 <b>Welcome, {user.first_name}!</b>\n\n"
        f"💳 Credits: <b>{credits}</b>\n"
        f"👁️ You can get <b>{max_views}</b> views/taps\n\n"
        f"Choose an option below 👇",
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(),
    )
    return MAIN_MENU


async def verify_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if await is_user_joined(context, user_id):
        db_user = await db.get_user(user_id)
        credits = db_user["credits"] if db_user else 0
        await query.edit_message_text(
            f"✅ <b>Verified!</b>\n\n"
            f"💳 Credits: <b>{credits}</b>\n"
            f"👁️ Views available: <b>{credits * VIEWS_PER_CREDIT}</b>",
            parse_mode=ParseMode.HTML,
        )
        await query.message.reply_text(
            "Use the menu below 👇", reply_markup=main_keyboard()
        )
    else:
        await query.answer(
            "❌ You haven't joined yet! Please join first.",
            show_alert=True,
        )
    return MAIN_MENU


async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Catch-all for main menu — routes text to the right handler."""
    text = update.message.text

    from helpers import check_join_and_proceed
    if not await check_join_and_proceed(update, context):
        return MAIN_MENU

    state = await db.get_broadcast_state()
    if (state and state.get("is_on") == 1
            and update.effective_user.id != ADMIN_ID):
        if state.get("message"):
            await update.message.reply_text(
                state["message"], parse_mode=ParseMode.HTML,
            )
        return MAIN_MENU

    if text == "📢 Advertisement":
        from handlers.advertisement import advertisement_start
        return await advertisement_start(update, context)
    elif text == "💳 Buy Credits":
        from handlers.buy_credits import buy_credits_start
        return await buy_credits_start(update, context)
    elif text == "👥 Users":
        from handlers.users import show_users
        return await show_users(update, context)

    return MAIN_MENU
