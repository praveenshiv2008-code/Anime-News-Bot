import os

API_ID = int(os.environ.get("API_ID", ""))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
OWNER_ID = int(os.environ.get("OWNER_ID", ""))
ADMIN_ID = int(os.environ.get("ADMIN_ID", ""))
LOG_CHANNEL = os.environ.get("LOG_CHANNEL", "")
UPDATE_INTERVAL = int(os.environ.get("UPDATE_INTERVAL", "5"))  # minutes
PORT = int(os.environ.get("PORT", "8080"))  # for web health checks
DB_NAME = "anime_news"
DB_URL = os.environ.get("DB_URI", "")
# ... (your other message and image variables)