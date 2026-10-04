import time
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


def earn_link_keyboard(link_id: int, views_left: int, credits_reward: int = 1):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"🔗 Earn {credits_reward} Credit ({views_left} left)",
            callback_data=f"earn_{link_id}"
        )],
    ])


def ad_task_keyboard(advertiser_link: str, link_id: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Visit Link", url=advertiser_link)],
        [InlineKeyboardButton("✅ Claim 1 Credit", callback_data=f"claim_{link_id}")],
    ])


# ---------- MAIN ENTRY: Earn Credits button ----------
async def earn_credits_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User 'Earn Credits' dabata hai — active ads dikhao."""
    user_id = update.effective_user.id
    logger.info(f"━━━ 💰 EARN CREDITS clicked by user {user_id} ━━━")

    try:
        await ensure_user(update, context)
    except Exception as e:
        logger.error(f"ensure_user failed: {e}")

    try:
        links = await db.get_active_links()
        logger.info(f"   📊 DB returned {len(links)} active link(s)")
    except Exception as e:
        logger.error(f"❌ get_active_links error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        await update.message.reply_text(
            "❌ <b>Could not load ads right now.</b>\n\n"
            "Please try again in a moment.",
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(),
        )
        return MAIN_MENU

    if not links:
        logger.info("   ℹ️ No active links in DB")
        await update.message.reply_text(
            "📭 <b>No active advertisements right now.</b>\n\n"
            "New ads are added regularly. Please check back later!",
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(),
        )
        return MAIN_MENU

    # Filter out ads the user has already claimed
    available = []
    for link in links:
        try:
            clicked = await db.has_clicked(link["id"], user_id)
            logger.info(f"   🔗 link#{link['id']} already_clicked={clicked}")
            if not clicked:
                available.append(link)
        except Exception as e:
            logger.error(f"   ⚠️ has_clicked error for #{link['id']}: {e}")
            # Still add it, be lenient
            available.append(link)

    logger.info(f"   ✅ available for user: {len(available)}")

    if not available:
        await update.message.reply_text(
            "✅ <b>You've already claimed all available ads!</b>\n\n"
            "Wait for new advertisements to appear.",
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(),
        )
        return MAIN_MENU

    # Send header
    try:
        await update.message.reply_text(
            f"💰 <b>Earn Credits</b>\n\n"
            f"🎯 <b>{len(available)}</b> ad(s) available for you.\n"
            f"Each ad = <b>1 credit</b> (after {AD_WAIT_SECONDS} sec).\n\n"
            f"👇 Tap any ad below to start:",
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.error(f"Header send error: {e}")

    # Send each ad message
    for link in available:
        views_left = link["views_target"] - link["views_delivered"]
        try:
            await update.message.reply_text(
                f"🔗 <b>Ad #{link['id']}</b>\n"
                f"👁️ Views left: <b>{views_left}</b>\n"
                f"💰 Reward: <b>1 credit</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=earn_link_keyboard(link["id"], views_left),
            )
            logger.info(f"   📤 Ad #{link['id']} sent to user")
        except Exception as e:
            logger.error(f"Failed to send ad #{link['id']}: {e}")

    try:
        await update.message.reply_text(
            "👆 Tap an ad above to begin. Good luck! 🍀",
            reply_markup=main_keyboard(),
        )
    except Exception as e:
        logger.error(f"Footer send error: {e}")

    return MAIN_MENU


# ---------- CALLBACK: User taps an ad ----------
async def earn_link_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    logger.info(f"━━━ 🔗 EARN callback: {query.data} by {user_id} ━━━")

    try:
        link_id = int(query.data.split("_", 1)[1])
    except Exception as e:
        logger.error(f"Invalid earn data '{query.data}': {e}")
        await query.answer("❌ Invalid request.", show_alert=True)
        return

    try:
        await ensure_user(update, context)
    except Exception as e:
        logger.error(f"ensure_user failed: {e}")

    try:
        link = await db.get_link_by_id(link_id)
    except Exception as e:
        logger.error(f"DB error: {e}")
        await query.answer("❌ DB error.", show_alert=True)
        return

    if not link:
        await query.answer("⚠️ Ad not found.", show_alert=True)
        return

    if link["status"] != "active":
        await query.answer("⚠️ This ad is no longer active.", show_alert=True)
        return

    try:
        already = await db.has_clicked(link_id, user_id)
    except Exception:
        already = False

    if already:
        await query.answer("⚠️ You already claimed this ad!", show_alert=True)
        return

    # Start 10-sec timer
    context.user_data[f"ad_start_{link_id}"] = time.time()

    task_text = (
        f"📢 <b>Advertisement Task</b>\n\n"
        f"👇 <b>Step 1:</b> Click <b>Visit Link</b>\n\n"
        f"🔗 Link: <code>{link['link']}</code>\n\n"
        f"⏱️ <b>Step 2:</b> Stay on page for <b>{AD_WAIT_SECONDS} seconds</b>\n\n"
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
