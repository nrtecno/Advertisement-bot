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
    """Task ke liye Visit + Claim buttons."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Visit Link", url=advertiser_link)],
        [InlineKeyboardButton("✅ Claim 1 Credit", callback_data=f"claim_{link_id}")],
    ])


# ---------- MAIN ENTRY: Earn Credits button ----------
async def earn_credits_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User 'Earn Credits' dabata hai — active ads dikhao."""
    await ensure_user(update, context)
    user_id = update.effective_user.id

    try:
        links = await db.get_active_links()
    except Exception as e:
        logger.error(f"get_active_links error: {e}")
        await update.message.reply_text(
            "❌ Could not load ads right now. Please try again.",
            reply_markup=main_keyboard(),
        )
        return MAIN_MENU

    if not links:
        await update.message.reply_text(
            "📭 <b>No active advertisements right now.</b>\n\n"
            "Please check back later. New ads are added regularly!",
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(),
        )
        return MAIN_MENU

    # Filter links user has already claimed
    available = []
    for link in links:
        if not await db.has_clicked(link["id"], user_id):
            available.append(link)

    if not available:
        await update.message.reply_text(
            "✅ <b>You've already claimed all available ads!</b>\n\n"
            "Wait for new advertisements or check the menu later.",
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(),
        )
        return MAIN_MENU

    # Header message
    await update.message.reply_text(
        f"💰 <b>Earn Credits</b>\n\n"
        f"🎯 <b>{len(available)}</b> ad(s) available for you.\n"
        f"Each ad = <b>1 credit</b> (after 10 sec verification).\n\n"
        f"👇 Tap any ad below to start:",
        parse_mode=ParseMode.HTML,
    )

    # Send each ad as separate message with Earn button
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
        except Exception as e:
            logger.warning(f"Failed to send ad #{link['id']}: {e}")

    await update.message.reply_text(
        "👆 Tap an ad to begin. Good luck! 🍀",
        reply_markup=main_keyboard(),
    )
    return MAIN_MENU


# ---------- CALLBACK: User taps an ad from earn list ----------
async def earn_link_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User 'Earn X Credit' button dabata hai — task dikhao."""
    query = update.callback_query
    user_id = query.from_user.id

    # Parse link_id from earn_<id>
    try:
        link_id = int(query.data.split("_", 1)[1])
    except Exception as e:
        logger.error(f"Invalid earn data '{query.data}': {e}")
        await query.answer("❌ Invalid request.", show_alert=True)
        return

    # Ensure user exists
    await ensure_user(update, context)

    # Get link
    try:
        link = await db.get_link_by_id(link_id)
    except Exception as e:
        logger.error(f"DB error: {e}")
        await query.answer("❌ DB error.", show_alert=True)
        return

    if not link or link["status"] != "active":
        await query.answer("⚠️ This ad is no longer active.", show_alert=True)
        return

    # Already claimed?
    if await db.has_clicked(link_id, user_id):
        await query.answer("⚠️ You already claimed this ad!", show_alert=True)
        return

    # Start timer
    context.user_data[f"ad_start_{link_id}"] = time.time()

    # Show task message (as a reply to the button message)
    task_text = (
        f"📢 <b>Advertisement Task</b>\n\n"
        f"👇 <b>Step 1:</b> Click <b>Visit Link</b> below\n\n"
        f"🔗 Link: <code>{link['link']}</code>\n\n"
        f"⏱️ <b>Step 2:</b> Stay on that page for <b>{AD_WAIT_SECONDS} seconds</b>\n\n"
        f"✅ <b>Step 3:</b> Come back here and click <b>Claim 1 Credit</b>\n\n"
        f"⚠️ <i>Claim will only work after {AD_WAIT_SECONDS} seconds.</i>"
    )

    try:
        await query.message.reply_text(
            task_text,
            parse_mode=ParseMode.HTML,
            reply_markup=ad_task_keyboard(link["link"], link_id),
            disable_web_page_preview=True,
        )
        await query.answer("✅ Task started!")
    except Exception as e:
        logger.error(f"Failed to send task message: {e}")
        await query.answer("❌ Could not start task.", show_alert=True)
