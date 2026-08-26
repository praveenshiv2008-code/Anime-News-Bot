import asyncio
import logging
import os
from aiohttp import web
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pyrogram import Client, filters
from pyrogram.errors import FloodWait

from config import API_ID, API_HASH, BOT_TOKEN, UPDATE_INTERVAL, PORT
from helper.news_job import broadcast_news
from route import web_server

# ---------- Logging ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ---------- Pyrogram Client ----------
class AnimeBot(Client):
    def __init__(self):
        super().__init__(
            "anime_session",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            plugins=dict(root="plugins"),   # auto‑load all .py files in plugins/
            in_memory=True
        )

    # ---------- Start ----------
    async def start(self):
        # Start the client and load plugins
        try:
            await super().start()
            logger.info("✅ Pyrogram client started.")
        except FloodWait as e:
            logger.warning(f"⏳ FloodWait: waiting {e.value}s before retry.")
            await asyncio.sleep(e.value)
            await super().start()
            logger.info("✅ Pyrogram client started after flood wait.")

        # ---------- Echo handler for diagnostics ----------
        @self.on_message(filters.text & filters.private)
        async def echo(client, message):
            logger.info(f"📩 Received: '{message.text}' from {message.from_user.id}")
            await message.reply_text(f"Echo: {message.text}")

        # ---------- Scheduler ----------
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            broadcast_news,
            "interval",
            minutes=max(1, UPDATE_INTERVAL),
            args=[self],
            id="news_broadcast",
            replace_existing=True
        )
        scheduler.start()
        logger.info(f"✅ Scheduler started – checking RSS every {UPDATE_INTERVAL} minute(s).")

        # Run once immediately
        asyncio.create_task(broadcast_news(self))
        logger.info("✅ First broadcast task launched.")

        # ---------- Web Server ----------
        try:
            # route.web_server() returns an aiohttp Application
            app_web = await web_server()
            runner = web.AppRunner(app_web)
            await runner.setup()
            site = web.TCPSite(runner, "0.0.0.0", PORT)
            await site.start()
            logger.info(f"✅ Health‑check web server running on port {PORT}")
        except Exception as e:
            logger.error(f"❌ Web server failed to start: {e}")

    # ---------- Stop ----------
    async def stop(self, *args):
        await super().stop()
        logger.info("🛑 Bot stopped.")

# ---------- Entry Point ----------
if __name__ == "__main__":
    AnimeBot().run()