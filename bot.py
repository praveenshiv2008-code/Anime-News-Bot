import asyncio
import logging
import os

from pyrogram import Client, filters
from pyrogram.types import Message

from config import API_ID, API_HASH, BOT_TOKEN
from route import web_server

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------- Pyrogram Client ----------
app = Client(
    "anime_news_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True
)

# ---------- Simple /start handler ----------
@app.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    logger.info(f"✅ /start from {message.from_user.id}")
    await message.reply_text("Hello! I'm alive and responding to /start.")

# ---------- Echo for any other text ----------
@app.on_message(filters.text & filters.private)
async def echo(client: Client, message: Message):
    logger.info(f"📩 Text from {message.from_user.id}: {message.text}")
    await message.reply_text(f"You said: `{message.text}`")

# ---------- Main ----------
async def main():
    # Start health server
    await web_server()
    logger.info("🌐 Health server started.")

    # Start bot
    await app.start()
    logger.info("✅ Bot started. Waiting for messages...")

    # Keep running
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())