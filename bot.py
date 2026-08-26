import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from pyrogram import Client

from config import API_ID, API_HASH, BOT_TOKEN, UPDATE_INTERVAL
from helper.news_job import broadcast_news
from helper.weekly_anime import send_weekly_anime
from route import web_server   # aiohttp health‑check server

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

# ---------- Load All Plugins ----------
import plugins.help
import plugins.admin
import plugins.anime
import plugins.img
import plugins.trending
import plugins.weekly
import plugins.start   # we add this now

# ---------- Background Tasks ----------
async def news_scheduler():
    """Run news broadcast every UPDATE_INTERVAL minutes."""
    interval = max(1, UPDATE_INTERVAL) * 60   # seconds
    while True:
        try:
            await broadcast_news(app)
        except Exception as e:
            logger.error(f"News broadcast error: {e}")
        await asyncio.sleep(interval)

async def weekly_scheduler():
    """Run weekly Top 16 every Sunday at midnight IST."""
    ist = ZoneInfo("Asia/Kolkata")
    while True:
        now = datetime.now(ist)
        days_until_sunday = (6 - now.weekday()) % 7
        if days_until_sunday == 0 and now.hour == 0 and now.minute == 0:
            try:
                await send_weekly_anime(app)
            except Exception as e:
                logger.error(f"Weekly anime error: {e}")
            await asyncio.sleep(86400)   # avoid re‑trigger
        else:
            await asyncio.sleep(60)      # check every minute

# ---------- Main ----------
async def main():
    # Start the aiohttp health‑check server
    await web_server()
    logger.info("Health‑check web server started.")

    # Start background tasks
    asyncio.create_task(news_scheduler())
    asyncio.create_task(weekly_scheduler())

    # Start the bot
    await app.start()
    logger.info("Bot started. Waiting for messages...")
    await asyncio.Event().wait()   # keep running

if __name__ == "__main__":
    asyncio.run(main())