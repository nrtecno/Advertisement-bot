import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME", "")  # without @
CHANNEL_ID = os.getenv("CHANNEL_ID")  # @nr_hackz
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
ADMIN_CHANNEL_ID = os.getenv("ADMIN_CHANNEL_ID")  # -1001234567890
UPI_ID = os.getenv("UPI_ID", "yourupi@ybl")
UPI_NAME = os.getenv("UPI_NAME", "Bot Owner")
CREDITS_PER_RUPEE = float(os.getenv("CREDITS_PER_RUPEE", "1"))

VIEWS_PER_CREDIT = 5

PAY_IMAGE_PATH = os.path.join(os.path.dirname(__file__), "pay.png")
