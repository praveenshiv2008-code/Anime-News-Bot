import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from pyrogram import Client
from pyrogram.errors import FloodWait

from config import API_ID, API_HASH, BOT_TOKEN, UPDATE_INTERVAL
from helper.news_job import broadcast_news
from helper.weekly_anime import send_weekly_anime
from route import web_server

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Client(
    "anime_news_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True
)

# ---------- Plugins ----------
import plugins.help
import plugins.admin
import plugins.anime
import plugins.img
import plugins.trending
import plugins.weekly
import plugins.start   # ensure you have this file

# ---------- Schedulers ----------
async def news_scheduler():
    interval = max(1, UPDATE_INTERVAL) * 60
    while True:
        try:
            await broadcast_news(app)
        except Exception as e:
            logger.error(f"News broadcast error: {e}")
        await asyncio.sleep(interval)

async def weekly_scheduler():
    ist = ZoneInfo("Asia/Kolkata")
    while True:
        now = datetime.now(ist)
        days_until_sunday = (6 - now.weekday()) % 7
        if days_until_sunday == 0 and now.hour == 0 and now.minute == 0:
            try:
                await send_weekly_anime(app)
            except Exception as e:
                logger.error(f"Weekly anime error: {e}")
            await asyncio.sleep(86400)
        else:
            await asyncio.sleep(60)

# ---------- Start Bot with FloodWait Retry ----------
async def start_bot_with_retry(max_retries=5):
    retries = 0
    while retries < max_retries:
        try:
            await app.start()
            logger.info("Bot started successfully.")
            return
        except FloodWait as e:
            wait = e.x
            logger.warning(f"FloodWait: need to wait {wait}s before retrying.")
            await asyncio.sleep(wait)
            retries += 1
        except Exception as e:
            logger.error(f"Fatal error starting bot: {e}")
            raise
    raise Exception("Max retries exceeded – could not start bot.")

# ---------- Main ----------
async def main():
    # Start health‑check web server
    await web_server()
    logger.info("Health‑check web server started.")

    # Start bot with retry logic
    await start_bot_with_retry()

    # Now start background tasks (they use the already‑started bot)
    asyncio.create_task(news_scheduler())
    asyncio.create_task(weekly_scheduler())

    # Keep running
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())