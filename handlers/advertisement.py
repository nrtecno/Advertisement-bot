import asyncio
import logging
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

import database as db
from config import VIEWS_PER_CREDIT, BOT_USERNAME
from keyboards import main_keyboard, ad_earn_keyboard
from helpers import ensure_user, log_to_admin_channel
from states import (
    MAIN_MENU, AD_CALC_VIEWS, AD_LINK_INPUT, AD_FINAL_VIEWS,
)

logger = logging.getLogger(__name__)


async def advertisement_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"💰 <b>Digital Price Calculator</b>\n\n"
        f"• 1 credit = {VIEWS_PER_CREDIT} views/taps\n"
        f"• 4 credits = {4 * VIEWS_PER_CREDIT} views/taps\n\n"
        f"👉 <b>Enter the number of views/taps you want:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardRemove(),
    )
    return AD_CALC_VIEWS


async def ad_calc_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        views = int(update.message.text.strip())
        if views <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Please send a valid positive number.")
        return AD_CALC_VIEWS

    credits_needed = (views + VIEWS_PER_CREDIT - 1) // VIEWS_PER_CREDIT
    context.user_data["ad_calc_views"] = views

    await update.message.reply_text(
        f"📊 <b>Price Calculation</b>\n\n"
        f"👁️ Views: <b>{views}</b>\n"
        f"💳 Credits needed: <b>{credits_needed}</b>\n\n"
        f"📩 <b>Send your link for advertisement:</b>",
        parse_mode=ParseMode.HTML,
    )
    return AD_LINK_INPUT


async def ad_link_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link = update.message.text.strip()
    if not link.startswith(("http://", "https://", "t.me/")):
        await update.message.reply_text(
            "❌ Please send a valid link (http://, https:// or t.me/)."
        )
        return AD_LINK_INPUT

    if not link.startswith(("http://", "https://")):
        link = "https://" + link

    user_id = update.effective_user.id
    db_user = await db.get_user(user_id)
    credits = db_user["credits"]
    max_views = credits * VIEWS_PER_CREDIT

    context.user_data["ad_link"] = link

    await update.message.reply_text(
        f"💳 <b>Your Account</b>\n\n"
        f"Available credits: <b>{credits}</b>\n"
        f"Views you can get: <b>{max_views}</b>\n\n"
        f"👉 <b>How many views/taps do you need?</b> (Send a number)",
        parse_mode=ParseMode.HTML,
    )
    return AD_FINAL_VIEWS


async def ad_final_views(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        views_wanted = int(update.message.text.strip())
        if views_wanted <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Please send a valid positive number.")
        return AD_FINAL_VIEWS

    user_id = update.effective_user.id
    db_user = await db.get_user(user_id)
    credits = db_user["credits"]
    max_views = credits * VIEWS_PER_CREDIT
    link = context.user_data.get("ad_link")

    if not link:
        await update.message.reply_text("❌ Session expired. Please start again.")
        return MAIN_MENU

    if credits <= 0:
        await update.message.reply_text(
            "❌ You don't have any credits. Please buy credits first.",
            reply_markup=main_keyboard(),
        )
        return MAIN_MENU

    if views_wanted > max_views:
        credits_to_deduct = credits
        views_to_deliver = max_views
    else:
        credits_to_deduct = (views_wanted + VIEWS_PER_CREDIT - 1) // VIEWS_PER_CREDIT
        views_to_deliver = views_wanted

    await db.set_user_credits(user_id, credits - credits_to_deduct)
    link_id = await db.create_link(
        user_id, link, views_to_deliver, credits_to_deduct
    )

    await update.message.reply_text(
        f"✅ <b>Advertisement Created!</b>\n\n"
        f"🔗 Link: {link}\n"
        f"👁️ Target views: <b>{views_to_deliver}</b>\n"
        f"💳 Credits spent: <b>{credits_to_deduct}</b>\n"
        f"💳 Remaining credits: <b>{credits - credits_to_deduct}</b>\n\n"
        f"📢 Broadcasting to all users...",
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(),
    )

    await log_to_admin_channel(
        context,
        f"📢 <b>New Ad Created</b>\n"
        f"User: <code>{user_id}</code>\n"
        f"Link: {link}\n"
        f"Views: {views_to_deliver}\n"
        f"Credits: {credits_to_deduct}",
    )

    await broadcast_ad_to_users(context, link_id, link)

    context.user_data.pop("ad_calc_views", None)
    context.user_data.pop("ad_link", None)
    return MAIN_MENU


async def broadcast_ad_to_users(context, link_id: int, link: str):
    user_ids = await db.get_all_user_ids()
    state = await db.get_broadcast_state()
    if state and state.get("is_on") == 1:
        return

    deep_link = f"https://t.me/{BOT_USERNAME}?start=ad_{link_id}"
    keyboard = ad_earn_keyboard(deep_link)
    text = (
        f"🔗 <b>New Advertisement</b>\n\n"
        f"👇 Click below to view and earn 1 credit!"
    )

    for uid in user_ids:
        try:
            msg = await context.bot.send_message(
                chat_id=uid,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
            )
            await db.save_delivery(link_id, uid, msg.message_id)
            await asyncio.sleep(0.05)
        except Exception as e:
            logger.warning(f"Ad send failed for {uid}: {e}")


async def handle_ad_click(update: Update, context: ContextTypes.DEFAULT_TYPE,
                          link_id: int):
    user = update.effective_user
    user_id = user.id

    link = await db.get_link_by_id(link_id)
    if not link:
        await update.message.reply_text("❌ This ad no longer exists.")
        return

    if link["status"] != "active":
        await update.message.reply_text("✅ This ad has already been completed.")
        return

    await ensure_user(update, context)

    if await db.has_clicked(link_id, user_id):
        await update.message.reply_text(
            "⚠️ You already clicked this link. Only 1 credit per link.",
            reply_markup=main_keyboard(),
        )
        await update.message.reply_text(
            f"🔗 Here's the link again:\n{link['link']}"
        )
        return

    await db.record_click(link_id, user_id)
    await db.update_user_credits(user_id, 1)
    completed = await db.increment_link_views(link_id)

    await update.message.reply_text(
        f"✅ <b>+1 Credit Earned!</b>\n\n"
        f"🔗 Your link:\n{link['link']}\n\n"
        f"Thanks for supporting the community! 🙏",
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(),
    )

    if completed:
        await finalize_link(context, link_id)


async def finalize_link(context, link_id: int):
    link = await db.get_link_by_id(link_id)
    if not link:
        return

    deliveries = await db.get_deliveries_for_link(link_id)
    for d in deliveries:
        try:
            await context.bot.delete_message(
                chat_id=d["user_id"], message_id=d["message_id"]
            )
        except Exception:
            pass
        await asyncio.sleep(0.03)

    try:
        await context.bot.send_message(
            chat_id=link["user_id"],
            text=(
                f"🎉 <b>Your Advertisement is Completed!</b>\n\n"
                f"🔗 Link: {link['link']}\n"
                f"👁️ Views delivered: <b>{link['views_delivered']}/{link['views_target']}</b>\n\n"
                f"All ad messages have been removed from users' chats."
            ),
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.warning(f"Advertiser notify failed: {e}")
