import asyncio
import time
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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

# Wait time in seconds
AD_WAIT_SECONDS = 10


# ---------- AD TASK KEYBOARD ----------
def ad_task_keyboard(advertiser_link: str, link_id: int):
    """Ad task ke liye 2 buttons — visit + claim."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Visit Link", url=advertiser_link)],
        [InlineKeyboardButton("✅ Claim 1 Credit", callback_data=f"claim_{link_id}")],
    ])


# ---------- ADVERTISEMENT FLOW (Advertisement button) ----------
async def advertisement_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"💰 <b>Digital Price Calculator</b>\n\n"
        f"• 1 credit = {VIEWS_PER_CREDIT} views/taps\n"
        f"• 4 credits = {4 * VIEWS_PER_CREDIT} views/taps\n\n"
        f"👉 <b>Enter the number of views/taps you want:</b>",
        parse_mode=ParseMode.HTML,
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


# ---------- BROADCAST AD TO ALL USERS ----------
async def broadcast_ad_to_users(context, link_id: int, link: str):
    user_ids = await db.get_all_user_ids()
    state = await db.get_broadcast_state()
    if state and state.get("is_on") == 1:
        return

    deep_link = f"https://t.me/{BOT_USERNAME}?start=ad_{link_id}"
    keyboard = ad_earn_keyboard(deep_link)

    # Updated message text with 10-second instruction
    text = (
        f"🔗 <b>New Advertisement</b>\n\n"
        f"👉 Click & visit for <b>{AD_WAIT_SECONDS} seconds</b>.\n"
        f"💰 You will earn <b>1 credit</b> after verification!"
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


# ---------- AD CLICK HANDLER (deep-link se aata hai) ----------
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

    # Already claimed?
    if await db.has_clicked(link_id, user_id):
        await update.message.reply_text(
            "⚠️ <b>You already claimed this ad!</b>\n\n"
            "Only 1 credit per ad link. Please check other ads in menu.",
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(),
        )
        return

    # Store start time (per user, per link)
    context.user_data[f"ad_start_{link_id}"] = time.time()

    text = (
        f"📢 <b>Advertisement Task</b>\n\n"
        f"👇 <b>Step 1:</b> Click the button below to visit the link\n\n"
        f"🔗 <b>{link['link']}</b>\n\n"
        f"⏱️ <b>Step 2:</b> Stay on that page for <b>{AD_WAIT_SECONDS} seconds</b>\n\n"
        f"✅ <b>Step 3:</b> Come back here and click <b>Claim 1 Credit</b>\n\n"
        f"⚠️ <i>Claim button will only work after {AD_WAIT_SECONDS} seconds.</i>"
    )

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=ad_task_keyboard(link["link"], link_id),
        disable_web_page_preview=True,
    )


# ---------- CLAIM CREDIT CALLBACK ----------
async def claim_ad_credit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    # Parse link_id from callback data (claim_<id>)
    try:
        link_id = int(query.data.split("_", 1)[1])
    except Exception as e:
        logger.error(f"Invalid claim data '{query.data}': {e}")
        await query.answer("❌ Invalid request.", show_alert=True)
        return

    # --- Check timer ---
    start_key = f"ad_start_{link_id}"
    start_time = context.user_data.get(start_key)

    if start_time is None:
        await query.answer(
            "⚠️ Session expired. Please click the ad link again from menu.",
            show_alert=True,
        )
        return

    elapsed = time.time() - start_time
    if elapsed < AD_WAIT_SECONDS:
        remaining = int(AD_WAIT_SECONDS - elapsed) + 1
        await query.answer(
            f"⏱️ Please wait {remaining} more second(s) before claiming!",
            show_alert=True,
        )
        return

    # --- Check if already claimed ---
    if await db.has_clicked(link_id, user_id):
        await query.answer("⚠️ You already claimed this ad!", show_alert=True)
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        return

    # --- Verify link still active ---
    link = await db.get_link_by_id(link_id)
    if not link or link["status"] != "active":
        await query.answer("⚠️ This ad is completed.", show_alert=True)
        return

    # --- Credit user ---
    await db.record_click(link_id, user_id)
    await db.update_user_credits(user_id, 1)
    completed = await db.increment_link_views(link_id)

    # Remove claim button
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass

    # Success message
    try:
        await query.edit_message_text(
            f"🎉 <b>+1 Credit Earned!</b>\n\n"
            f"✅ Verification complete ({int(elapsed)}s).\n"
            f"💰 Your balance has been updated.\n\n"
            f"Thanks for supporting the community! 🙏",
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        await query.message.reply_text(
            f"🎉 <b>+1 Credit Earned!</b>",
            parse_mode=ParseMode.HTML,
        )

    await query.answer("✅ +1 Credit earned!")

    # Clear session
    context.user_data.pop(start_key, None)

    # If link completed, clean up
    if completed:
        await finalize_link(context, link_id)


# ---------- FINALIZE (when target views reached) ----------
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
