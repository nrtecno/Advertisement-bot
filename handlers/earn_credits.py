import time
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

import database as db
from config import VIEWS_PER_CREDIT
from keyboards import main_keyboard
from helpers import ensure_user
from states import MAIN_MENU

logger = logging.getLogger(__name__)

AD_WAIT_SECONDS = 10


def earn_link_keyboard(link_id: int, views_left: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"🔗 Earn 1 Credit ({views_left} views left)",
            callback_data=f"earn_{link_id}"
        )],
    ])


def ad_task_keyboard(advertiser_link: str, link_id: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Visit Link", url=advertiser_link)],
        [InlineKeyboardButton("✅ Claim 1 Credit", callback_data=f"claim_{link_id}")],
    ])


# ---------- CORE: Send next available ad ----------
async def send_next_earn_ad(context, chat_id: int, user_id: int):
    """Ek available ad bhejo. Return True agar bheja, False agar koi nahi."""
    try:
        link = await db.get_next_available_link(user_id)
    except Exception as e:
        logger.error(f"get_next_available_link error: {e}")
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ Could not load ads right now. Please try again later.",
            reply_markup=main_keyboard(),
        )
        context.user_data.pop("in_earn_flow", None)
        return False

    if not link:
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "🎉 <b>No more ads available!</b>\n\n"
                "You've earned all available credits for now.\n"
                "New advertisements are added regularly — check back later!"
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(),
        )
        context.user_data.pop("in_earn_flow", None)
        return False

    views_left = link["views_target"] - link["views_delivered"]

    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"💰 <b>Earn Credits</b>\n\n"
                f"🔗 <b>Ad #{link['id']}</b>\n"
                f"👁️ Views left: <b>{views_left}</b>\n"
                f"💰 Reward: <b>1 credit</b>\n\n"
                f"👇 Tap below to start the task:"
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=earn_link_keyboard(link["id"], views_left),
        )
        logger.info(f"   📤 Next ad #{link['id']} sent to user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Send ad failed: {e}")
        return False


# ---------- MAIN ENTRY: Earn Credits button ----------
async def earn_credits_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info(f"━━━ 💰 EARN CREDITS clicked by {user_id} ━━━")

    try:
        await ensure_user(update, context)
    except Exception as e:
        logger.error(f"ensure_user: {e}")

    # Send first ad
    sent = await send_next_earn_ad(context, user_id, user_id)

    # Show how it works (only if ad sent)
    if sent:
        try:
            await update.message.reply_text(
                f"💡 <b>How it works:</b>\n\n"
                f"1️⃣ Tap the ad button above\n"
                f"2️⃣ Visit the link & stay for {AD_WAIT_SECONDS} seconds\n"
                f"3️⃣ Come back and claim your credit\n"
                f"4️⃣ Next ad appears automatically ✨",
                parse_mode=ParseMode.HTML,
                reply_markup=main_keyboard(),
            )
        except Exception as e:
            logger.error(f"Help msg error: {e}")

    return MAIN_MENU


# ---------- CALLBACK: User taps an ad to start task ----------
async def earn_link_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    logger.info(f"━━━ 🔗 EARN tap: {query.data} by {user_id} ━━━")

    try:
        link_id = int(query.data.split("_", 1)[1])
    except Exception as e:
        logger.error(f"Invalid earn data: {e}")
        await query.answer("❌ Invalid request.", show_alert=True)
        return

    try:
        await ensure_user(update, context)
    except Exception:
        pass

    try:
        link = await db.get_link_by_id(link_id)
    except Exception as e:
        logger.error(f"DB: {e}")
        await query.answer("❌ DB error.", show_alert=True)
        return

    if not link:
        await query.answer("⚠️ Ad not found.", show_alert=True)
        return
    if link["status"] != "active":
        await query.answer("⚠️ Ad no longer active.", show_alert=True)
        return

    try:
        already = await db.has_clicked(link_id, user_id)
    except Exception:
        already = False
    if already:
        await query.answer("⚠️ Already claimed!", show_alert=True)
        return

    # 🔑 Mark: user is in earn flow → after claim, next ad will be sent
    context.user_data["in_earn_flow"] = True
    context.user_data[f"ad_start_{link_id}"] = time.time()

    task_text = (
        f"📢 <b>Advertisement Task</b>\n\n"
        f"👇 <b>Step 1:</b> Click <b>Visit Link</b>\n\n"
        f"🔗 Link: <code>{link['link']}</code>\n\n"
        f"⏱️ <b>Step 2:</b> Stay for <b>{AD_WAIT_SECONDS} seconds</b>\n\n"
        f"✅ <b>Step 3:</b> Come back & click <b>Claim 1 Credit</b>"
    )

    try:
        await query.message.reply_text(
            task_text,
            parse_mode=ParseMode.HTML,
            reply_markup=ad_task_keyboard(link["link"], link_id),
            disable_web_page_preview=True,
        )
        await query.answer("✅ Task started!")
        logger.info(f"   ✅ Task shown for link#{link_id}")
    except Exception as e:
        logger.error(f"Task send failed: {e}")
        await query.answer("❌ Could not start task.", show_alert=True)
