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
    await query.answer()

    if query.from_user.id != ADMIN_ID:
        await query.answer("⛔ Not authorized!", show_alert=True)
        return

    data = query.data
    action, order_id_str = data.split("_", 1)
    order_id = int(order_id_str)

    order = await db.get_pending_order(order_id)
    if not order:
        await query.answer("Order not found!", show_alert=True)
        return

    if order["status"] != "pending":
        await query.answer(f"Already {order['status']}!", show_alert=True)
        return

    user_id = order["user_id"]
    credits = order["credits"]
    amount = order["amount"]
    admin_tag = f"@{query.from_user.username or query.from_user.id}"

    if action == "approve":
        await db.update_user_credits(user_id, credits)
        await db.update_order_status(order_id, "approved")

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
        except Exception as e:
            logger.error(f"User notify error: {e}")

        try:
            new_caption = (query.message.caption or "") + (
                f"\n\n✅ <b>APPROVED</b> by {admin_tag}"
            )
            await query.edit_message_caption(
                caption=new_caption, parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass

        await query.answer("✅ Approved!")

    elif action == "reject":
        await db.update_order_status(order_id, "rejected")

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
        except Exception as e:
            logger.error(f"User notify error: {e}")

        try:
            new_caption = (query.message.caption or "") + (
                f"\n\n❌ <b>REJECTED</b> by {admin_tag}"
            )
            await query.edit_message_caption(
                caption=new_caption, parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass

        await query.answer("❌ Rejected!")
