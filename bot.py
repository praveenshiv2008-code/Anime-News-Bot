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
            plugins=dict(root="plugins"),
            in_memory=True
        )
        self._started = False

    # ---------- Start client with non‑blocking retry ----------
    async def start_client_with_retry(self):
        """Attempt to start the client, retry on FloodWait without blocking."""
        retries = 0
        max_retries = 10
        while not self._started and retries < max_retries:
            try:
                await super().start()
                self._started = True
                logger.info("✅ Pyrogram client started.")
                # Now that client is up, schedule background tasks
                await self._schedule_tasks()
                return
            except FloodWait as e:
                wait = e.value
                retries += 1
                logger.warning(f"⏳ FloodWait: waiting {wait}s before retry (attempt {retries}/{max_retries}).")
                await asyncio.sleep(wait)
            except Exception as e:
                logger.error(f"❌ Client start failed: {e}")
                retries += 1
                await asyncio.sleep(60)  # wait a bit before retry
        if not self._started:
            logger.error("❌ Failed to start client after multiple retries.")

    # ---------- Schedule background tasks ----------
    async def _schedule_tasks(self):
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

    # ---------- Start health server and bot ----------
    async def start(self):
        # 1. Start health server first
        try:
            app_web = await web_server()
            runner = web.AppRunner(app_web)
            await runner.setup()
            site = web.TCPSite(runner, "0.0.0.0", PORT)
            await site.start()
            logger.info(f"✅ Health‑check web server running on port {PORT}")
        except Exception as e:
            logger.error(f"❌ Web server failed: {e}")

        # 2. Start client in background (non‑blocking)
        asyncio.create_task(self.start_client_with_retry())

        # 3. Echo handler (adds after client is started? Actually we can add it before)
        @self.on_message(filters.text & filters.private)
        async def echo(client, message):
            logger.info(f"📩 Received: '{message.text}' from {message.from_user.id}")
            await message.reply_text(f"Echo: {message.text}")

        # Keep the event loop alive
        await asyncio.Event().wait()

    # ---------- Stop ----------
    async def stop(self, *args):
        await super().stop()
        logger.info("🛑 Bot stopped.")

# ---------- Entry Point ----------
if __name__ == "__main__":
    AnimeBot().run()