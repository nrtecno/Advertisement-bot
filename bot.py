import os
import logging
import asyncio
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, ReplyKeyboardRemove,
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler,
)
from telegram.constants import ParseMode

import database as db
from config import (
    BOT_TOKEN, BOT_USERNAME, CHANNEL_ID, ADMIN_ID, ADMIN_CHANNEL_ID,
    UPI_ID, UPI_NAME, CREDITS_PER_RUPEE, VIEWS_PER_CREDIT,
    PAY_IMAGE_PATH,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---------- STATES ----------
(
    MAIN_MENU,
    AD_CALC_VIEWS,
    AD_LINK_INPUT,
    AD_FINAL_VIEWS,
    BUY_CREDITS_INPUT,
    BUY_SCREENSHOT_INPUT,
    BROADCAST_CONTROL,
    BROADCAST_MESSAGE,
) = range(8)


# ---------- KEYBOARDS ----------
def main_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["📢 Advertisement", "💳 Buy Credits"],
            ["👥 Users"],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def join_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "📢 Join Channel",
            url=f"https://t.me/{CHANNEL_ID.lstrip('@')}"
        )],
        [InlineKeyboardButton("✅ Verify", callback_data="verify_join")],
    ])


def cast_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 ON", callback_data="cast_on")],
        [InlineKeyboardButton("🔴 OFF", callback_data="cast_off")],
    ])


# ---------- HELPERS ----------
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


# ---------- /start ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # Deep-link click tracking: /start ad_<link_id>
    if context.args:
        arg = context.args[0]
        if arg.startswith("ad_"):
            try:
                link_id = int(arg.replace("ad_", ""))
                await handle_ad_click(update, context, link_id)
                return MAIN_MENU
            except (ValueError, IndexError):
                pass

    db_user = await ensure_user(update, context)

    if user.id != ADMIN_ID and not await is_user_joined(context, user.id):
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


# ---------- VERIFY ----------
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


# ---------- MAIN MENU ----------
async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

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
        return await advertisement_start(update, context)
    elif text == "💳 Buy Credits":
        return await buy_credits_start(update, context)
    elif text == "👥 Users":
        return await show_users(update, context)

    return MAIN_MENU


# ---------- ADVERTISEMENT FLOW ----------
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

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("👉 Tap & Earn 1 Credit", url=deep_link)],
    ])

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


# ---------- AD CLICK HANDLER ----------
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


# ---------- BUY CREDITS ----------
async def buy_credits_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = await db.get_user(user.id)
    credits = db_user["credits"] if db_user else 0
    max_views = credits * VIEWS_PER_CREDIT
    mobile = db_user.get("mobile") if db_user else None

    text = (
        f"💳 <b>Your Account Details</b>\n\n"
        f"🆔 Telegram ID: <code>{user.id}</code>\n"
        f"👤 Username: @{user.username or 'Not set'}\n"
        f"📱 Mobile: {mobile or 'Not set'}\n\n"
        f"💰 Available Credits: <b>{credits}</b>\n"
        f"👁️ Views you can get: <b>{max_views}</b>\n\n"
        f"Click BUY to purchase more credits."
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 BUY", callback_data="buy_credits")],
    ])

    await update.message.reply_text(
        text, parse_mode=ParseMode.HTML, reply_markup=keyboard,
    )
    return MAIN_MENU


async def buy_credits_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id

    pending = await db.get_user_pending_orders(user_id)
    if pending:
        await query.edit_message_text(
            "⏳ <b>You already have a pending payment!</b>\n\n"
            "Please wait for admin approval before placing a new order.",
            parse_mode=ParseMode.HTML,
        )
        return MAIN_MENU

    await query.edit_message_text(
        "💰 <b>How many credits do you want to buy?</b>\n\n"
        "Send a number 👇",
        parse_mode=ParseMode.HTML,
    )
    return BUY_CREDITS_INPUT


async def buy_credits_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        credits_to_buy = int(update.message.text.strip())
        if credits_to_buy <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Please send a valid positive number.")
        return BUY_CREDITS_INPUT

    amount_rupees = credits_to_buy / CREDITS_PER_RUPEE
    context.user_data["buy_credits"] = credits_to_buy
    context.user_data["buy_amount"] = amount_rupees

    # Check pay.png exists
    if not os.path.exists(PAY_IMAGE_PATH):
        logger.error(f"pay.png not found at {PAY_IMAGE_PATH}")
        await update.message.reply_text(
            "❌ Payment QR not available right now. Please contact admin.",
            reply_markup=main_keyboard(),
        )
        return MAIN_MENU

    caption = (
        f"💳 <b>Payment Details</b>\n\n"
        f"💰 Amount to pay: <b>₹{amount_rupees:.2f}</b>\n"
        f"💳 Credits you'll get: <b>{credits_to_buy}</b>\n\n"
        f"📸 <b>Scan the QR above with PhonePe / any UPI app and pay ₹{amount_rupees:.2f}.</b>\n\n"
        f"After payment, <b>send the payment screenshot here</b> for verification.\n\n"
        f"⚠️ <i>Send exact amount — otherwise verification may fail.</i>"
    )

    try:
        with open(PAY_IMAGE_PATH, "rb") as photo:
            await update.message.reply_photo(
                photo=photo,
                caption=caption,
                parse_mode=ParseMode.HTML,
            )
    except Exception as e:
        logger.error(f"Failed to send pay.png: {e}")
        await update.message.reply_text(
            "❌ Failed to send payment QR. Please try again.",
            reply_markup=main_keyboard(),
        )
        return MAIN_MENU

    return BUY_SCREENSHOT_INPUT


async def buy_screenshot_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    if not update.message.photo:
        await update.message.reply_text(
            "❌ Please send a <b>screenshot (photo)</b> of your payment.",
            parse_mode=ParseMode.HTML,
        )
        return BUY_SCREENSHOT_INPUT

    credits_to_buy = context.user_data.get("buy_credits")
    amount = context.user_data.get("buy_amount")
    if not credits_to_buy or not amount:
        await update.message.reply_text(
            "❌ Session expired. Please start again from Buy Credits.",
            reply_markup=main_keyboard(),
        )
        return MAIN_MENU

    file_id = update.message.photo[-1].file_id

    order_id = await db.create_pending_order(
        user_id, credits_to_buy, amount, file_id
    )

    await update.message.reply_text(
        f"✅ <b>Screenshot received!</b>\n\n"
        f"🆔 Order ID: <code>#{order_id}</code>\n"
        f"💳 Credits: <b>{credits_to_buy}</b>\n"
        f"💰 Amount: <b>₹{amount:.2f}</b>\n\n"
        f"⏳ Your payment is pending admin approval. "
        f"You'll be notified once verified.",
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(),
    )

    if ADMIN_CHANNEL_ID:
        caption = (
            f"🔔 <b>NEW PAYMENT REQUEST</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🆔 Order ID: <code>#{order_id}</code>\n"
            f"👤 Name: {user.first_name}\n"
            f"🔗 Username: @{user.username or 'N/A'}\n"
            f"🆔 User ID: <code>{user.id}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💳 Credits Requested: <b>{credits_to_buy}</b>\n"
            f"💰 Payment Amount: <b>₹{amount:.2f}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⏳ Status: <b>PENDING</b>"
        )

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Approve", callback_data=f"approve_{order_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject_{order_id}"),
            ]
        ])

        try:
            admin_msg = await context.bot.send_photo(
                chat_id=ADMIN_CHANNEL_ID,
           
