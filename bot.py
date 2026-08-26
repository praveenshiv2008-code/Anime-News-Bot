import logging
import asyncio
from pyrogram import Client
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiohttp import web
from config import *
from route import web_server
from helper.news_job import broadcast_news

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

class AnimeBot(Client):
    def __init__(self):
        super().__init__(
            name="anime_session",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            plugins=dict(root="plugins")
        )

    async def start(self):
        await super().start()
        logging.info("✅ Pyrogram Client Started")

        # --- Scheduler ---
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            broadcast_news,
            "interval",
            minutes=UPDATE_INTERVAL,
            args=[self],
            id="broadcast_job",
            replace_existing=True
        )
        scheduler.start()
        logging.info(f"✅ Scheduler started — checking RSS every {UPDATE_INTERVAL} minute(s)")

        # --- First broadcast ---
        asyncio.create_task(broadcast_news(self))
        logging.info("✅ First broadcast task launched")

        # --- Web Server (fixed) ---
        try:
            await web_server()   # <-- this starts the server, no extra runner needed
            logging.info(f"✅ Web server running on port {PORT}")
        except Exception as e:
            logging.error(f"❌ Web server failed to start: {e}")

    async def stop(self, *args):
        await super().stop()
        logging.info("Bot Stopped")

if __name__ == "__main__":
    AnimeBot().run()