import os
import logging
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler,
)

import database as db
from config import BOT_TOKEN, ADMIN_ID
from states import (
    MAIN_MENU, AD_CALC_VIEWS, AD_LINK_INPUT, AD_FINAL_VIEWS,
    BUY_CREDITS_INPUT, BUY_SCREENSHOT_INPUT,
    BROADCAST_CONTROL, BROADCAST_MESSAGE,
)

# Handlers
from handlers.start_handler import start, verify_join, main_menu_handler
from handlers.advertisement import (
    advertisement_start, ad_calc_input, ad_link_input, ad_final_views,
    claim_ad_credit,
)
from handlers.buy_credits import (
    buy_credits_start, buy_credits_callback,
    buy_credits_amount, buy_screenshot_handler,
)
from handlers.users import show_users
from handlers.cast import cast_command, cast_callback, broadcast_message_input
from handlers.payment import payment_action_callback

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def post_init(app: Application):
    """Sirf DB init karo — webhook run_webhook() khud set karega."""
    await db.init_db()
    logger.info("✅ Turso DB initialized")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"❌ Update {update} caused error {context.error}")
    import traceback
    logger.error("".join(traceback.format_exception(
        type(context.error), context.error, context.error.__traceback__
    )))


# ---------- DEBUG COMMAND ----------
async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Apna Telegram ID check karne ke liye."""
    user = update.effective_user
    await update.message.reply_text(
        f"🆔 <b>Your Telegram ID:</b> <code>{user.id}</code>\n"
        f"👤 Username: @{user.username or 'N/A'}\n"
        f"📛 Name: {user.first_name}\n\n"
        f"🔧 <b>Bot's ADMIN_ID (from env):</b> <code>{ADMIN_ID}</code>\n"
        f"✅ Match: <b>{user.id == ADMIN_ID}</b>",
        parse_mode="HTML",
    )


def main():
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # ---------- GROUP -1: Payment + Ad Claim callbacks (always active) ----------
    app.add_handler(
        CallbackQueryHandler(
            payment_action_callback,
            pattern=r"^(approve|reject)_\d+$",
        ),
        group=-1,
    )

    app.add_handler(
        CallbackQueryHandler(
            claim_ad_credit,
            pattern=r"^claim_\d+$",
        ),
        group=-1,
    )

    # ---------- GROUP 0: Debug commands ----------
    app.add_handler(CommandHandler("myid", myid_command), group=0)

    # ---------- GROUP 0: Main conversation handler ----------
    conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("cast", cast_command),
        ],
        states={
            MAIN_MENU: [
                MessageHandler(filters.Regex("^📢 Advertisement$"), advertisement_start),
                MessageHandler(filters.Regex("^💳 Buy Credits$"), buy_credits_start),
                MessageHandler(filters.Regex("^👥 Users$"), show_users),
                CallbackQueryHandler(verify_join, pattern="^verify_join$"),
                CallbackQueryHandler(buy_credits_callback, pattern="^buy_credits$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, main_menu_handler),
            ],
            AD_CALC_VIEWS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ad_calc_input),
            ],
            AD_LINK_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ad_link_input),
            ],
            AD_FINAL_VIEWS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ad_final_views),
            ],
            BUY_CREDITS_INPUT: [
                CallbackQueryHandler(buy_credits_callback, pattern="^buy_credits$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, buy_credits_amount),
            ],
            BUY_SCREENSHOT_INPUT: [
                MessageHandler(filters.PHOTO, buy_screenshot_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, buy_screenshot_handler),
            ],
            BROADCAST_CONTROL: [
                CallbackQueryHandler(cast_callback, pattern="^cast_(on|off)$"),
            ],
            BROADCAST_MESSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_message_input),
            ],
        },
        fallbacks=[
            CommandHandler("start", start),
            CommandHandler("cast", cast_command),
        ],
        allow_reentry=True,
    )

    app.add_handler(conv, group=0)
    app.add_error_handler(error_handler)

    # ---------- WEBHOOK / POLLING ----------
    PORT = int(os.environ.get("PORT", 8443))
    RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL")

    if RENDER_URL:
        logger.info(f"🚀 Starting webhook on port {PORT}")
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=f"/webhook/{BOT_TOKEN}",
            webhook_url=f"{RENDER_URL}/webhook/{BOT_TOKEN}",
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES,
        )
    else:
        logger.info("🚀 Starting polling (local mode)...")
        app.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
        )


if __name__ == "__main__":
    main()
