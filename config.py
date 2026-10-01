import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME", "")  # e.g. "MyCreditsBot" (without @)
CHANNEL_ID = os.getenv("CHANNEL_ID")  # e.g. "@nr_hackz"
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
ADMIN_CHANNEL_ID = os.getenv("ADMIN_CHANNEL_ID")  # numeric ID e.g. -1001234567890
UPI_ID = os.getenv("UPI_ID", "yourupi@kotak")  # just for display text
UPI_NAME = os.getenv("UPI_NAME", "Bot Owner")
CREDITS_PER_RUPEE = float(os.getenv("CREDITS_PER_RUPEE", "1"))

# 1 credit = 5 views/taps
VIEWS_PER_CREDIT = 5

# Path to static payment QR image (in repo root)
PAY_IMAGE_PATH = os.path.join(os.path.dirname(__file__), "pay.png")
