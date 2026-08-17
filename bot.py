import logging
import asyncio

from pyrogram import Client
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiohttp import web

from config import *
from helper.news_job import broadcast_news


# Professional logging setup
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

        self.web_runner = None
        self.scheduler = None

    async def start(self):
        await super().start()
        logging.info("✅ Pyrogram Client Started")

        # -----------------------------
        # Scheduler
        # -----------------------------
        self.scheduler = AsyncIOScheduler()

        self.scheduler.add_job(
            broadcast_news,
            "interval",
            minutes=UPDATE_INTERVAL,
            args=[self],
            id="broadcast_job",
            replace_existing=True
        )

        self.scheduler.start()

        logging.info(
            f"✅ Scheduler started — checking RSS every "
            f"{UPDATE_INTERVAL} minute(s)"
        )

        # -----------------------------
        # First RSS check
        # -----------------------------
        asyncio.create_task(broadcast_news(self))

        logging.info("✅ First broadcast task launched")

        # -----------------------------
        # Render Health Check Server
        # -----------------------------

        async def health(request):
            return web.Response(
                text="Anime News Bot is running! ✅",
                status=200
            )

        app = web.Application()

        app.router.add_get("/", health)
        app.router.add_get("/health", health)

        self.web_runner = web.AppRunner(app)

        await self.web_runner.setup()

        site = web.TCPSite(
            self.web_runner,
            "0.0.0.0",
            PORT
        )

        await site.start()

        logging.info(
            f"✅ Web server running on 0.0.0.0:{PORT}"
        )

    async def stop(self, *args):
        # Stop scheduler
        if self.scheduler:
            try:
                self.scheduler.shutdown(wait=False)
                logging.info("🛑 Scheduler stopped")
            except Exception as e:
                logging.error(
                    f"Scheduler shutdown error: {e}"
                )

        # Stop web server
        if self.web_runner:
            try:
                await self.web_runner.cleanup()
                logging.info("🛑 Web server stopped")
            except Exception as e:
                logging.error(
                    f"Web server shutdown error: {e}"
                )

        await super().stop()

        logging.info("🛑 Bot Stopped")


if __name__ == "__main__":
    AnimeBot().run()