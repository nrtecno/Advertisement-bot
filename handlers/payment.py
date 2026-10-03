import logging
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

import database as db
from config import ADMIN_ID
from keyboards import main_keyboard

logger = logging.getLogger(__name__)


async def payment_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    # ---------- STEP 1: Logging ----------
    logger.info(
        f"🔔 Payment callback received: data={query.data} "
        f"from_user={query.from_user.id} username=@{query.from_user.username} "
        f"ADMIN_ID={ADMIN_ID}"
    )

    # ---------- STEP 2: Answer the callback FIRST (once only) ----------
    try:
        await query.answer()
    except Exception as e:
        logger.warning(f"query.answer() failed: {e}")

    # ---------- STEP 3: Admin check ----------
    if query.from_user.id != ADMIN_ID:
        logger.warning(
            f"⛔ Unauthorized click: from_user={query.from_user.id} "
            f"!= ADMIN_ID={ADMIN_ID}"
        )
        try:
            await query.answer("⛔ Not authorized!", show_alert=True)
        except Exception:
            pass
        return

    # ---------- STEP 4: Parse data ----------
    try:
        data = query.data
        action, order_id_str = data.split("_", 1)
        order_id = int(order_id_str)
    except Exception as e:
        logger.error(f"❌ Failed to parse callback data '{query.data}': {e}")
        try:
            await query.answer("❌ Invalid data!", show_alert=True)
        except Exception:
            pass
        return

    logger.info(f"📦 Processing order_id={order_id} action={action}")

    # ---------- STEP 5: Get order from DB ----------
    try:
        order = await db.get_pending_order(order_id)
    except Exception as e:
        logger.error(f"❌ DB get_pending_order error: {e}")
        try:
            await query.answer("❌ DB error!", show_alert=True)
        except Exception:
            pass
        return

    if not order:
        logger.warning(f"❌ Order #{order_id} not found")
        try:
            await query.answer("❌ Order not found!", show_alert=True)
        except Exception:
            pass
        return

    logger.info(f"✅ Order found: {dict(order)}")

    if order["status"] != "pending":
        logger.warning(f"⚠️ Order #{order_id} already {order['status']}")
        try:
            await query.answer(f"Already {order['status']}!", show_alert=True)
        except Exception:
            pass
        return

    user_id = order["user_id"]
    credits = order["credits"]
    amount = order["amount"]
    admin_tag = f"@{query.from_user.username or query.from_user.id}"

    # ---------- APPROVE ----------
    if action == "approve":
        try:
            await db.update_user_credits(user_id, credits)
            await db.update_order_status(order_id, "approved")
            logger.info(f"✅ Order #{order_id} approved. +{credits} credits to user {user_id}")
        except Exception as e:
            logger.error(f"❌ DB update error on approve: {e}")
            try:
                await query.answer("❌ DB error!", show_alert=True)
            except Exception:
                pass
            return

        # Notify user
        try:
            db_user = await db.get_user(user_id)
            new_credits = db_user["credits"] if db_user else credits
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    f"🎉 <b>Payment Approved!</b>\n\n"
                    f"🆔 Order ID: <code>#{order_id}</code>\n"
                    f"💰 Amount: <b>₹{amount:.2f}</b>\n"
                    f"💳 Credits added: <b>{credits}</b>\n"
                    f"💼 Total Credits: <b>{new_credits}</b>\n\n"
                    f"Thank you for your purchase! 🙏"
                ),
                parse_mode=ParseMode.HTML,
                reply_markup=main_keyboard(),
            )
            logger.info(f"✅ User {user_id} notified about approval")
        except Exception as e:
            logger.error(f"⚠️ User notify error (approve): {e}")

        # Update admin message caption
        try:
            old_caption = query.message.caption or ""
            new_caption = old_caption + f"\n\n✅ <b>APPROVED</b> by {admin_tag}"
            await context.bot.edit_message_caption(
                chat_id=query.message.chat_id,
                message_id=query.message.message_id,
                caption=new_caption,
                parse_mode=ParseMode.HTML,
            )
            logger.info(f"✅ Admin message caption updated")
        except Exception as e:
            logger.warning(f"⚠️ Caption edit failed (approve): {e}")

        try:
            await query.answer("✅ Approved!")
        except Exception:
            pass

    # ---------- REJECT ----------
    elif action == "reject":
        try:
            await db.update_order_status(order_id, "rejected")
            logger.info(f"❌ Order #{order_id} rejected")
        except Exception as e:
            logger.error(f"❌ DB update error on reject: {e}")
            try:
                await query.answer("❌ DB error!", show_alert=True)
            except Exception:
                pass
            return

        # Notify user
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    f"❌ <b>Payment Rejected</b>\n\n"
                    f"🆔 Order ID: <code>#{order_id}</code>\n"
                    f"💰 Amount: <b>₹{amount:.2f}</b>\n\n"
                    f"Your payment could not be verified. "
                    f"Please contact admin if you believe this is a mistake."
                ),
                parse_mode=ParseMode.HTML,
                reply_markup=main_keyboard(),
            )
            logger.info(f"✅ User {user_id} notified about rejection")
        except Exception as e:
            logger.error(f"⚠️ User notify error (reject): {e}")

        # Update admin message caption
        try:
            old_caption = query.message.caption or ""
            new_caption = old_caption + f"\n\n❌ <b>REJECTED</b> by {admin_tag}"
            await context.bot.edit_message_caption(
                chat_id=query.message.chat_id,
                message_id=query.message.message_id,
                caption=new_caption,
                parse_mode=ParseMode.HTML,
            )
            logger.info(f"✅ Admin message caption updated")
        except Exception as e:
            logger.warning(f"⚠️ Caption edit failed (reject): {e}")

        try:
            await query.answer("❌ Rejected!")
        except Exception:
            pass
